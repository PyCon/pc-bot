from .base import BaseBotMode
from ..models import TalkProposal, KittendomeVotes

CHAMPION_SECONDS = 2*60
DEBATE_SECONDS = 3*60

class ReviewBot(BaseBotMode):

    def __init__(self, bot):
        super(ReviewBot, self).__init__(bot)

    def handle_start(self, channel):
        for i, talk in enumerate(self.talks):
            if "decision" not in talk:
                break
        if i > 0:
            self.idx = i - 1
            next_id = self.talks[i]['id']
            self.bot.msg(channel, "=== Skipped %s talks; next will be #%d ===" % (i, next_id))
        else:
            self.bot.msg(channel, "=== Ready (no talks to skip). ===")

    def handle_goto(self, channel, talk_id):
        try:
            talk_id = int(talk_id)
        except ValueError:
            self.bot.msg(channel, "Erm, %s doesn't seem to be a talk ID." % talk_id)
            return
        for i, talk in enumerate(self.talks):
            if talk['id'] == talk_id:
                self.idx = i - 1
                next_talk = self.talks[i]
                msg = "OK, the next talk will be #{id}."
                if 'decision' in next_talk:
                    msg += " This talk was previously {decision}"
                    if 'votes' in next_talk:
                        msg += ' by a vote of {votes[yay]}/{votes[nay]}/{votes[abstain]}'
                    msg += '.'
                self.bot.msg(channel, msg.format(**next_talk))
                break
        else:
            self.bot.msg(channel, "Uh oh, I couldn't find talk ID %s." % talk_id)

    def handle_next(self, channel):
        self.idx += 1
        self.bot.state_handler = None
        try:
            talk = self.talks[self.idx]
        except IndexError:
            self.bot.msg(channel, "Out of talks")
            return

        self.bot.set_timer(channel, CHAMPION_SECONDS)
        self.bot.msg(channel, str("=== Talk %d: %s - %s ===" % (
            talk["id"], talk["name"], self.talk_url(talk["id"])
        )))

        try:
            next = self.talks[self.idx+1]
        except IndexError:
            pass
        else:
            self.bot.msg(channel, "(%s will be next)" % self.talk_url(next['id']))

        self.bot.msg(channel, "If you are (a/the) champion for #%s, or "
            "willing to champion the it, please say 'me'. Then, please type a succinct argument for "
            "inclusion of this talk. (2 Minutes). Say 'done' when you are finished." % talk['id'])

    def handle_debate(self, channel):
        self.bot.set_timer(channel, DEBATE_SECONDS)
        talk = self.talks[self.idx]
        self.bot.msg(channel, "=== General Debate (3 minutes) for Talk: #%d ===" % (
            talk["id"]
        ))

    def handle_vote(self, channel):
        self.bot.clear_timer()
        self.current_votes = {}
        talk = self.talks[self.idx]
        self.bot.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===" % (
            talk["id"]
        ))
        self.bot.msg(channel, "Please do not speak after voting until we've gotten "
            "our report.")
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
            self.bot.msg(channel, "%s: please vote yay, nay, or abstain." % user)

    def handle_report(self, channel):
        talk = self.talks[self.idx]
        yay, nay, abstain = 0, 0, 0
        for vote in self.current_votes.itervalues():
            if vote == 'yay':
                yay += 1
            elif vote == 'nay':
                nay += 1
            elif vote == 'abstain':
                abstain += 1
        self.bot.msg(channel, "=== Talk Votes on #%s: %s yays, %s nays, %s abstentions ===" % (talk['id'], yay, nay, abstain))
        if yay > nay:
            msg = "The yays have it."
        elif nay > yay:
            msg = "The nays have it."
        elif yay == nay:
            msg = "It's a tie: http://i.imgur.com/Cw3lg.jpg"
        self.bot.msg(channel, msg)
        self.bot.state_handler = None

        # Save the votes for posterity
        self.talks[self.idx]["votes"] = {"yay": yay, "nay": nay, "abstain": abstain}
        self.save_state()

    def handle_accept(self, channel):
        self._make_decision(channel, 'accepted', 'talk #{id} accepted, moves on to thunderdome.')

    def handle_reject(self, channel):
        self._make_decision(channel, 'rejected', 'talk #{id} rejected.')

    def handle_poster(self, channel):
        self._make_decision(channel, 'poster', 'talk #{id} rejected; suggest re-submission as poster.')

    def handle_table(self, channel):
        self._make_decision(channel, 'tabled', 'talk #{id} tabled, will be reviewed at a future meeting.')

    def _make_decision(self, channel, decision, message):
        self.bot.clear_timer()
        talk = self.talks[self.idx]
        self.bot.msg(channel, "=== Chair decision: %s ===" % message.format(**talk))
        self.talks[self.idx]["decision"] = decision
        self.save_state()

    def handle_rules(self, channel):
        """Remind participants where they can find the rules."""
        self.bot.msg(channel, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.bot.msg(channel, "Notes about process: http://bit.ly/pycon-pc-format")
