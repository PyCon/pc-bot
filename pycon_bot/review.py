import json
import os

from pycon_bot.base import main, BasePyConBot


class PyConReviewBot(BasePyConBot):
    commands = frozenset(["next", "debate", "vote", "report"])
    with open(os.path.join(os.path.dirname(__file__), 'talks.json')) as f:
        talks = json.load(f)

    def __init__(self):
        BasePyConBot.__init__(self)
        self.idx = -1

    def handle_next(self, channel):
        self.idx += 1
        self.state_handler = None
        try:
            talk = self.talks[self.idx]
        except IndexError:
            self.msg(channel, "Out of talks")
            return
        self.msg(channel, str("==== Talk %d: %s now, %s ====" % (
            talk["id"], talk["name"], self.talk_url(talk["id"])
        )))
        self.msg(channel, "If you are (a/the) champion for this talk, or "
            "willing to champion the talk, please type a succinct argument for "
            "inclusion of this talk. (2 Minutes). State when you are done.")

    def handle_debate(self, channel):
        talk = self.talks[self.idx]
        self.msg(channel, "==== General Debate (3 minutes) for Talk: #%d ====" % (
            talk["id"]
        ))

    def handle_vote(self, channel):
        talk = self.talks[self.idx]
        self.msg(channel, "==== Voting time! yay/nay votes for talk #%d ====" % (
            talk["id"]
        ))
        self.msg(channel, "Please do not speak after voting until we've gotten "
            "our report.")
        self.current_votes = {}
        self.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        self.current_votes[user] = message

    def handle_report(self, channel):
        talk = self.talks[self.idx]
        yay, nay = 0, 0
        for vote in self.current_votes.itervalues():
            if vote.lower() in ("yay", "+1"):
                yay += 1
            elif vote.lower() in ("nay", "-1"):
                nay += 1
        self.msg(channel, "Talk Votes: %s yays, %s nays" % (yay, nay))
        if yay > nay:
            msg = "The yays have it"
        elif nay > yay:
            msg = "The nays have it"
        elif yay == nay:
            msg = "Mother of god. It's a tie"
        self.msg(channel, msg)

if __name__ == "__main__":
    main(PyConReviewBot)
