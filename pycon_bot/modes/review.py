from __future__ import division
from .base import BaseBotMode
from ..models import TalkProposal, KittendomeVotes, Meeting
from datetime import datetime

CHAMPION_CALL_SECONDS = 30
CHAMPION_MINUTES = 2
DEBATE_MINUTES = 3

class ReviewMode(BaseBotMode):

    def __init__(self, bot):
        super(ReviewMode, self).__init__(bot)
        
        # the current talks
        self.next = None
        self.current = None
        
        # the current meeting
        self.meeting = None
        
        # where we are in the review process for the current talk on the plate
        self.segment = None
        self.champions = []

    def handle_start(self, channel, meeting_num=None):
        try:
            self.next = TalkProposal.next_unreviewed_talk()
        except IndexError:
            self.msg(channel, "Out of talks!")
            return
        try:
            self.meeting = Meeting.objects.get(number=meeting_num)
            action = "resumed"
        except Meeting.DoesNotExist:
            self.meeting = Meeting.objects.create(start=datetime.now())
            action = "started"
        self.msg(channel, '=== Meeting #%s %s. Next talk will be #%s ===',
                 self.meeting.number, action, self.next.talk_id)
                 
        # now ask the folks in channel for names (unless this is a resumed meeting)
        if not meeting_num:
            self.handle_names(channel)

    def handle_end(self, channel):
        self.msg(channel, "=== Th-th-th-that's all folks! ===")
        self.meeting.end = datetime.now()
        self.meeting.save()
        self.meeting = None
        
    def handle_current(self, channel):
        """Output to the channel the current talk we're on."""
        
        # sanity check: are we on a talk at all?
        if not self.current or not self.segment:
            self.msg(channel, 'There is no current talk in the system.')
            return
            
        # okay, there is a current talk; show it
        self.msg(channel, 'We are reviewing %s.' % self.current.review_url)
        if self.segment == 'champion':
           self.msg(channel, 'Currently, the talk is being championed. Please refrain from speaking until debate.')
        elif self.segment == 'debate':
            self.msg(channel, 'Currently, we are in debate. Feel free to participate.')
        elif self.segment == 'voting':
            self.msg(channel, 'Currently, we are voting.')

    def handle_agenda(self, channel, talk_count=12):
        try:
            talk_count = int(talk_count)
        except ValueError:
            return
            
        # get the list of talks
        talks = TalkProposal.objects.filter(status='unreviewed').order_by('talk_id')[0:talk_count]
        
        # sanity check: do we have any talks up to bat at all?
        if not talks:
            self.msg(channel, 'There are no talks on the agenda. Clearly, we shouldn\'t be here.')
            return
            
        # okay, show the talks coming next
        next_up = talks[0]
        subsequent_talks = talks[1:talk_count]
        
        # print out the list to the channel
        self.msg(channel, 'The next talk on the table is:')
        self.msg(channel, next_up.review_url)
        self.msg(channel, 'Subsequent talks will be: %s.' % ", ".join([str(t.talk_id) for t in subsequent_talks]))

    def handle_goto(self, channel, talk_id):
        try:
            self.next = TalkProposal.objects.get(talk_id=talk_id)
        except TalkProposal.DoesNotExist:
            self.msg(channel, "Erm, %s doesn't seem to be a talk ID.", talk_id)
            return
        msg = "OK, the next talk will be %s. This talk is %s." % \
              (self.next.talk_id, self.next.get_status_display())
        if self.next.kittendome_votes:
            msg += " Previous vote was %s." % self.next.kittendome_votes
        self.msg(channel, msg)

    def handle_next(self, channel):
        """Move to the next talk, and immediately shift into champion mode."""
        
        # Figure out which talk is up now.
        if self.next:
            t = self.current = self.next
            self.next = None
        else:
            try:
                t = self.current = TalkProposal.next_unreviewed_talk()
            except IndexError:
                self.msg(channel, "Out of talks!")
                return
                
        # this is a new talk; no champions have declared themselves
        self.champions = []

        # announce the talk
        self.msg(channel, "=== Talk %d: %s - %s ===", t.talk_id, t.title, t.review_url)

        try:
            self.next = TalkProposal.next_unreviewed_talk(after=t)
            self.msg(channel, "(%s will be next)", self.next.review_url)
        except IndexError:
            pass
            
        # begin the championing process
        # note: if this talk has *already* been debated and is, in fact, on hold,
        #   we have a different process for it
        if self.current.status == 'hold':
            self.bot.set_timer(channel, CHAMPION_CALL_SECONDS * 2, callback=self.handle_reject, callback_kwargs={ 'channel': channel })
            self.msg(channel, 'This talk, #%d, has already been debated and voted down. If you think it deserves to go to thunderdome and want to attempt to resurrect it, please say "me". If there is a champion, then after the champion period, we will debate as normal. If there is no champion within %s, this talk will be automatically rejected.', self.current.talk_id, self._seconds_to_text(CHAMPION_CALL_SECONDS * 2))
        else:
            self.bot.set_timer(channel, CHAMPION_CALL_SECONDS, callback=self.handle_debate, callback_kwargs={ 'channel': channel })
            self.msg(channel, 'If you are a champion for #%d, or willing to champion it, please say, "me". If nobody steps up within %s, we will move on to debate.' % (self.current.talk_id, self._seconds_to_text(CHAMPION_CALL_SECONDS)))
        
        # start watching what users say
        self.bot.state_handler = self.handle_user_champion
        
        # tell the bot that we are currently in champion mode
        self.segment = 'champion'
        
    def handle_user_champion(self, channel, user, message):
        """Handle the baton pass where a user declares that he will champion a talk,
        and give him time to do it. Gripe at anyone who goes off script unless it's a superuser."""
        
        # if this message is "me", add the person to the champion list
        # and address appropriately
        message = message.lower().strip().rstrip('.')
        if message == 'me':
            # add this user to the champion queue
            if user not in self.champions:
                self.champions.append(user)
            
                # should this user champion immediately, or is he
                # in queue behind someone?
                if len(self.champions) == 1:
                    self.handle_next_champion(channel, _initial=True)
                else:
                    # tell this user to hold off for a bit...
                    self.msg(channel, '%s: Excellent. Please champion #%d, but wait until %s is finished.' % (user, self.current.talk_id, self.champions[0]))
        else:
            # if this isn't the championing user, tell them to STFU
            if not self.champions or user != self.champions[0]:
                # is this user in queue later?
                instructions = '%s: Please do not speak during the championing process. If you want to champion #%d, please say "me".'
                if user in self.champions:
                    instructions = '%s: You are in line to champion #%d, but please be quiet until it is your turn.'
                self.msg(channel, instructions % (user, self.current.talk_id))
                
            # if this is the championing user, check to see if he's done
            if self.champions and user == self.champions[0]:
                if message.rstrip().endswith(('done', 'done.', 'done!')):
                    # okay, this person is done. pop him off the champion list
                    self.msg(channel, '%s: Thank you.' % user)
                    
                    # is there anyone else in line to champion? if so, move on
                    # to that person, otherwise move to debate
                    if len(self.champions) > 1:
                        self.handle_next_champion(channel)
                    else:
                        self.handle_debate(channel, debate_time=2 if self.current.status == 'hold' else 3)
                        
    def handle_next_champion(self, channel, _initial=False):
        """Move to the next champion. Normally, this is called automatically by a champion's self-designation
        or by a first champion's being finished, giving way to the next one. However, this allows the chair to
        manually continue the process if needed."""
        
        # move to the next champion
        if not _initial and len(self.champions):
            self.champions.pop(0)
            
        # sanity check: are there any champions?
        if not self.champions:
            self.msg(channel, 'There are no more champions in queue. Moving on to debate.')
            self.handle_debate(channel)
            return
            
        # this user is up; tell him what to do
        champion = self.champions[0]
        self.msg(channel, '%s: You\'re up. Please type a succinct argument for the inclusion of #%d. When you are finished, please type "done".' % (champion, self.current.talk_id))
        
        # clear any existing timer
        self.bot.clear_timer()

    def handle_debate(self, channel, debate_time=DEBATE_MINUTES):
        """Shift the channel into debate mode, and set the appropriate timer."""
        
        # clear out the state handler
        self.bot.state_handler = None
                
        # actually set the bot timer
        self.bot.set_timer(channel, float(debate_time) * 60)
        
        # now report the shift to debate mode
        self.segment = 'debate'
        self.msg(channel, "=== General Debate (%s) for Talk: #%d ===", self._minutes_to_text(debate_time), self.current.talk_id)
        
    def handle_extend(self, channel, extend_time=1):
        """Extend the time on the clock. In reality, this does nothing
        but set another clock, but it's a useful management tool within meetings."""
                        
        # clear the timer and set a new one
        self.bot.clear_timer()
        self.bot.set_timer(channel, float(extend_time) * 60)
        
        # now report the extension
        self.msg(channel, '=== Extending time by %s. Please continue. ===' % self._minutes_to_text(extend_time))

    def handle_vote(self, channel):
        self.bot.clear_timer()
        self.current_votes = {}
        self.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===", self.current.talk_id)
        self.msg(channel, "Please do not speak after voting until we've gotten our report.")
        self.segment = 'voting'
        self.bot.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        message = message.strip().lower()
        if message == 'y' or message.startswith(('yes', 'yay', 'yea', 'aye', '+1')):
            self.current_votes[user] = 'yay'
        elif message == 'n' or message.startswith(('no', 'nay', '-1')):
            self.current_votes[user] = 'nay'
        elif message == 'a' or message.startswith(('abs', 'abstain', '0')):
            self.current_votes[user] = "abstain"
        else:
            self.msg(channel, "%s: please vote yay, nay, or abstain.", user)

    def handle_report(self, channel):
        if not self.current:
            return

        yay, nay, abstain = 0, 0, 0
        for vote in self.current_votes.itervalues():
            if vote == 'yay':
                yay += 1
            elif vote == 'nay':
                nay += 1
            elif vote == 'abstain':
                abstain += 1
        self.msg(channel, "=== Talk Votes on #%s: %s yays, %s nays, %s abstentions ===", self.current.talk_id, yay, nay, abstain)
        if yay > nay:
            msg = "The yays have it."
        elif nay > yay:
            msg = "The nays have it."
        elif yay == nay:
            msg = "It's a tie: http://i.imgur.com/Cw3lg.jpg"
        self.msg(channel, msg)
        self.bot.state_handler = None

        # Save the votes for posterity
        self.current.kittendome_votes = KittendomeVotes(yay=yay, nay=nay, abstain=abstain)
        self.current.save()
        
        # tell the system that we're not in any segment
        # (used only for reports from ,current right now)
        self.segment = None

    def handle_accept(self, channel):
        self._make_decision(channel, 'thunderdome', 'talk #%s accepted, moves on to thunderdome.')

    def handle_reject(self, channel):
        self._make_decision(channel, 'rejected', 'talk #%s rejected.')

    def handle_poster(self, channel):
        self._make_decision(channel, 'poster', 'talk #%s rejected; suggest re-submission as poster.')

    def handle_hold(self, channel):
        self._make_decision(channel, 'hold', 'talk #%s put on hold, will be reviewed at a future meeting.')

    def _make_decision(self, channel, decision, message):
        self.bot.clear_timer()
        if not self.current:
            return
        self.msg(channel, "=== Chair decision: %s ===" % message, self.current.talk_id)
        self.current.status = decision
        self.current.save()
        if self.meeting:
            # don't push the same talk onto a meeting twice
            # (when there's duplication, it's almost always bot operator error)
            meeting_copy = Meeting.objects.get(id=self.meeting.id)
            if self.current not in meeting_copy.talks_decided:
                Meeting.objects(id=self.meeting.id).update_one(push__talks_decided=self.current)

    def handle_rules(self, channel):
        """Remind participants where they can find the rules."""
        
        self.msg(channel, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.msg(channel, "Notes about process: http://bit.ly/pycon-pc-format")

    def log_message(self, user, channel, message):
        """
        Save a transcript for debate along with each talk.
        """
        if self.meeting:
            self.meeting.add_to_transcript(datetime.now(), user, message)
        if self.current:
            self.current.add_to_transcript(datetime.now(), user, message)