import json
import os

from twisted.internet import reactor

from pycon_bot.base import main, BasePyConBot

CHAMPION_SECONDS = 2*60
DEBATE_SECONDS = 3*60

class PyConReviewBot(BasePyConBot):
    commands = frozenset(["start", "next", "debate", "vote", "report", "accept",
                          "reject", "poster", "rules", "pester", "voter",
                          "nonvoter"])
    jsonfile = os.path.join(os.path.dirname(__file__), 'talks.json')
    with open(jsonfile) as f:
        talks = json.load(f)

    def __init__(self):
        BasePyConBot.__init__(self)
        self.idx = -1
        self.timer = None
        self.nonvoters = set() 

    def save_state(self):
        with open(self.jsonfile, 'w') as fp:
            json.dump(self.talks, fp, indent=4)

    def say_time(self, channel):
        self.timer = None
        self.msg(channel, "==== Time has ended. ===")

    def set_timer(self, channel, seconds):
        self.clear_timer()
        self.timer = reactor.callLater(seconds, self.say_time, channel)

    def clear_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
            
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
        self.idx += 1
        self.state_handler = None
        try:
            talk = self.talks[self.idx]
        except IndexError:
            self.msg(channel, "Out of talks")
            return

        self.set_timer(channel, CHAMPION_SECONDS)
        self.msg(channel, str("==== Talk %d: %s - %s ====" % (
            talk["id"], talk["name"], self.talk_url(talk["id"])
        )))

        try:
            next = self.talks[self.idx+1]
        except IndexError:
            pass
        else:
            self.msg(channel, "(%s will be next)" % self.talk_url(next['id']))

        self.msg(channel, "If you are (a/the) champion for #%s, or "
            "willing to champion the it, please type a succinct argument for "
            "inclusion of this talk. (2 Minutes). Say 'done' when you are finished." % talk['id'])

    def handle_debate(self, channel):
        self.set_timer(channel, DEBATE_SECONDS)
        talk = self.talks[self.idx]
        self.msg(channel, "==== General Debate (3 minutes) for Talk: #%d ====" % (
            talk["id"]
        ))

    def handle_nonvoter(self, channel, user):
        if user == self.nickname:
            self.msg(channel, "I am above such mortal things.")
            return
        self.nonvoters.add(user)
        self.msg(channel, "Will no longer pester %s." % user)

    def handle_voter(self, channel, user):
        if user == self.nickname:
            self.msg(channel, "I am above such mortal things.")
            return
        try:
            self.nonvoters.remove(user)
        except KeyError:
            pass
        self.msg(channel, "Will now pester %s." % user)

    def handle_vote(self, channel):
        self.clear_timer()
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

    def handle_pester(self, channel):
        def names_callback(names):
            laggards = (set(names) - set(self.current_votes.keys()) -
                        self.nonvoters)
            laggards.remove(self.nickname)
            if laggards:
                self.msg(channel, "Didn't vote: %s." % (", ".join(laggards)))
            else:
                self.msg(channel, "Everyone voted.")
        self.names(channel).addCallback(names_callback)
        
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

        # Save the votes for posterity
        self.talks[self.idx]["votes"] = {"yay": yay, "nay": nay, "abstain": abstain}
        self.save_state()

    def handle_accept(self, channel):
        self._make_decision(channel, 'accepted', 'talk #{id} accepted, moves on to thunderdome.')

    def handle_reject(self, channel):
        self._make_decision(channel, 'rejected', 'talk #{id} rejected.')

    def handle_poster(self, channel):
        self._make_decision(channel, 'poster', 'talk #{id} rejected; suggest re-submission as poster.')

    def _make_decision(self, channel, decision, message):
        self.clear_timer()
        talk = self.talks[self.idx]
        self.msg(channel, "==== Chair decision: %s ====" % message.format(**talk))
        self.talks[self.idx]["decision"] = decision
        self.save_state()

    def handle_rules(self, channel):
        """Remind participants where they can find the rules."""
        self.msg(channel, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.msg(channel, "Notes about process: http://bit.ly/pyon-pc-format")

if __name__ == "__main__":
    main(PyConReviewBot)
