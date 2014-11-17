from __future__ import division
from .base import BaseMode
from ..models import ThunderdomeGroup, ThunderdomeVotes
from copy import copy
from datetime import datetime
from random import randint
from twisted.internet import reactor
import re


class Mode(BaseMode):
    """A mdoer for handling Thunderdome sessions."""

    def __init__(self, bot):
        super(Mode, self).__init__(bot)

        # variables that track the state of where we are right now
        self.groups = ()
        self.meeting = None
        self.segment = None
        self.unaddressed = 0

    @property
    def current_group(self):
        return self.groups[0]

    @property
    def next_group(self):
        return self.groups[1]

    def handler_voting_soon(self, user, channel, message):
        """Handle the case where we're counting down to a premature vote.
        If anyone says "wait", call off the countdown.
        """
        # If the message is (or even just begins with) "wait", that's our
        # signal to hold off.
        message = message.strip().lower()
        if message.startswith('wait'):
            self._delayed_vote_timer.cancel()
            self._delayed_vote_timer = None

            # Print that we're holding off.
            self.msg(channel, 'Request to wait acknowledged. Holding off.')

    def chair_start(self, user, channel):
        """Begin a meeting. If a meeting number is given, then
        resume that meeting. Initializes the next group.
        """
        self.groups = ThunderdomeGroup.objects.filter(undecided=True)

        # Sanity check: Are there any groups?
        if not self.groups:
            self.msg(channel, "There are no unreviewed groups remaining. "
                              "Clearly, we shouldn't be here.")
            return

        # Announce that the meeting has begun.
        self.msg(channel, 'THIS. IS. THUNDERDOME!')
        self.msg(channel, "And the meeting has started. Let's do this thing!")

        # Get some statistics.
        self.msg(channel, '* - * - * - * - *')
        self.msg(channel, 'First, some statistics thus far:')
        self.chair_progress(user, channel)
        self.msg(channel, '* - * - * - * - *')

        # Tell the mode that the meting has begun.
        self._in_meeting = True
        self.segment = 'intro'

        # Ask folks for their names iff this is a new meeting.
        self.names(channel)

    def chair_next(self, user, channel):
        """Move us to the next group."""

        # Sanity check: Ensure we've started the meeting.
        if self.segment is None:
            self.msg(channel, 'No, silly. Run `,start` first.')
            return

        # Sanity check: we could be in the "post-report" stage; if we are
        # then most likely the chair tried to move to the next group without
        # addressing the one we were in -- refuse.
        if self.segment == 'post-report':
            self.msg(channel, 'We just had a report on the current group. '
                              'I am cowardly refusing to move on to the next '
                              'group until results from the current one have '
                              'been addressed.')
            return

        # Are there any groups remaining?
        if len(self.groups) <= 1:
            self.msg(channel, "There are no groups left for review. "
                              "We're done!")
            return

        # Kill any current votes.
        self.current_votes = {}

        # Move us to the next group.
        # Note: There's one exception to this, which is if we're in the
        # "intro" segment, since the initial group wouldn't've been done yet.
        if self.segment != 'intro':
            self.groups = self.groups[1:]

        # Print out the group we're now on, and the necessary information
        # about it.
        self.msg(channel, '=== Thunderdome for "{0}" begins now! ==='.format(
            self.current_group.label,
        ))
        self._report_on_group(channel, self.current_group)
        self.msg(channel, ' * - * - * - * ')

        # Calculate the period of silent time to give to review talks
        # before shifting to the debate period.
        silent_minutes = min(len(self.current_group.talk_ids) * 0.25, 1)
        self.msg(channel, 'You now have {time} to review these talks and '
                          'collect your thoughts prior to debate. Please '
                          'refrain from speaking until debate begins.'.format(
                                time=self._minutes_to_text(silent_minutes),
                          ))

        # Now begin the timer and count down the silent period.
        self.bot.set_timer(channel, silent_minutes * 60,
            callback=self.chair_debate,
            callback_kwargs={
                'channel': channel,
                'user': user,
            },
        )
        self.segment = 'silent_review'

        # Set the state handler for the silent review period.
        self.bot.state_handler = self.handler_silent_review

    def chair_debate(self, user, channel):
        """Shift the channel into debate mode. The time allotted for debate
        should scale with the number of talks in the group."""

        # Determine the debate time; it should be a function of the number
        # of talks in the group.
        debate_minutes = len(self.current_group.talk_ids) * 1.5

        # Announce that we're in debate now.
        self.msg(channel, '=== General Debate ({time}) for "{name}" ==='.format(
            name=self.current_group.label,
            time=self._minutes_to_text(debate_minutes),
        ))

        # remove any state handler that is currently on the channel
        self.bot.state_handler = None

        # set the timer and status
        self.bot.set_timer(channel, debate_minutes * 60)
        self.segment = 'debate'

    def chair_vote(self, user, channel, defer=None):
        """Call for a vote.

        If an argument (`defer`) is specified, wait `defer` seconds before
        calling the vote, and if anyone in the channel says "wait", then 
        cancel the countdown.
        """
        # The basic idea here is that if any defer is called that
        # is >= some number, there should be a second announcement saying
        # that time is almost up.
        #
        # So, if voting will commence in 15 seconds, give the initial
        # warning and then a second warning just beforehand.
        #
        # The constants are just here so that these boundaries can be
        # modified in one place, but I'm pretty sure 10 and 5 are where I
        # want them.
        _DOUBLE_MESSAGE_BOUNDARY = 10
        _DOUBLE_MESSAGE_SECOND_CALL = 5

        # Sanity check: If there is no current talk, then a vote call
        # makes no sense.
        if not self.current_group:
            self.msg(channel, 'There is no current group to vote on. '
                              'Aborting.')
            return

        # Handle a deferred vote; this comes up when we want to give
        # some warning before voting actually begins, to allow someone
        # to have us hold off.
        if defer:
            defer = int(defer)

            # First, delay the timer currently on the bot by the amount of
            # the deferral; do this in lieu of clearing the timer because
            # if we are asked to wait; we still need it
            if self.bot.timer and self.bot.timer.active():
                if defer >= _DOUBLE_MESSAGE_BOUNDARY:
                    self.bot.timer.delay(defer)
                else:
                    self.bot.timer.delay(defer - _DOUBLE_MESSAGE_SECOND_CALL)
            else:
                # There is no timer; this is an odd case, but I don't know
                # how to automate it; the chair will have to handle this as
                # he/she sees fit.
                self.msg(user, ' '.join((
                    'Note: You called a deferred vote called with no',
                    'active timer on the channel. I am doing as I am',
                    'told, but am not sure what you are intending. FYI.',
                )))

            # Now set up our own timer for the vote delay; note that
            # we need to *not* use `self.bot.set_timer` because it will
            # wipe out the "main" timer that we need back.
            # Therefore; set this one off to the side.
            if defer >= _DOUBLE_MESSAGE_BOUNDARY:
                self._delayed_vote_timer = reactor.callLater(
                    defer - _DOUBLE_MESSAGE_SECOND_CALL,
                    self.chair_vote, user, channel,
                    defer=_DOUBLE_MESSAGE_SECOND_CALL,
                )
            else:
                self._delayed_vote_timer = reactor.callLater(
                    defer, self.chair_vote, user, channel,
                )
            self.msg(channel, ' '.join((
                'Voting in {seconds} seconds unless someone objects',
                '(type "wait").',
            )).format(seconds=defer))

            # Set the state handler so the bot actually listens to wait calls.
            self.bot.state_handler = self.handler_voting_soon

        else:
            # Clear any timer that may exist now.
            self.bot.clear_timer()

            # Clear out the votes.
            self.current_votes = {}

            # Tell the channel and bot that we're switching segments.
            self.msg(channel, '=== Voting time! ===')
            self.msg(channel, 'Enter your vote in any form I understand '
                              '(details: `/msg {nick} voting`). You may vote '
                              'for as many talks as you like, but remember that'
                              ' we are limited to 95 slots.'.format(
                                    nick=self.bot.nickname,
                              ))
            self.segment = 'voting'

            # set the state handler
            self.bot.state_handler = self.handler_user_votes

    def chair_extend(self, user, channel, extend_time=1):
        """Extend the time on the clock. In reality, this does nothing
        but set another clock, but it's a useful management tool
        within meetings.
        """
        # If there's an active timer, just delay it.
        if self.bot.timer and self.bot.timer.active():
            self.bot.timer.delay(float(extend_time) * 60)
        else:
            # Clear the timer and set a new one.
            self.bot.clear_timer()
            self.bot.set_timer(channel, float(extend_time) * 60)

        # Now report the extension
        self.msg(channel, '=== Extending time by %s. Please continue. ===' %
                          self._minutes_to_text(extend_time))

    def chair_report(self, user, channel):
        """Report the results of the vote that was just taken to the
        channel.
        """
        # Sanity check: Are there votes to report?
        if not getattr(self, 'current_votes', None):
            self.msg(channel, "No votes to report. This isn't the chair "
                              "command you're looking for.")
            return

        # Turn off any state handlers.
        self.bot.state_handler = None

        # Iterate over each talk in the group, and save its thunderdome
        # results to the database.
        for talk in self.current_group.talks:
            supporters = sum([(1 if talk.id in vote else 0)
                              for vote in self.current_votes.values()])
            total_voters = len(self.current_votes)

            # Record the thunderdome votes for this talk.
            talk.set_thunderdome_votes(supporters, total_voters)

        # Now get me a sorted list of talks, sorted by the total
        # number of votes received (descending).
        sorted_talks = sorted(self.current_group.talks,
                              key=lambda t: t.thunderdome_votes.percent,
                              reverse=True)

        # Print out the talks to the channel, in order from
        # those voted well to those voted poorly.
        for talk in sorted_talks:
            self.msg(channel, '{status}: #{talk_id}: {talk_title} '
                              '({supporters}/{attendees}, '
                              '{percent:.2f}%%)'.format(
                attendees=talk.thunderdome_votes.total_voters,
                percent=talk.thunderdome_votes.percent,
                status=talk.thunderdome_votes.vote_result.upper(),
                supporters=talk.thunderdome_votes.supporters,
                talk_id=talk.id,
                talk_title=talk.title,
            )) 

        # Declare that we are in the post-report segment.
        self.segment = 'post-report'
        self.unaddressed = len(self.current_group.talk_ids)

    def chair_certify(self, user, channel):
        """Certify the results as just reported."""

        # Sanity check: Are we in the post-report segment?
        # if not, then this command doesn't make sense.
        if self.segment != 'post-report':
            self.msg(channel, 'There are no results to certify.')

        # Iterate over the talks and record the results of the voting.
        accepted = []
        damaged = []
        rejected = []
        for talk in self.current_group.talks:
            # Sanity check: If this talk already has a decision,
            # the certify command should not trump it.
            if talk.id not in self.current_group.undecided_talks:
                continue

            # Record the decision locally.
            result = talk.thunderdome_votes.vote_result
            if result == 'accepted':
                accepted.append(talk.id)
            elif result == 'damaged':
                damaged.append(talk.id)
            elif result == 'rejected':
                rejected.append(talk.id)

        # Actually perform the accepting, damaging, and rejecting
        # of the talks based on the votes.
        self.chair_accept(user, channel, *accepted)
        self.chair_damage(user, channel, *damaged)
        self.chair_reject(user, channel, *rejected)

        # Send the decisions to the PyCon server.
        self.current_group.certify()

        # Denote that certification is done.
        self.segment = 'post-certify'

    def chair_accept(self, user, channel, *talk_ids):
        """Accept the talks provided as arguments."""
        self._make_decision(user, channel, 'undecided', *talk_ids)

    def chair_reject(self, user, channel, *talk_ids):
        """Reject the talks provided as arguments."""
        self._make_decision(user, channel, 'rejected', *talk_ids)

    def chair_damage(self, user, channel, *talk_ids):
        """Damage the talks provided as arguments."""
        self._make_decision(user, channel, 'damaged', *talk_ids)

    def chair_suggest(self, user, channel, talk_alternative, *talk_ids):
        """Set the given talk alternative (poster, open space, etc.) on
        the given talk. This does *not* change its main status, since it
        may be either damaged or rejected."""

        # Make sure that each talk ID I was given is a damaged
        # or rejected talk in this group; if not, complain loudly and quit.
        not_found = []
        wrong_status = []
        talk_objects = []
        for talk_id in talk_ids:
            try:
                talk = self.current_group.talk_by_id(talk_id)
                if talk.status not in ('damaged', 'rejected'):
                    wrong_status.append(talk_id)
                else:
                    talk_objects.append(talk)
            except ValueError:
                not_found.append(talk_id)

        # Print out any errata.
        if len(not_found):
            self.msg(channel, 'The following talk{plural} is not part of '
                              'the current group: {missing}.'.format(
                missing=', '.join([str(i) for i in not_found]),
                plural='s' if len(not_found) != 1 else '',
            ))
        if len(wrong_status):
            self.msg(channel, 'The following talk{plural} has a status that '
                              'is not "damaged" or "rejected": {wrongstatus}. '
                              'Please damage or reject {pnoun} before giving '
                              '{pnoun} a suggested talk alternative.'.format(
                plural='s' if len(wrong_status) != 1 else '',
                pnoun='it' if len(wrong_status) == 1 else 'them',
                wrongstatus=', '.join([str(i) for i in wrong_status]),
            ))

        # If there were any errata, hard stop.
        if len(not_found) or len(wrong_status):
            self.msg(channel, 'Since I cannot process all of the given input, '
                              'I am cowardly refusing to do anything.  Please '
                              'try again.')
            return

        # Sanity check: is this an alternative I understand?
        if talk_alternative not in [i[0] for i in
                                    TalkProposal.TALK_ALTERNATIVES]:
            self.msg(channel, 'I do not recognize the talk alternative "{0}". '
                              'Sorry.'.format(talk_alternative))
            return

        # Okay, apply the alternative status to every requested talk.
        for talk in talk_objects:
            talk.alternative = talk_alternative
            talk.save()
        self.msg(channel, '== Suggested {alternative} for '
                          'talk{plural} {talks}. ==='.format(
            alternative=talk_alternative.replace('_', ' '),
            plural='s' if len(talk_objects) != 1 else '',
            talks=', '.join(talk_ids)
        ))

    def _make_decision(self, user, channel, decision, *talk_ids):
        # Sanity check: if there is an empty list of talk ids
        # (which could happen, since `chair_certify` doesn't check
        # for a non-zero list), then simply do nothing.
        if not talk_ids:
            return

        # Iterate over each provided talk id, get the talk from
        # the group's list of talks, and make the decision on the talk
        errors = []
        for talk_id in talk_ids:
            if int(talk_id) not in self.current_group.talk_ids:
                errors.append(talk_id)

        # If there were errors on any of the talk ids given,
        # then error out now.
        if errors:
            self.msg(channel, 'The following talk{plural} are not part of the '
                              'active group and could not be {decision}: '
                              '{badness}'.format(
                badness=', '.join([str(i) for i in errors]),
                decision=decision,
                plural='s' if len(errors) != 1 else '',
            ))
            self.msg(channel, 'As some of the input is in error, and '
                              'because I am a very picky robot, I am cowardly '
                              'refusing to do anything.')
            return

        # Actually make the decision on the given talks.
        for talk_id in talk_ids:
            self.current_group.decide_talk(int(talk_id), decision)

        # Report success to the channel.
        self.msg(channel, '=== Talk{plural} {decision}: {talk_ids} ==='.format(
            decision=decision.replace('undecided', 'accepted').capitalize(),
            plural='s' if len(talk_ids) else '',
            talk_ids=', '.join([str(i) for i in talk_ids]),
        ))

    def _report_on_group(self, dest_output, group):
        """Report on the contents of a group to the given user or channel."""
        for talk in group.talks:
            self.msg(dest_output, '#{id}: {title} ({url})'.format(
                id=talk.id,
                title=talk.title,
                url=talk.review_url,
            ))

    def chair_end(self, user, channel):
        """Conclude the meeting."""

        self.msg(channel, "=== Th-th-th-that's all folks! ===")

        # Remove any state handler that may be present.
        self.bot.clear_timer()
        self.bot.state_handler = None
        self._in_meeting = False

        # Show the progress thus far.
        self.chair_progress(user, channel)

        # Pull out of this mode; ,end implies a reversion to skeleton mode.
        self.chair_mode(user, channel, 'none', _silent=True)

    def chair_progress(self, user, channel):
        """Report on the total progress of thunderdome."""

        # Get a full list of thunderdome groups.
        # Iterate over it to determine how many have been decided.
        td_groups = ThunderdomeGroup.objects.all()
        decided = 0
        total = len(td_groups)

        # Sanity check: Dividing by zero is bad.
        if not total:
            return

        # Get the total number of decided talks.
        for group in td_groups:
            if group.decided:
                decided += 1

        # Print how many groups have been decided thus far.
        self.msg(channel, '{decided} of {total} groups decided. '
                          '({percent:.2f}%%)'.format(
            decided=decided,
            percent=decided * 100 / total,
            total=total,
        ))

        # Iterate over the talks in each group and determine how many
        # were accepted.
        accepted = 0
        decided = 0
        total = 0
        for group in td_groups:
            total += len(group.talks)

            # If this group has been decided, it follows that every talk
            # within this group has also been decided.
            if group.decided:
                decided += len(group.talks)

            # For every accepted talk within this group, increment the
            # accepted counter.
            #
            # Note: Due to the fact that marking a talk accepted makes
            # this immediately public, we use "undecided" instead.
            for talk in group.talks:
                if talk.status == 'undecided':
                    accepted += 1

        # Sanity check: Dividing by zero is still bad.
        if not total:
            return

        # Report on the total number of decided talks.
        self.msg(channel, '{decided} of {total} talks decided. '
                          '({percent:.2f}%%)'.format(
            decided=decided,
            percent=decided * 100 / total,
            total=total,
        ))

        # Sanity check: Dividing by zero...yup, just checked, still bad.
        if not decided:
            return

        # Report on the total number of accepted talks.
        self.msg(channel, '{accepted} talks accepted thus far '
                          '(rate: {percent:.2f}%%).'.format(
            accepted=accepted,
            percent=accepted * 100 / decided,
        ))

        # Display a warning if our acceptance rate gets too high.
        if (accepted * 100 / decided) > 32.5:
            self.msg(channel, 'As a reminder, we have only 90 talk slots, and '
                              'therefore must have an acceptance rate no '
                              'higher than 30%%.')

    def private_current(self, user):
        """Spit out information about the current group."""

        # Sanity check: is there a current group?
        if not self.current_group:
            self.msg(user, 'There is no current group being discussed.')
            return

        # Report on the current group.
        self.msg(user, 'The current group on the plate is: {0}'.format(
                       self.current_group.label,
        ))
        self._report_on_group(user, self.current_group)

    def private_next(self, user):
        """Spit out information about the next group."""

        # sanity check: is there an upcoming group?
        if not self.next_group:
            self.msg(user, 'There is no next group to be discussed.')
            return

        # report on the next group
        self.msg(user, 'The next group on the plate is: {0}'.format(
                 self.next_group.name,
        ))
        self._report_on_group(user, self.next_group)

    def private_voting(self, user):
        """Explain how voting is done."""

        # if there is a current group, use examples from that group
        examples = [92, 418]
        if self.current_group:
            examples = list(self.current_group.talk_ids)[0:1]

        # explain what voting paradigms I understand
        self.msg(user, 'I understand two voting paradigms:')
        self.msg(user, '1. An absolute list of talks (e.g. `{0}, '
                       '{1}`)'.format(*examples))
        self.msg(user, '2. Two special keywords ("all", "none"), and the '
                       'addition/removal of talks from those keywords or from '
                       'your prior vote (e.g. `all -{1}` or '
                       '`+{0}`).'.format(*examples))

    def handler_silent_review(self, user, channel, message):
        """If a user speaks, tell them to be quiet, because it's the
        silent review period."""

        # tell the user to be quiet
        self.msg(channel, '{user}: We are currently in the silent review '
                          'period. Please be quiet.'.format(user=user))

    def handler_user_votes(self, user, channel, message):
        """Record a user's vote."""

        # parse out the vote into individual tokens, separated by commas,
        # spaces, or both -- make this into a purely comma-separated vote
        message = re.sub(r'/[\s]+/', ' ', message)
        message = message.replace(', ', ',').replace(' ', ',')
        vote = message.split(',')

        # Copy the user's former vote, if any.
        # We will modify `answer` instead of writing his vote directly
        # to `self.current_votes`, so that if there's an error, we don't save
        # only half the vote somehow.
        answer = set()
        if user in self.current_votes:
            answer = self.current_votes[user]

        # Ensure that every sub-piece of this vote is individually valid
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
                if talk_id not in self.current_group.talk_ids:
                    invalid_talk_ids.append(talk_id)
                continue

            # I understand "all" and "none"
            if piece == 'all' or piece == 'none':
                continue

            # I have no idea what this is
            invalid_pieces.append(piece)

        # Sanity check: if I have any invalid tokens or talk_ids that aren't
        # in the talk_id list, fail out now.
        if len(invalid_pieces) or len(invalid_talk_ids):
            if len(invalid_pieces) > 3:
                self.msg(channel, '%s: I do not believe that was intended '
                                  'to be a vote.' % user)
            elif len(invalid_pieces):
                self.msg(channel, '{user}: I do not understand {tok}.'.format(
                    user=user,
                    tok=self._english_list(
                        ['"{0}"'.format(i) for i in invalid_pieces],
                        conjunction='or',
                    ),
                ))
            if len(invalid_talk_ids):
                self.msg(channel, '{user}: You voted for {talks}, which '
                                  '{to_be_verb} not part of this group. Your '
                                  'vote has not been recorded.'.format(
                    talks=self._english_list(
                        ['#{0}'.format(i) for i in invalid_talk_ids],
                    ),
                    to_be_verb='is' if len(invalid_talk_ids) == 1 else 'are',
                    user=user,
                ))
            return

        # The simple case is that this is a "plain" vote -- a list of
        # integers with no specials (e.g. "none") and no modifiers (+/-).
        #
        # This is straightforward: the vote becomes, in its entirety, the
        # user's vote, and anything previously recorded for the user is
        # simply dropped.
        if reduce(lambda x, y: bool(x) and bool(y),
                               [re.match(r'^[\d]+$', i) for i in vote]):
            self.current_votes[user] = set([int(i) for i in vote])
            return

        # Sanity check: non-plain votes should not have *any* plain elements;
        # therefore, if there are any, we should error out now.
        if reduce(lambda x, y: bool(x) or bool(y),
                  [re.match(r'^[\d]+$', i) for i in vote]):
            # Use examples from the actual group to minimize confusion
            examples = list(self.current_group.talk_ids)[0:2]
            while len(examples) < 2:
                examples.append(randint(1, 100))  # just in case

            # Spit out the error.
            # Since this is long, send as much of it as possible to PMs
            self.msg(channel, '{0}: I cannot process this vote. See your '
                              'private messages for details.'.format(user))
            self.msg(user, 'I cannot process this vote. I understand two '
                           'voting paradigms:')
            self.msg(user, '1. An absolute list of talks '
                           '(e.g. `{0}, {1}`)'.format(*examples))
            self.msg(user, '2. Two special keywords ("all", "none"), and the '
                           'addition/removal of talks from those keywords or '
                           'from your prior vote (e.g. `all -{1}` or '
                            '`+{0}`).'.format(*examples))
            self.msg(user, 'Your vote mixes these two paradigms together, and '
                           "I don't know how to process that, so as a picky "
                           'robot, I am cowardly giving up.')
            return

        # Sanity check: exclusive modifier votes only make sense if either
        #   1. "all" or "none" is included in the vote -or-
        #   2. the user has voted already
        # If neither of these cases obtains, error out.
        if vote[0] not in ('all', 'none') and user not in self.current_votes:
            self.msg(channel, '{0}: You can only modify your prior vote if '
                              'you have already voted; you have '
                              'not.'.format(user))
            return

        # Sanity check (last one, for now): "all" or "none" only make sense 
        # at the *beginning* of a vote; don't take them at the end.
        if 'all' in vote[1:] or 'none' in vote[1:]:
            self.msg(channel, '{0}: If using "all" or "none" in a complex '
                              'vote, please use them exclusively at the '
                              'beginning.'.format(user))
            return

        # Okay, this is a valid vote with modifiers; parse it from left
        # to right and process each of the modifiers.
        for piece in vote:
            # First, is this "all" or "none"? these are the simplest
            # cases -- either a full set or no set.
            if piece == 'all':
                answer = copy(self.current_group.talk_ids)
            if piece == 'none':
                answer = set()

            # Add or remove votes with operators from the set.
            if piece.startswith('+'):
                talk_id = int(piece[1:])
                answer.add(talk_id)
            if piece.startswith('-'):
                talk_id = int(piece[1:])
                answer.remove(talk_id)

        # Okay, we processed a valid vote without error; set it.
        self.current_votes[user] = answer

    def event_user_joined(self, user, channel):
        """React to a user's joining the channel when a meeting is
        already in progress."""

        # Sanity check: if we're not in a meeting, then no need
        # to do anything at all.
        if not self._in_meeting:
            return

        # Sanity check: if the user is already in the non-voter list,
        # then this is a red herring; ignore it.
        if user in self.nonvoters:
            return

        # Spit out a welcome, and a request for a name, to the meeting channel,
        # but tailor the request to where we are.
        if self.segment == 'silent_review':
            self.msg(channel, 'Howdy %s. Right now we are in the %s segment '
                              'on group %s. Please print your name for the '
                              'record, but wait until this segment '
                              'concludes.' % (
                user,
                self.segment.replace('_', ' '),
                self.current_group.label,
            ))
        else:
            self.msg(channel, 'Howdy %s; name for the record, please?' % user)

        # Also, send the user a welcome with information about
        # where we are and what's going on.
        self.msg(user, 'Thanks for coming, %s! This meeting has already '
                       'begun.' % user)
        if self.current_group:
            self.private_current(user)
        else:
            self.msg(user, 'There is no current talk under consideration at '
                           'this moment.')

        # now give a quick overview of bot abilities
        self.msg(user, 'You may issue me commands via. private message if '
                       'you like. Issue `help` at any time for a list.')
