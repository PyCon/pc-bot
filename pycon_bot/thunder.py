import re
import json
import os

from pycon_bot.base import main, BasePyConBot


REVIEW_SECONDS = 2 * 60     # Length of "quiet review" before debate.
DEBATE_SECONDS = 5 * 60     # Length of debate.
WINNING_THRESHOLD = 0.75    # Min % votes for a winning talk.
DAMAGED_THRESHOLD = 0.50    # Min % votes for a damaged talk.

"""
Talk group JSON format, for reference:

[
    {
        "name": "Name of this talk group III",
        "talks": {
            123: "Talk name",
            456: "Talk name",
            789: "Talk name",
        },
        "decision": {
            "accepted": [123],
            "damaged": [456],
            "rejeted": [789],
        }
        "votes": {
            "jacobkm": [123, 456, 789],
            ...
        }
    },
    ...
]
"""

class PyConThunderdomeBot(BasePyConBot):
    commands = frozenset(["next", "debate", "vote", "report", "pester", "start",
                          "in", "out", "dam", 'voter', 'nonvoter'])

    jsonfile = os.path.join(os.path.dirname(__file__), 'talk_groups.json')

    def __init__(self):
        self.load_talk_groups()
        BasePyConBot.__init__(self)
        self.idx = -1

    def load_talk_groups(self):
        with open(self.jsonfile) as f:
            self.talk_groups = json.load(f)

    @property
    def nonvoter_list(self):
        return ', '.join(self.nonvoters) if self.nonvoters else 'none'

    def save_state(self):
        with open(self.jsonfile, 'w') as fp:
            json.dump(self.talk_groups, fp, indent=4)

    def handle_start(self, channel):
        for i, group in enumerate(self.talk_groups):
            if "decision" not in group:
                break
        if i > 0:
            self.idx = i - 1
            next_name = self.talk_groups[i]['name']
            self.msg(channel, '=== Skipped {0} groups; next will be "{1}" ==='.format(i, next_name))
        else:
            self.msg(channel, "=== Ready (no groups to skip). ===")

    def handle_next(self, channel):
        self.idx += 1
        self.state_handler = None
        try:
            group = self.talk_groups[self.idx]
        except IndexError:
            self.msg(channel, "Out of talk groups")
            return
        self.msg(channel, '=== Thunderdome for "{name}" begins now! ==='.format(**group))
        for talk_id, talk_title in group["talks"].items():
            self.msg(channel, "#{id}: {title} - {url}".format(
                url=self.talk_url(talk_id), title=talk_title, id=talk_id))
        self.msg(channel, "You now have 2 minutes to review these talks and "
                          "collect your thoughts prior to debate. Please refrain "
                          "from speaking until debate begins.")
        self.set_timer(channel, REVIEW_SECONDS)

    def handle_debate(self, channel):
        group = self.talk_groups[self.idx]
        self.msg(channel, '=== General debate (5 minutes) for "{name}" ==='.format(**group))
        self.set_timer(channel, DEBATE_SECONDS)

    def handle_vote(self, channel):
        group = self.talk_groups[self.idx]
        talk_ids = str(", ".join(group['talks']))
        self.clear_timer()
        self.msg(channel, '=== Voting time! ===')
        self.msg(channel, 'Enter your vote in the form "%s", or "none".  '
            'You may vote for as many talks as you like, but please keep in '
            'mind the limited number of available slots.' % talk_ids
        )
        self.current_votes = {}
        self.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        group = self.talk_groups[self.idx]
        valid_talks = map(int, group['talks'].keys())
        votes = self.current_votes[user] = []

        if message.strip() in ('-', 'none', '[]', '{}'):
            return

        for vote in re.split(r'[, ]+', message):
            try:
                vote = int(vote)
            except ValueError:
                self.msg(channel, "{0}: '{1}' isn't an int; please enter a valid vote.".format(user, vote))
                return
            if vote not in valid_talks:
                valid_ids = ", ".join(map(str, valid_talks))
                self.msg(channel, "{0}: '{1}' isn't a talk ID under review. Valid IDs: {2}".format(user, vote, valid_ids))
                return
            votes.append(vote)

    def handle_report(self, channel):
        group = self.talk_groups[self.idx]
        talk_votes = dict.fromkeys(map(int, group["talks"].keys()), 0)
        num_voters = len(self.current_votes)
        for vote_list in self.current_votes.itervalues():
            for vote in vote_list:
                talk_votes[vote] += 1

        # sorted_votes ends up being a list of (talk_id, score), sorted by score.
        sorted_votes = list(sorted(talk_votes.items(), key=lambda t: t[1], reverse=True))
        winning_score = sorted_votes[0][1]
        for (talk_id, score) in sorted_votes:
            score_pct = float(score) / (num_voters if num_voters else 0)
            if score == winning_score and score_pct >= WINNING_THRESHOLD:
                status = "WINNER"
            elif score_pct >= DAMAGED_THRESHOLD:
                status = "DAMAGED"
            else:
                status = "OUT"
            self.msg(channel, "%s - #%s: %d votes (%d%%)" % (status, talk_id, score, score_pct*100))

        # Save for posterity
        group['votes'] = self.current_votes
        self.save_state()
        self.state_handler = None

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

    def handle_in(self, channel, *talks):
        self._make_decision(channel, 'accepted', talks)

    def handle_out(self, channel, *talks):
        self._make_decision(channel, 'rejected', talks)

    def handle_dam(self, channel, *talks):
        self._make_decision(channel, 'damaged', talks)

    def _make_decision(self, channel, decision, talks):
        group = self.talk_groups[self.idx]
        talk_ids = map(int, group['talks'])

        if 'decision' not in group:
            group['decision'] = {}

        # Validate decision
        for t in talks:
            try:
                t = int(t)
            except ValueError:
                self.msg(channel, "Oops, %s isn't an int; action ignored." % t)
                return
            if t not in talk_ids:
                self.msg(channel, "Oops, %s isn't under discussion; action ignored" % t)
                return

        self.msg(channel, '=== Chair decision: %s %s ===' % (decision, ', '.join(talks)))

        # Remove each talk in question from any existing decisions, if needed,
        # then add the talk to the apropriate decision group.
        talks = map(int, talks)
        for t in talks:
            for d in group['decision'].values():
                try:
                    d.remove(t)
                except ValueError:
                    pass
            group['decision'].setdefault(decision, []).append(t)

        self.save_state()

if __name__ == "__main__":
    main(PyConThunderdomeBot)
