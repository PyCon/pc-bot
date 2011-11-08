import json
import os

from pycon_bot.base import main, BasePyConBot

class PyConReviewBot(BasePyConBot):
    commands = frozenset(["start", "next", "debate", "vote", "report", "accept", "reject", "final_report"])
    jsonfile = os.path.join(os.path.dirname(__file__), 'talks.json')
    with open(jsonfile) as f:
        talks = json.load(f)

    def __init__(self):
        BasePyConBot.__init__(self)
        self.idx = -1

    def handle_start(self, channel):
        for i, talk in enumerate(self.talks):
            if "decision" not in talk:
                break
        if i > 0:
            self.idx = i - 1
            self.msg(channel, "==== Skipped to just after #%d ===" % self.talks[i-1]["id"])
        else:
            self.msg(channel, "==== Ready (no talks to skip). ===")

    def handle_next(self, channel):
        # Dump the state if this isn't the first time we've next'd
        if self.idx > -1:
            with open(self.jsonfile, 'w') as fp:
                json.dump(self.talks, fp, indent=4)

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
        message = message.strip().lower()
        if message in ("y", "yes", "yay", "yea", "+1", ":)", ":-)"):
            self.current_votes[user] = "yay"
        elif message in ("n", "no", "nay", "-1", ":(", ":-("):
            self.current_votes[user] = "nay"
        elif message in ("a", "abs", "abstain", "0", ":/", ":-/"):
            self.current_votes[user] = "abstain"
        else:
            self.msg(channel, "%s: please vote yay, nay, or abstain." % user)

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
        self.msg(channel, "Talk Votes on #%s: %s yays, %s nays, %s abstentions" % (talk['id'], yay, nay, abstain))
        if yay > nay:
            msg = "The yays have it."
        elif nay > yay:
            msg = "The nays have it."
        elif yay == nay:
            msg = "It's a tie"
        self.msg(channel, msg)
        self.state_handler = None

    def handle_accept(self, channel):
        talk = self.talks[self.idx]
        self.msg(channel, "==== Chair decision: talk #%s accepted, moves on to thunderdome. ====" % talk['id'])
        self.talks[self.idx]["decision"] = "accepted"
        self.handle_next(channel)

    def handle_reject(self, channel):
        talk = self.talks[self.idx]
        self.msg(channel, "==== Chair decision: talk #%s rejected. ====" % talk['id'])
        self.talks[self.idx]["decision"] = "rejected"
        self.handle_next(channel)

if __name__ == "__main__":
    main(PyConReviewBot)
