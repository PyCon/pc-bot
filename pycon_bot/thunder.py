import os
import re
import json

from pycon_bot.base import main, BasePyConBot


class PyConThunderdomeBot(BasePyConBot):
    commands = frozenset(["next", "debate", "vote", "report"])
    vote_re = re.compile(r"[, ]")
    with open(os.path.join(os.path.dirname(__file__), 'talk_groups.json')) as f:
        talk_groups = json.load(f)

    def __init__(self):
        BasePyConBot.__init__(self)
        self.idx = -1

    def handle_next(self, channel):
        self.idx += 1
        self.state_handler = None
        try:
            group = self.talk_groups[self.idx]
        except IndexError:
            self.msg(channel, "Out of talk groups")
            return
        self.msg(channel, "Group: %s up next.  Talks: %s" % (
            str(group["name"]), ", ".join(map(str, group["talks"]))
        ))
        self.msg(channel, "The following group is on deck. You have 2 minutes "
                "to review the group and collect your thoughts prior to open "
                "debate (5 minutes). Once the debate is  completed, you will be "
                "asked to vote for the talk(s) you feel strongly should continue "
                "on to the final PyCon program.")
        for talk in group["talks"]:
            self.msg(channel, "Talk %s: %s" % (talk, self.talk_url(talk)))
        self.msg(channel, "We will now have %d minutes to review the talks "
            "before debate" % (group.get("discussion_time", 2))
        )

    def handle_debate(self, channel):
        group = self.talk_groups[self.idx]
        self.msg(channel, "The floor is now open for debate, we'll have %d "
            "minutes before voting" % (group.get("debate_time", 5))
        )

    def handle_vote(self, channel):
        self.msg(channel, 'Voting time!  Enter your vote in the form 1, 2, 3.  '
            'You may vote for as many talks as you feel should be accepted, '
            'however keep in mind we have a limited number of slots.'
        )
        self.current_votes = {}
        self.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        self.current_votes[user] = message

    def handle_report(self, channel):
        group = self.talk_groups[self.idx]
        talks = group["talks"]
        talk_votes = dict.fromkeys(talks, 0)
        for vote in self.current_votes.itervalues():
            votes = self.vote_re.split(vote)
            for vote in votes:
                try:
                    vote = int(vote)
                except ValueError:
                    pass
                else:
                    if vote in talk_votes:
                        talk_votes[vote] += 1
        self.msg(channel, "Talk Vote Scores: %s" % (
            ", ".join(
                "talk #%s: %s votes" % (k, v)
                for k, v in sorted(talk_votes.iteritems(), key=lambda (k, v): v, reverse=True)
            )
        ))

if __name__ == "__main__":
    main(PyConThunderdomeBot)
