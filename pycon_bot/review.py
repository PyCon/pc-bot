import json
import os

from pycon_bot.base import main, BasePyConBot

CHAMPION_SECONDS = 2*60
DEBATE_SECONDS = 3*60

class PyConReviewBot(BasePyConBot):
    commands = frozenset(["start", "next", "debate", "vote", "report", "accept",
                          "reject", "poster", "rules", "pester", "voter",
                          "nonvoter", "table", "goto"])
    jsonfile = os.path.join(os.path.dirname(__file__), 'talks.json')
    with open(jsonfile) as f:
        talks = json.load(f)

    def __init__(self):
        BasePyConBot.__init__(self)
        self.idx = -1

    def save_state(self):
        with open(self.jsonfile, 'w') as fp:
            json.dump(self.talks, fp, indent=4)

    def handle_start(self, channel):
        for i, talk in enumerate(self.talks):
            if "decision" not in talk:
                break
        if i > 0:
            self.idx = i - 1
            next_id = self.talks[i]['id']
            self.msg(channel, "=== Skipped %s talks; next will be #%d ===" % (i, next_id))
        else:
            self.msg(channel, "=== Ready (no talks to skip). ===")

    def handle_goto(self, channel, talk_id):
        try:
            talk_id = int(talk_id)
        except ValueError:
            self.msg(channel, "Erm, %s doesn't seem to be a talk ID." % talk_id)
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
                self.msg(channel, msg.format(**next_talk))
                break
        else:
            self.msg(channel, "Uh oh, I couldn't find talk ID %s." % talk_id)

    def handle_next(self, channel):
        self.idx += 1
        self.state_handler = None
        try:
            talk = self.talks[self.idx]
        except IndexError:
            self.msg(channel, "Out of talks")
            return

        self.set_timer(channel, CHAMPION_SECONDS)
        self.msg(channel, str("=== Talk %d: %s - %s ===" % (
            talk["id"], talk["name"], self.talk_url(talk["id"])
        )))

        try:
            next = self.talks[self.idx+1]
        except IndexError:
            pass
        else:
            self.msg(channel, "(%s will be next)" % self.talk_url(next['id']))

        self.msg(channel, "If you are (a/the) champion for #%s, or "
            "willing to champion the it, please say 'me'. Then, please type a succinct argument for "
            "inclusion of this talk. (2 Minutes). Say 'done' when you are finished." % talk['id'])

    def handle_debate(self, channel):
        self.set_timer(channel, DEBATE_SECONDS)
        talk = self.talks[self.idx]
        self.msg(channel, "=== General Debate (3 minutes) for Talk: #%d ===" % (
            talk["id"]
        ))

    def handle_vote(self, channel):
        self.clear_timer()
        self.current_votes = {}
        talk = self.talks[self.idx]
        self.msg(channel, "=== Voting time! yay/nay votes for talk #%d ===" % (
            talk["id"]
        ))
        self.msg(channel, "Please do not speak after voting until we've gotten "
            "our report.")
        self.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        message = message.strip().lower()
        if message in ("y", "yes", "yay", "yea", "+1"):
            self.current_votes[user] = "yay"
        elif message in ("n", "no", "nay", "-1"):
            self.current_votes[user] = "nay"
        elif message in ("a", "abs", "abstain", "0"):
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
        self.msg(channel, "=== Talk Votes on #%s: %s yays, %s nays, %s abstentions ===" % (talk['id'], yay, nay, abstain))
        if yay > nay:
            msg = "The yays have it."
        elif nay > yay:
            msg = "The nays have it."
        elif yay == nay:
            msg = "It's a tie: http://i.imgur.com/Cw3lg.jpg"
        self.msg(channel, msg)
        self.state_handler = None

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
        self.clear_timer()
        talk = self.talks[self.idx]
        self.msg(channel, "=== Chair decision: %s ===" % message.format(**talk))
        self.talks[self.idx]["decision"] = decision
        self.save_state()

    def handle_rules(self, channel):
        """Remind participants where they can find the rules."""
        self.msg(channel, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.msg(channel, "Notes about process: http://bit.ly/pycon-pc-format")

if __name__ == "__main__":
    main(PyConReviewBot)
