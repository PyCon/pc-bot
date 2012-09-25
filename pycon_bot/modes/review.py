from __future__ import division
from .base import BaseBotMode
from ..models import TalkProposal, KittendomeVotes, Meeting
from datetime import datetime

CHAMPION_MINUTES = 2
DEBATE_MINUTES = 3

class ReviewMode(BaseBotMode):

    def __init__(self, bot):
        super(ReviewMode, self).__init__(bot)
        self.next = None
        self.current = None
        self.meeting = None

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

    def handle_end(self, channel):
        self.msg(channel, "=== Th-th-th-that's all folks! ===")
        self.meeting.end = datetime.now()
        self.meeting.save()
        self.meeting = None

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

    def handle_next(self, channel, champion_time=CHAMPION_MINUTES):
        """Move to the next talk, and immediately shift into champion mode."""
        
        champion_time = int(float(champion_time) * 60)
        
        # Clear out the state handler in case we're voting.
        self.bot.state_handler = None

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

        # Announce the talk
        self.bot.set_timer(channel, champion_time)
        self.msg(channel, "=== Talk %d: %s - %s ===", t.talk_id, t.title, t.review_url)

        try:
            self.next = TalkProposal.next_unreviewed_talk(after=t)
            self.msg(channel, "(%s will be next)", self.next.review_url)
        except IndexError:
            pass
            
        # make nice, human readable time text
        # (even though, in reality, there's no good reason for this ever to not be 2 minutes)
        champion_time_text = '%d minutes' % (champion_time // 60)
        if champion_time % 60:
            champion_time_text += ', %d seconds' % (champion_time % 60)

        # begin the championing process
        self.msg(channel, ' * * * ')
        self.msg(channel, 'If you are a champion for #%s, or '
            'willing to champion it, please say, "me". Then, please type a succinct argument for '
            'inclusion of this talk (%s). Say "done" when you are finished.', t.talk_id, champion_time_text)

    def handle_debate(self, channel, debate_time=DEBATE_MINUTES):
        """Shift the channel into debate mode, and set the appropriate timer."""
        
        # parse out the debate time, and make nice, optimal
        # human readable text
        debate_time = int(float(debate_time) * 60)
        debate_time_text = '%d minutes' % (debate_time // 60)
        if debate_time % 60:
            debate_time_text += ', %d seconds' % (debate_time % 60)
        
        # actually set the bot timer
        self.bot.set_timer(channel, debate_time)
        
        # now report the shift to debate mode
        self.msg(channel, "=== General Debate (%s) for Talk: #%d ===", debate_time_text, self.current.talk_id)
        
    def handle_extend(self, channel, extend_time=1):
        """Extend the time on the clock. In reality, this does nothing
        but set another clock, but it's a useful management tool within meetings."""
        
        # what's the human readable extension time?
        extend_time = int(float(extend_time) * 60)
        extend_time_text = '%d minute%s' % (
            extend_time // 60,
            '' if extend_time == 60 else 's',
        )
        
        # add seconds if appropriate
        if extend_time % 60:
            extend_time_text += ', %d seconds' % (extend_time % 60)
                
        # clear the timer and set a new one
        self.bot.clear_timer()
        self.bot.set_timer(channel, extend_time)
        
        # now report the extension
        self.msg(channel, '=== Extending time by %s. Please continue. ===' % extend_time_text)

    def handle_vote(self, channel):
        self.bot.clear_timer()
        self.current_votes = {}
        self.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===", self.current.talk_id)
        self.msg(channel, "Please do not speak after voting until we've gotten our report.")
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
