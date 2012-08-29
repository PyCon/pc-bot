import datetime
from .base import BaseBotMode
from ..models import TalkProposal, KittendomeVotes, Meeting

CHAMPION_SECONDS = 2
DEBATE_SECONDS = 3

class ReviewMode(BaseBotMode):

    def __init__(self, bot):
        super(ReviewMode, self).__init__(bot)
        self.next = None
        self.current = None
        self.meeting = None

    def handle_start(self, channel):
        try:
            self.next = TalkProposal.objects(status='unreviewed')[0]
        except IndexError:
            self.msg(channel, "Out of talks!")
            return
        self.meeting = Meeting.objects.create(start=datetime.datetime.now())
        self.msg(channel, '=== Meeting #%s started. Next talk will be #%s ===', self.meeting.number, self.next.talk_id)

    def handle_end(self, channel):
        self.msg(channel, "=== Th-th-th-that's all folks! ===")
        self.meeting.end = datetime.datetime.now()
        self.meeting.save()
        self.meeting = None

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
        # Clear out the state handler in case we're voting.
        self.bot.state_handler = None

        # Figure out which talk is up now.
        if self.next:
            t = self.current = self.next
            self.next = None
        else:
            try:
                t = self.current = TalkProposal.objects(status='unreviewed')[0]
            except IndexError:
                self.msg(channel, "Out of talks!")
                return

        # Announce the talk
        self.bot.set_timer(channel, CHAMPION_SECONDS)
        self.msg(channel, "=== Talk %d: %s - %s ===", t.talk_id, t.title, t.review_url)

        try:
            self.next = TalkProposal.objects(status='unreviewed', talk_id__ne=t.talk_id)[0]
        except IndexError:
            pass
        else:
            self.msg(channel, "(%s will be next)", self.next.review_url)

        self.msg(channel, "If you are (a/the) champion for #%s, or "
            "willing to champion the it, please say 'me'. Then, please type a succinct argument for "
            "inclusion of this talk. (2 Minutes). Say 'done' when you are finished.", t.talk_id)

    def handle_debate(self, channel):
        self.bot.set_timer(channel, DEBATE_SECONDS)
        self.msg(channel, "=== General Debate (3 minutes) for Talk: #%d ===", self.current.talk_id)

    def handle_vote(self, channel):
        self.bot.clear_timer()
        self.current_votes = {}
        self.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===", self.current.talk_id)
        self.msg(channel, "Please do not speak after voting until we've gotten our report.")
        self.bot.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        message = message.strip().lower()
        if message in ("y", "yes", "yay", "yea", "+1"):
            self.current_votes[user] = "yay"
        elif message in ("n", "no", "nay", "-1"):
            self.current_votes[user] = "nay"
        elif message in ("a", "abs", "abstain", "0"):
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
        self.current.kittendome_votes = KittendomeVotes(yay=yay, nay=nay, abs=abstain)
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
            self.meeting.add_to_transcript(datetime.datetime.now(), user, message)
        if self.current:
            self.current.add_to_transcript(datetime.datetime.now(), user, message)
