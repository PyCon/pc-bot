from __future__ import division
from .base import BaseMode
from ..models import Meeting, Group, TalkProposal, ThunderdomeVotes
from copy import copy
from datetime import datetime
from random import randint
import re


class Mode(BaseMode):
    """A mdoer for handling Thunderdome sessions."""

    def __init__(self, bot):
        super(Mode, self).__init__(bot)

        # variables that track the state of where we are right now
        self.meeting = None
        self.current_group = None
        self.next_group = None
        self.segment = None
        self.unaddressed = 0

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

        # get the group that should be up next
        try:
            self.next_group = Group.next_undecided_group()
        except IndexError:
            self.msg(channel, "There are no unreviewed groups remaining. Clearly, we shouldn't be here.")
            return
            
        # announce that the meeting has begun
        self.msg(channel, 'THIS. IS. THUNDERDOME!')
        self.msg(channel, "And meeting #{number} has {action}. Let's do this thing!".format(number=self.meeting.number, action=action))

        # ask folks for their names iff this is a new meeting
        if action == 'started':
            self.names()

    def chair_next(self, user, channel):
        """Move us to the next group."""

        # sanity check: we could be in the "post-report" stage; if we are
        #   then most likely the chair tried to move to the next group without
        #   addressing the one we were in -- refuse.
        if self.segment == 'post-report':
            self.msg(channel, 'We just had a report on the current group. I am cowardly refusing to move on to the next group until results from the current one have been addressed.')
            return

        # move us to the next group
        if self.next_group:
            self.current_group = self.next_group
            try:
                self.next_group = Group.next_undecided_group()
            except IndexError:
                self.next_group = None
        else:
            self.msg(channel, "There are no groups left for review. We're done!")
            return

        # print out the group we're now on, and the necessary information about it
        self.msg(channel, '=== Thunderdome for "{0}" begins now! ==='.format(self.current_group.name))
        for talk in group.talks:
            self.msg(channel, '#{id}: {title} ({url})'.format(
                id=talk.talk_id,
                title=talk.title,
                url=talk.review_url,
            ))
        self.msg(channel, ' * - * - * - * ')

        # now calculate the period of silent time to give to review talks
        # before shifting to the debate period
        silent_minutes = max(len(self.current_group) * 0.5, 2)
        self.msg(channel, 'You now have {time} to review these talks and collect your thoughts prior to debate. Please refrain from speaking until debate begins.'.format(
            time=self._minutes_to_text(silent_minutes),
        ))

        # now begin the timer and count down the silent period
        self.bot.set_timer(silent_minutes * 60, callback=self.chair_debate, callback_kwargs={
            'channel': channel,
            'user': user,
        })
        self.segment = 'silent_review'

        # set the state handler for the silent review period
        self.bot.state_handler = self.handler_silent_review

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

        # remove any state handler that is currently on the channel
        self.bot.state_handler = None
        
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

    def chair_report(self, user, channel):
        """Report the results of the vote that was just taken to the channel."""

        # turn off any state handlers
        self.state_handler = None

        # iterate over each talk in the group, and save its thunderdome
        # results to the database
        for talk in self.group.talks:
            supporters = sum(lambda vote: 1 if talk.talk_id in vote else 0, [i for i in self.current_votes.values()])
            total_voters = len(self.current_votes)

            # record the thunderdome votes for this talk
            talk.thunderdome_votes = ThunderdomeVotes(
                supporters=supporters,
                attendees=attendees,
            )
            talk.save()

        # now get me a sorted list of talks, sorted by the total
        # number of votes received (descending)
        sorted_talks = sorted(self.group.talks, key=lambda t: t.thunderdome_votes, reverse=True)

        # print out the talks to the channel, in order from
        # those voted well to those voted poorly
        for talk in sorted_talks:
            self.msg(channel, '{status}: #{talk_id}: {talk_title} ({supporters}/{attendees}, {percent:.2f}%)'.format(
                attendees=talk.thunderdome_votes.attendees,
                percent=talk.thunderdome_votes.percent,
                status=talk.thunderdome_votes.vote_result.upper(),
                supporters=talk.thunderdome_votes.supporters,
                talk_id=talk.talk_id,
                talk_title=talk.title,
            ))

        # declare that we are in the post-report segment
        self.segment = 'post-report'
        self.unaddressed = len(self.group)

    def chair_certify(self, user, channel):
        """Certify the results as just reported."""

        # sanity check: are we in the post-report segment?
        # if not, then this command doesn't make sense
        if self.segment != 'post-report':
            self.msg(channel, 'There are no results to certify.')

        # iterate over the talks and record the results of the voting
        accepted = []
        damaged = []
        rejected = []
        for talk in self.group.talks:
            result = talk.thunderdome_votes.vote_result
            if result == 'accepted':
                accepted.append(talk.talk_id)
            elif result == 'damaged':
                damaged.append(talk.talk_id)
            elif result == 'rejected':
                rejected.append(talk.talk_id)

        # actually perform the accepting, damaging, and rejecting
        # of the talks based on the votes
        chair_accept(user, channel, *accepted)
        chair_damage(user, channel, *damaged)
        chair_reject(user, channel, *rejected)

    def chair_accept(self, user, channel, *talk_ids):
        """Accept the talks provided as arguments."""
        self._make_decision(user, channel, 'accepted', *talk_ids)

    def chair_reject(self, user, channel, *talk_ids):
        """Reject the talks provided as arguments."""
        self._make_decision(user, channel, 'rejected', *talk_ids)

    def chair_damage(self, user, channel, *talk_ids):
        """Damage the talks provided as arguments."""
        self._make_decision(user, channel, 'damaged', *talk_ids)

    def _make_decision(self, user, channel, decision, *talk_ids):
        # sanity check: if there is an empty list of talk ids
        #   (which could happen, since `chair_certify` doesn't check
        #   for a non-zero list), then simply do nothing
        if not talk_ids:
            return

        # iterate over each provided talk id, get the talk from
        # the group's list of talks, and make the decision on the talk
        talks = []
        errors = []
        for talk_id in talk_ids:
            try:
                talk_id = int(talk_id)
                talk = self.group.talk_by_id(talk_id)
                talks.append(talk)
            except ValueError:
                errors.append(talk_id)

        # if there were errors on any of the talk ids given,
        # then error out now
        if errors:
            self.msg(channel, 'The following talk{plural} are not part of the active group and could not be {decision}: {badness}'.format(
                badness=', '.join([str(i) for i in errors]),
                decision=decision,
                plural='s' if len(errors) != 1 else '',
            ))
            self.msg(channel, 'As some of the input is in error, and because I am a very picky robot, I am cowardly refusing to do anything.')
            return

        # actually make the decision on the given talks
        for talk in talks:
            talk.thunderdome_result = decision
            talk.save()

        # report success to the channel
        self.msg(channel, '=== Talk{plural} {decision}: {talk_ids} ==='.format(
            decision=decision.capitalize(),
            plural='s' if len(talks) else '',
            talk_ids=', '.join([str(i.talk_id) for i in talks]),
        ))

        # if we don't have any more unaddressed talks, nix the segment and
        # mark the group as "done"
        if not self.group.undecided_talks:
            self.segment = None
            self.group.update(set__reviewed=True)

    def handler_silent_review(self, user, channel, message):
        """If a user speaks, tell them to be quiet, because it's the
        silent review period."""

        # tell the user to be quiet
        self.msg(channel, '{user}: We are currently in the silent review period. Please be quiet.'.format(user=user))

    def handler_user_votes(self, user, channel, message):
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
                examples.append(randint(1, 100))  # just in case
                
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
        self.group.update(set__reviewed=True)