from __future__ import division
from .base import BaseMode
from ..models import TalkProposal, KittendomeVotes, Meeting
from datetime import datetime, timedelta

CHAMPION_CALL_SECONDS = 30
CHAMPION_MINUTES = 2
DEBATE_MINUTES = 3

class Mode(BaseMode):
    """Review mode. Handles kittendome."""

    def __init__(self, bot):
        super(Mode, self).__init__(bot)

        # the current talks
        self.next = None
        self.current = None

        # the current meeting
        self.meeting = None

        # where we are in the review process for the current talk on the plate
        self.segment = None
        self.champions = []

    def chair_start(self, user, channel, meeting_num=None):
        """Start a meeting. If a meeting number is given, resume the
        meeting instead."""
        
        # get the next talk in queue
        try:
            self.next = TalkProposal.next_unreviewed_talk()
            self._in_meeting = True
        except IndexError:
            self.msg(channel, "Out of talks!")
            return
            
        # now pull up the meeting itself
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
            self.names(channel)

    def chair_end(self, user, channel):
        """Conclude the meeting."""
        
        self.msg(channel, "=== Th-th-th-that's all folks! ===")
        
        # remove any state handler that may be present
        self.bot.state_handler = None
        
        # end the meeting
        if self.meeting:
            self.meeting.end = datetime.now()
            self.meeting.save()
            self.meeting = None
            
        # pull out of this mode; ,end implies a reversion to skeleton mode
        self.chair_mode(user, channel, 'none', _silent=True)

    def chair_agenda(self, user, channel):
        """Print out the agenda. Attempt to assess how many talks are left
        and print out the expected agenda appropriately."""
                    
        # determine how many talks we expect to be left
        # first, we start with the expected number of talks; we'll be
        #   pessimistic and go with 12
        talk_count = 12
        
        # now, if we're more than 15 minutes into the meeting, then
        #   we can use the number of talks decided to guess how many we think
        #   will actually be left
        if hasattr(self, '_talks_remaining'):
            talk_count = self._talks_remaining + 1
        elif self.meeting:
            meeting_end = self.meeting.start + timedelta(minutes=70)
            time_left = meeting_end - datetime.now()
            talk_count = int(round(time_left.seconds / 300))

        # get the list of talks
        talks = TalkProposal.objects.filter(status__in=('unreviewed', 'hold')).order_by('talk_id')[0:talk_count]

        # sanity check: do we have any talks up to bat at all?
        if not talks:
            self.msg(channel, 'There are no talks on the agenda. Clearly, we shouldn\'t be here.')
            return

        # okay, show the talks coming next
        next_up = talks[0]
        subsequent_talks = talks[1:talk_count]

        # print out the current/next talk to the channel
        self.msg(channel, 'The %s talk on the table is:' % 'current' if self.current.talk_id == next_up.talk_id else 'next')
        self.msg(channel, next_up.review_url)
        
        # what about later talks? print them too
        upcoming_talks = ", ".join([str(t.talk_id) for t in subsequent_talks])
        if upcoming_talks:
            self.msg(channel, 'Subsequent talks will be: %s.' % upcoming_talks)
        else:
            self.msg(channel, 'The are no subsequent talks for today.')

    def chair_goto(self, user, channel, talk_id):
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

    def chair_next(self, user, channel, talks_remaining=None):
        """Move to the next talk, and immediately shift into champion mode."""

        # sanity check: are we in the post report phase?
        #   it's *really* easy to remember to issue ,report and not issue ,accept or ,reject
        #   and a call to ,next if this sequence has occured is almost certainly in error
        #   therefore, error out and force the chair to actually issue a decision
        if self.segment == 'post-report':
            self.msg(channel, 'We just had a report on the current talk. I am stubbornly refusing to move to the next talk until the current one has been officially accepted or rejected.')
            return
            
        # if we were told, now or previously, how many talks remain
        # in this meeting, then track that accordingly
        if talks_remaining is not None:
            self._talks_remaining = max(int(talks_remaining), 1)
        if hasattr(self, '_talks_remaining'):
            self._talks_remaining -= 1

        # figure out which talk is up now
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

        if getattr(self, '_talks_remaining', 3.14159):  # arbitrary non-zero number; I want "not set" to eval to True
            try:
                self.next = TalkProposal.next_unreviewed_talk(after=t)
                self.msg(channel, "(%s will be next)", self.next.review_url)
            except IndexError:
                self.msg(channel, 'This will be the last talk of kittendome!')
        else:
            self.msg(channel, 'This will be the last talk for today.')

        # begin the championing process
        # note: if this talk has *already* been debated and is, in fact, on hold,
        #   we have a different process for it
        if self.current.status == 'hold':
            self.bot.set_timer(channel, CHAMPION_CALL_SECONDS * 2, callback=self.chair_reject, callback_kwargs={ 'channel': channel, 'user': user })
            self.msg(channel, 'This talk, #%(talk_id)d, has already been debated and voted down (transcript: http://pyconbot.herokuapp.com/talks/%(talk_id)d).\nIf you think it deserves to go to thunderdome and want to attempt to resurrect it, please say "me". If there is a champion, then after the champion period, we will debate as normal. If there is no champion within %(time_text)s, this talk will be automatically rejected.' % {
                'talk_id': self.current.talk_id,
                'time_text': self._seconds_to_text(CHAMPION_CALL_SECONDS * 2),
            })
        else:
            self.bot.set_timer(channel, CHAMPION_CALL_SECONDS, callback=self.chair_debate, callback_kwargs={ 'channel': channel, 'user': user })
            self.msg(channel, 'If you are a champion for #%d, or willing to champion it, please say, "me". If nobody steps up within %s, we will move on to debate.' % (self.current.talk_id, self._seconds_to_text(CHAMPION_CALL_SECONDS)))

        # start watching what users say
        self.bot.state_handler = self.handler_user_champion

        # tell the bot that we are currently in champion mode
        self.segment = 'champion'

    def chair_next_champion(self, user, channel, _initial=False):
        """Move to the next champion. Normally, this is called automatically by a champion's self-designation
        or by a first champion's being finished, giving way to the next one. However, this allows the chair to
        manually continue the process if needed."""

        # move to the next champion
        if not _initial and len(self.champions):
            self.champions.pop(0)

        # sanity check: are there any champions?
        if not self.champions:
            self.msg(channel, 'There are no more champions in queue. Moving on to debate.')
            self.debate(channel)
            return

        # this user is up; tell him what to do
        champion = self.champions[0]
        self.msg(channel, '%s: You\'re up. Please type a succinct argument for the inclusion of #%d. When you are finished, please type "done".' % (champion, self.current.talk_id))

        # clear any existing timer
        self.bot.clear_timer()

    def chair_debate(self, user, channel, debate_time=DEBATE_MINUTES):
        """Shift the channel into debate mode, and set the appropriate timer."""

        # clear out the state handler
        self.bot.state_handler = None

        # actually set the bot timer
        self.bot.set_timer(channel, float(debate_time) * 60)

        # now report the shift to debate mode
        self.segment = 'debate'
        self.msg(channel, "=== General Debate (%s) for Talk: #%d ===", self._minutes_to_text(debate_time), self.current.talk_id)

    def chair_extend(self, user, channel, extend_time=1):
        """Extend the time on the clock. In reality, this does nothing
        but set another clock, but it's a useful management tool within meetings."""

        # clear the timer and set a new one
        self.bot.clear_timer()
        self.bot.set_timer(channel, float(extend_time) * 60)

        # now report the extension
        self.msg(channel, '=== Extending time by %s. Please continue. ===' % self._minutes_to_text(extend_time))

    def chair_vote(self, user, channel):
        self.bot.clear_timer()
        self.current_votes = {}
        self.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===", self.current.talk_id)
        self.msg(channel, "Please do not speak after voting until we've gotten our report.")
        self.segment = 'voting'
        self.bot.state_handler = self.handler_user_vote

    def chair_report(self, user, channel):
        if not self.current:
            return
            
        # turn off the state handler
        self.bot.state_handler = None

        # tally the vote
        yay, nay, abstain = 0, 0, 0
        for vote in self.current_votes.itervalues():
            if vote == 'yay':
                yay += 1
            elif vote == 'nay':
                nay += 1
            elif vote == 'abstain':
                abstain += 1
                
        # cobble together the report on the talk votes
        report = '=== Votes on #%d: %d in favor, %d opposed' % (self.current.talk_id, yay, nay)
        if abstain > 0:
            report += ', with %d abstention%s' % (abstain, 's' if abstain != 1 else '')
        report += ' ==='
        self.msg(channel, report)
        
        # Save the votes for posterity
        self.current.kittendome_votes = KittendomeVotes(yay=yay, nay=nay, abstain=abstain)
        self.current.save()

        # tell the system that we're between reporting and moving
        # to the next talk
        self.segment = 'post-report'

    def chair_accept(self, user, channel):
        self._make_decision(user, channel, 'thunderdome', 'Talk #%s accepted; moves on to thunderdome.')

    def chair_reject(self, user, channel):
        self._make_decision(user, channel, 'rejected', 'Talk #%s rejected.')

    def chair_poster(self, user, channel):
        self._make_decision(user, channel, 'poster', 'Talk #%s rejected (suggest re-submission as poster).')

    def chair_hold(self, user, channel):
        self._make_decision(user, channel, 'hold', 'Talk #%s put on hold; will be reviewed at a future meeting.')

    def private_rules(self, user):
        """Report where the user may find the rules and process notes."""

        self.msg(user, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.msg(user, "Notes about process: http://bit.ly/pycon-pc-format")
        
    def private_current(self, user):
        """Report on the current talk, and provide the link to view the talk
        on the PyCon PC website. Also, report where we are in the proceedings."""
        
        # sanity check: are we on a talk at all?
        if not self.current or not self.segment:
            self.msg(user, 'There is no current talk in the system.')
            return
    
        # okay, there is a current talk; show it
        self.msg(user, 'We are currently reviewing:')
        self.msg(user, '    #%d: %s (%s)' % (self.current.talk_id, self.current.title, self.current.speaker))
        self.msg(user, '    %s' % self.current.review_url)
        if self.segment == 'champion':
           self.msg(user, 'Currently, the talk is being championed. Please refrain from speaking until debate.')
        elif self.segment == 'debate':
            self.msg(user, 'Currently, we are in debate. Feel free to participate.')
        elif self.segment == 'voting':
            self.msg(user, 'Currently, we are voting.')
        
    def private_next(self, user):
        """Report the next talk, and provide the link to view the talk
        on the PyCon PC website."""
        
        # sanity check: is there a next talk in the system?
        if not self.next:
            message = 'There is no upcoming talk.'
            if self.current:
                message += ' We will be done after this talk.'
            self.msg(user, message)
            return
        
        # report on the talk coming next
        self.msg(user, 'The next talk to be discussed will be:')
        self.msg(user, '    #%d: %s (%s)' % (self.next.talk_id, self.next.title, self.next.speaker))
        self.msg(user, '    %s' % self.next.review_url)
        
    def handler_user_vote(self, user, channel, message):
        message = message.strip().lower()
        if message == 'y' or message.startswith(('yes', 'yay', 'yea', 'aye', '+1')):
            self.current_votes[user] = 'yay'
        elif message == 'n' or message.startswith(('no', 'nay', '-1')):
            self.current_votes[user] = 'nay'
        elif message == 'a' or message.startswith(('abs', 'abstain', '0')):
            self.current_votes[user] = "abstain"
        else:
            self.msg(channel, "%s: please vote yay, nay, or abstain.", user)
    
    def handler_user_champion(self, user, channel, message):
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
                    self.chair_next_champion(user, channel, _initial=True)
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
                        self.chair_next_champion(user, channel)
                    else:
                        self.chair_debate(user, channel, debate_time=2 if self.current.status == 'hold' else 3)
                        
    def event_user_joined(self, user, channel):
        """React to a user's joining the channel when a meeting is
        already in progress."""
        
        # sanity check: if we're not in a meeting, then no need
        # to do anything at all
        if not self._in_meeting:
            return
            
        # sanity check: if the user is already in the non-voter list,
        # then this is a red herring; ignore it
        if user in self.nonvoters:
            return
            
        # spit out a welcome, and a request for a name, to the meeting channel,
        # but tailor the request to where we are
        if self.segment in ('champion', 'voting'):
            self.msg(channel, 'Howdy %s. Right now we are in the %s segment on talk #%d. Please print your name for the record, but wait until this segment concludes.' % (user, self.segment, self.current.talk_id))
        else:
            self.msg(channel, 'Howdy %s; name for the record, please?' % user)
        
        # also, send the user a welcome with information about
        # where we are and what's going on
        self.msg(user, 'Thanks for coming, %s! This meeting has already begun.' % user)
        if self.current:
            self.msg(user, 'Currently, we are on talk #%d (%s). We are in the %s segment.' % (self.current.talk_id, self.current.review_url, self.segment))
        else:
            self.msg(user, 'There is no current talk under consideration at this moment.')
            
        # now give a quick overview of bot abilities
        self.msg(user, 'You may issue me commands via. private message if you like. Issue `help` at any time for a list.')

    def log_message(self, user, channel, message):
        """
        Save a transcript for debate along with each talk.
        """
        if self.meeting:
            self.meeting.add_to_transcript(datetime.now(), user, message)
        if self.current:
            self.current.add_to_transcript(datetime.now(), user, message)

    def _make_decision(self, user, channel, decision, message):
        """Make a given decision, and save it to the database."""
        
        # clear any timer and any user mode
        self.bot.clear_timer()
        self.bot.state_handler = None
        self.segment = None
        
        # actually make the decision
        if not self.current:
            return
        self.msg(channel, "=== %s ===" % message, self.current.talk_id)
        self.current.status = decision
        self.current.kittendome_result = decision
        self.current.save()
        
        # place the talk into the meeting's `talks_decided` list
        if self.meeting:
            # don't push the same talk onto a meeting twice
            # (when there's duplication, it's almost always bot operator error)
            meeting_copy = Meeting.objects.get(id=self.meeting.id)
            if self.current not in meeting_copy.talks_decided:
                Meeting.objects(id=self.meeting.id).update_one(push__talks_decided=self.current)
                
            # if this is the last talk, end
            if hasattr(self, '_talks_remaining') and self._talks_remaining == 0:
                self.chair_end(user, channel)