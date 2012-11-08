from .base import BaseMode
from ..models import Meeting, Group, TalkProposal, ThunderdomeVotes
from copy import copy
from datetime import datetime
from random import randInt
import re


WINNING_THRESHOLD = 0.75    # Min % votes for a winning talk.
DAMAGED_THRESHOLD = 0.50    # Min % votes for a damaged talk.


class Mode(BaseMode):
    """A mdoer for handling Thunderdome sessions."""
    
    def __init__(self):
        # variables that track the state of where we are right now
        self.meeting = None
        self.current_group = None
        self.next_group = None
        self.segment = None

    def chair_start(self, user, channel, meeting_num=None):
        """Begin a meeting. If a meeting number is given, then
        resume that meeting."""
        
        # pull up the meeting itself, or if no meeting number was specified,
        # then create a new meeting record
        if meeting_num:
            try:
                self.meeting = Meeting.objects.get(number=int(meeting_num))
                action = 'resumed'
            except Meeting.DoesNotExist:
                self.msg(channel, 'There is no meeting in the system with that number.')
                return
        else:
            self.meeting = Meeting.objects.create(start=datetime.now())
            action = 'started'
            
        # announce that the meeting has begun
        self.msg(channel, 'THIS. IS. THUNDERDOME!')
        self.msg(channel, "And meeting #{number} has {action}. Let's do this thing!".format(number=self.meeting.number, action=action))
        
        # ask folks for their names iff this is a new meeting
        if action == 'started':
            self.names()

    def chair_next(self, user, channel):
        """Move us to the next group."""
        
        # FIXME: come back to this
        pass
        
        # 
        # self.idx += 1
        # self.state_handler = None
        # try:
        #     group = self.talk_groups[self.idx]
        # except IndexError:
        #     self.msg(channel, "Out of talk groups")
        #     return
        # self.msg(channel, '=== Thunderdome for "{name}" begins now! ==='.format(**group))
        # for talk_id, talk_title in group["talks"].items():
        #     self.msg(channel, "#{id}: {title} - {url}".format(
        #         url=self.talk_url(talk_id), title=talk_title.encode('ascii', 'ignore'), id=talk_id))
        # self.msg(channel, "You now have {minutes} minutes ".format(minutes=minutes) +
        #                   "to review these talks and collect your thoughts prior to "
        #                   "debate. Please refrain from speaking until debate begins.")
        # self.set_timer(channel, minutes * 60)

    def chair_debate(self, user, channel):
        """Shift the channel into debate mode. The time allotted for debate
        should scale with the number of talks in the group."""
        
        # determine the debate time; it should be a function of the number
        # of talks in the group
        debate_minutes = len(self.current_group) * 1.5
            
        # announce that we're in debate now
        self.msg(channel, '=== General Debate ({time}) for "{name}" ==='.format(
            name=self.current_group.name,
            time=self._minutes_to_text(debate_minutes),
        ))
        
        # set the timer and status
        self.bot.set_timer(debate_minutes * 60)
        self.segment = 'debate'

    def chair_vote(self, user, channel):
        """Shift the channel into voting mode. Accept votes in
        any reasonable / parsable format, and collect data for the
        final report."""
        
        # clear any existing timer on the bot
        self.bot.clear_timer()
        
        # announce that we're shifting into voting
        self.msg(channel, '=== Voting time! ===')
        self.msg(channel, 'Enter your vote in any form I understand (details: `/msg {nick} voting`). You may vote for as many talks as you like, but remember that we are limited to roughly 110 slots.'.format(
            nick=self.driver.nickname,
        ))
        
        # wipe out the current list of votes (from the last group)
        # so that I can store the new list
        self.current_votes = {}
        self.state_handler = self.handler_user_votes

    def handler_user_votes(self, channel, user, message):
        """Record a user's vote."""
        
        # parse out the vote into individual tokens, separated by commas,
        # spaces, or both -- make this into a purely comma-separated vote
        message = re.sub(r'/[\s]+/', ' ', message)
        message = message.replace(', ', ',').replace(' ', ',')
        vote = message.split(',')
        
        # copy the user's former vote, if any
        # we will modify `answer` instead of writing his vote directly to self.current_votes,
        #   so that if there's an error, we don't save only half the vote somehow
        answer = set()
        if user in self.current_votes:
            answer = self.current_votes[user]
            
        # ensure that every sub-piece of this vote is individually valid
        # I currently understand:
        #   - integers on the talk_id list, optionally prefixed with [+-]
        #   - string "all"
        #   - string "none"
        invalid_pieces = []
        invalid_talk_ids = []
        for piece in vote:
            # I understand integers if they are on the talk_id list,
            # including if they are prefixed with [+-]
            if re.match(r'^[+-]?[\d]+$', piece):
                talk_id = int(piece.replace('-', '').replace('+', ''))
                if talk_id not in self.group.talk_ids:
                    invalid_talk_ids.append(talk_id)
                continue
            
            # I understand "all" and "none"
            if piece == 'all' or piece == 'none':
                continue
                
            # I have no idea what this is
            invalid_pieces.append(peice)
            
        # sanity check: if I have any invalid tokens or talk_ids that aren't
        #   in the talk_id list, fail out now
        if len(invalid_pieces):
            self.msg(channel, '{user}: I do not understand {tokens}.'.format(
                user=user,
                tokens=self._english_list(['"{0}"'.format(i) for i in invalid_pieces], conjunction='or'),
            ))
            return
        if len(invalid_talk_ids):
            self.msg(channel, '{user}: You voted for {talks}, which {to_be_verb} not part of this group. Your vote has not been recorded.'.format(
                talks=self._english_list(['#{0}'.format(i) for i in invalid_talk_ids]),
                to_be_verb='is' if len(invalid_talk_ids) == 1 else 'are',
                user=user,
            ))
        
        # the simple case is that this is a "plain" vote -- a list of
        #   integers with no specials (e.g. "none") and no modifiers (+/-)
        # this is straightforward: the vote becomes, in its entirety, the
        #   user's vote, and anything previously recorded for the user is
        #   simply dropped
        if reduce(lambda x, y: x & y, [re.match(r'^[\d]+$', i) for i in vote]):
            self.current_votes[user] = set([int(i) for i in vote])
            return
            
        # sanity check: non-plain votes should not have *any* plain elements;
        #   therefore, if there are any, we should error out now
        if reduce(lambda x, y: x | y, [re.match(r'^[\d]+$', i) for i in vote]):
            # use examples from the actual group to minimize confusion
            examples = list(self.group.talk_ids)[0:2]
            while len(examples) < 2:
                examples.append(randInt(1, 100))  # just in case
                
            # spit out the error -- since this is long, send as much of it as possible to PMs
            self.msg(channel, '{0}: I cannot process this vote. See your private messages for details.'.format(user))
            self.msg(user, 'I cannot process this vote. I understand two voting paradigms:')
            self.msg(user, '1. An absolute list of talks (e.g. `{0}, {1}`)'.format(*examples))
            self.msg(user, '2. Two special keywords ("all", "none"), and the addition/removal of talks from those keywords or from your prior vote (e.g. `all -{1}` or `+{0}`).'.format(*examples))
            self.msg(user, 'Your vote mixes these two paradigms together, and I don\'t know how to process that, so I am cowardly giving up.')
            return
            
        # sanity check: exclusive modifier votes only make sense if either
        #   1. "all" or "none" is included in the vote -or-
        #   2. the user has voted already
        # if neither of these cases obtains, error out
        if vote[0] not in ('all', 'none') and user not in self.current_votes:
            self.msg(channel, '{0}: You can only modify your prior vote if you have already voted; you have not.'.format(user))
            return

        # sanity check (last one, for now): "all" or "none" only make sense at the
        #   *beginning* of a vote; don't take them at the end
        if 'all' in vote[1:] or 'none' in vote[1:]:
            self.msg(channel, '{0}: If using "all" or "none" in a complex vote, please use them exclusively at the beginning.'.format(user))
            return
            
        # okay, this is a valid vote with modifiers; parse it from left to right
        # and process each of the modifiers
        for piece in vote:
            # first, is this "all" or "none"? these are the simplest
            # cases -- either a full set or no set
            if piece == 'all':
                answer = copy(self.group.talk_ids)
            if piece == 'none':
                answer = set()
                
            # add or remove votes with operators from the set
            if piece.startswith('+'):
                talk_id = int(piece[1:])
                answer.add(talk_id)
            if piece.startswith('-'):
                talk_id = int(piece[1:])
                answer.remove(talk_id)
                
        # okay, we processed a valid vote without error; set it
        self.current_votes[user] = answer

    def chair_report(self, user, channel):
        """Report the results of the vote that was just taken to the channel."""
        
        # iterate over each talk in the group, and save its thunderdome
        # results to the database
        for talk in self.group.talks:
            supporters = sum(lambda vote: 1 if talk.talk_id in vote else 0, [i for i in self.current_votes.values()])
            total_voters = len(self.current_votes)
            
            # record the thunderdome votes for this talk
            talk.thunderdome_votes = ThunderdomeVotes(
                supporters=supporters,
                total_voters=total_voters,
            )
            talk.save()
            
        # now get me a sorted list of talks, sorted by the total
        # number of votes received (descending)
        
        
        
        
        
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