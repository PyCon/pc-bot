from __future__ import division
from datetime import datetime, timedelta
from pycon_bot.models import Proposal # , KittendomeVotes, Meeting
from pycon_bot.modes.base import BaseMode
from twisted.internet import reactor

# Constants for time-related things.
CHAMPION_CALL_SECONDS = 30
CHAMPION_MINUTES = 2
DEBATE_MINUTES = 3

# Votes we understand and can parse.
AYE_VOTES = ('yes', 'yay', 'yea', 'aye', '+1')
NAY_VOTES = ('no', 'nay', '-1')
ABSTAIN_VOTES = ('abs', 'abstain')
ABSTAIN_REASONS = ('afk', 'coi')


class Mode(BaseMode):
    """Kitten mode. Handles kittendome."""

    def __init__(self, bot):
        super(Mode, self).__init__(bot)

        # The current talks
        self.next = None
        self.current = None

        # The current meeting
        self.meeting = None

        # Where we are in the review process for the current
        # talk on the plate
        self.segment = None
        self.champions = []

        # Some private things
        self._delayed_vote_timer = None

    def chair_start(self, user, channel, meeting_num=None):
        """Start a meeting. If a meeting number is given, resume the
        meeting instead."""

        # Get the next talk in queue.
        try:
            self.next = Proposal.objects.next(
                status='undecided',
                type='talk',
            )
            self._in_meeting = True
        except IndexError:
            self.msg(channel, "Out of talks!")
            return

        # now pull up the meeting itself
        # try:
        #     self.meeting = Meeting.objects.get(number=meeting_num)
        #     action = "resumed"
        # except Meeting.DoesNotExist:
        #     self.meeting = Meeting.objects.create(start=datetime.now(),
        #                                           type='kittendome')
        #     action = "started"
        # self.msg(channel, '=== Meeting #%s %s. Next talk will be #%s ===',
        #          self.meeting.number, action, self.next.talk_id)
        self.msg(channel,
                 '=== Meeting started. The next talk will be #%d. ===',
                 self.next.id,
        )

        # Now ask the folks in channel for names
        # (unless this is a resumed meeting)
        if not meeting_num:
            self.names(channel)

    def chair_end(self, user, channel):
        """Conclude the meeting."""

        self.msg(channel, "=== Th-th-th-that's all folks! ===")

        # remove any state handler that may be present
        self.bot.state_handler = None

        # end the meeting
        if self.meeting:
            self.meeting.end = datetime.now()
            self.meeting.save()
            self.meeting = None

        # pull out of this mode; ,end implies a reversion to skeleton mode
        self.chair_mode(user, channel, 'none', _silent=True)

    def chair_goto(self, user, channel, talk_id):
        """Cause the next talk to be the talk with the given `talk_id`."""
        try:
            self.next = Proposal.objects.get(id=talk_id)
        except Proposal.DoesNotExist as ex:
            self.msg(channel, str(ex))
            return
        msg = 'OK, the next talk will be {id} (status: {status}).'.format(
            id=self.next.id,
            status=self.next.status,
        )
        # if self.next.kittendome_votes:
        #     msg += " Previous vote was %s." % self.next.kittendome_votes
        self.msg(channel, msg)

    def chair_next(self, user, channel, talks_remaining=None):
        """Move to the next talk, and immediately shift into champion mode."""

        # Sanity check: are we in the post report phase?
        #
        # It's *really* easy to remember to issue `,report` and not
        # issue `,accept` or `,reject`, and a call to `,next` if this
        # sequence has occured is almost certainly in error.
        #
        # Therefore, error out and force the chair to actually
        # issue a decision.
        if self.segment == 'post-report':
            self.msg(channel, ' '.join((
                'We just had a report on the current talk.',
                'I am stubbornly refusing to move to the next talk until the',
                'current one has been officially accepted or rejected.',
            )))
            return

        # If we were told, now or previously, how many talks remain
        # in this meeting, then track that accordingly.
        if talks_remaining is not None:
            self._talks_remaining = max(int(talks_remaining), 1)
        if hasattr(self, '_talks_remaining'):
            self._talks_remaining -= 1

        # Figure out which talk is up now.
        if self.next:
            t = self.current = self.next
            self.next = None
        else:
            try:
                t = self.current = Proposal.objects.next(
                    status='undecided',
                    type='talk',
                )
            except IndexError:
                self.msg(channel, 'Out of talks!')
                return

        # this is a new talk; no champions have declared themselves
        self.champions = []

        # announce the talk
        self.msg(channel, "=== Talk %d: %s - %s ===",
                          t.id, t.title, t.review_url)

        if getattr(self, '_talks_remaining', 3.14159):  # something non-falsy
            try:
                self.next = Proposal.objects.next(
                    after=t.id,
                    status='undecided',
                    type='talk',
                )
                self.msg(channel, '(%s will be next)', self.next.review_url)
            except IndexError:
                self.msg(channel, 'This will be the last talk of kittendome!')
        else:
            self.msg(channel, 'This will be the last talk for today.')

        # Begin the championing process.
        #
        # Note: if this talk has *already* been debated and is, in fact,
        # on hold, we have a different process for it.
        if self.current.status == 'hold':
            self.bot.set_timer(channel,
                               CHAMPION_CALL_SECONDS * 2,
                               callback=self.chair_reject,
                               callback_kwargs={
                                   'channel': channel,
                                   'user': user,
                               })
            msg_template = ' '.join((
                'This talk, #{talk_id}, has already been debated',
                'and voted down (transcript: {transcript}).\nIf you',
                'think it deserves to go to thunderdome and want to attempt',
                'to resurrect it, please say "me". If there is a champion,',
                'then after the champion period, we will debate as normal.',
                'If there is no champion within {time_text}, this talk will',
                'be automatically rejected.',
            ))
            self.msg(channel, msg_template.format(
                talk_id=self.current.id,
                time_text=self._seconds_to_text(CHAMPION_CALL_SECONDS * 2),
                transcript='<COMING SOON>',
                        # http://pyconbot.herokuapp.com/talks/%(talk_id)d
            ))
        else:
            # This represents the "normal" championing process.
            self.bot.set_timer(channel,
                               CHAMPION_CALL_SECONDS,
                               callback=self.chair_debate,
                               callback_kwargs={
                                   'channel': channel,
                                   'user': user,
                               })
            msg_template = ' '.join((
                'If you are a champion for #{talk_id}, or willing to',
                'champion it, please say, "me". If nobody steps up within',
                '{time_text}, we will move on to debate.'
            ))
            self.msg(channel, msg_template.format(
                talk_id=self.current.id,
                time_text=self._seconds_to_text(CHAMPION_CALL_SECONDS),
            ))

        # Start watching what users say.
        self.bot.state_handler = self.handler_user_champion

        # Tell the bot that we are currently in champion mode.
        self.segment = 'champion'

    def chair_next_champion(self, user, channel, _initial=False):
        """Move to the next champion.

        Normally, this is called automatically by a champion's
        self-designation or by a first champion's being finished,
        giving way to the next one. However, this allows the chair to
        manually continue the process if needed.
        """
        # Move to the next champion.
        if not _initial and len(self.champions):
            self.champions.pop(0)

        # Sanity check: Are there any champions?
        if not self.champions:
            self.msg(channel, ' '.join((
                'There are no more champions in queue.',
                'Moving on to debate.',
            )))
            self.debate(channel)
            return

        # This user is up; tell him what to do.
        champion = self.champions[0]
        self.msg(channel, ' '.join((
            '{username}: You\'re up. Please type a succinct argument',
            'for the inclusion of #{talk_id}. When you are finished,',
            'please type "done".',
        )).format(username=champion, talk_id=self.current.id))

        # Clear any existing timer.
        self.bot.clear_timer()

    def chair_debate(self, user, channel, debate_time=DEBATE_MINUTES):
        """Shift the channel into debate mode, and set the
        appropriate timer.
        """
        # Clear out the state handler.
        self.bot.state_handler = None

        # Actually set the bot timer.
        self.bot.set_timer(channel, float(debate_time) * 60)

        # Now report the shift to debate mode.
        self.segment = 'debate'
        self.msg(channel, "=== General Debate (%s) for Talk: #%d ===",
                 self._minutes_to_text(debate_time), self.current.id)

    def chair_extend(self, user, channel, extend_time=1):
        """Extend the time on the clock.

        In reality, this does nothing but set another clock, but it's a
        useful management tool within meetings.
        """
        # If there's an active timer, just delay it.
        if self.bot.timer and self.bot.timer.active():
            self.bot.timer.delay(float(extend_time) * 60)
        else:
            # Clear the timer and set a new one.
            self.bot.clear_timer()
            self.bot.set_timer(channel, float(extend_time) * 60)

        # Now report the extension
        self.msg(channel, '=== Extending time by %s. Please continue. ===',
                 self._minutes_to_text(extend_time))

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
        if not self.current:
            self.msg(channel, 'There is no current talk to vote on. Aborting.')
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

            # Tell the channel that we're switching segments.
            self.msg(channel, ' '.join((
                '=== Voting time! Yay/Nay votes for talk #%d ===',
                '\nPlease do not speak during voting; wait until',
                "we've gotten our report.",
            )), self.current.id)
            self.segment = 'voting'

            # set the state handler
            self.bot.state_handler = self.handler_user_vote

    def chair_report(self, user, channel):
        if not self.current:
            return

        # Turn off the state handler, which was recording votes.
        self.bot.state_handler = None

        # Tally the vote
        ayes, nays, abstentions = 0, 0, 0
        for vote in self.current_votes.itervalues():
            if vote == 'aye':
                ayes += 1
            elif vote == 'nay':
                nays += 1
            elif vote == 'abstain':
                abstentions += 1

        # Cobble together the report on the talk votes.
        report = '=== Votes on #{id}: {ayes} in favor, {nays} opposed'.format(
            ayes=ayes,
            id=self.current.id,
            nays=nays,
        )
        if abstentions > 0:
            report += ', with {abstentions} abstention{plural}'.format(
                abstentions=abstentions,
                plural='s' if abstentions != 1 else '',
            )
        report += ' ==='
        self.msg(channel, report)

        # Save the votes for posterity.
        # self.current.kittendome_votes = KittendomeVotes(
        # yay=yay, nay=nay, abstain=abstain)
        # self.current.save()

        # Tell the system that we're between reporting and moving
        # to the next talk.
        self.segment = 'post-report'

    def chair_accept(self, user, channel):
        """Accept the current talk."""
        self._make_decision(user, channel, 'thunderdome',
                            'Talk #%d accepted; moves on to thunderdome.')

    def chair_reject(self, user, channel, alternative=None):
        """Reject the current talk."""

        # If we got an argument, and there was a rejection type that we
        # recognize, then reject the talk, but in a special way.
        if alternative == 'poster':
            return self._make_decision(user, channel, 'rejected',
                'Talk #%d rejected (suggest submission of poster).',
                alternative='poster',
            )
        if alternative == 'lightning':
            return self._make_decision(user, channel, 'rejected',
                'Talk #%d rejected (suggest submission of lightning talk).',
                alternative='lightning',
            )
        if alternative == 'open_space':
            return self._make_decision(user, channel, 'rejected',
                'Talk #%d rejected (suggest submission of open space).',
                alternative='open_space',
            )

        # If we got a rejection type, but we don't understand it, then
        # error out -- probably the chair meant something else
        if alternative:
            return self.msg(channel,
                '%s, I do not understand what kind of rejection you want.',
                user,
            )

        # Okay, perform a standard rejection.
        self._make_decision(user, channel, 'rejected', 'Talk #%d rejected.')

    def chair_hold(self, user, channel):
        """Place the current talk on hold."""
        self._make_decision(user, channel, 'hold',
            'Talk #%d put on hold; will be reviewed at a future meeting.',
        )

    def private_rules(self, user):
        """Report where the user may find the rules and process notes."""

        self.msg(user, "Meeting rules: http://bit.ly/pycon-pc-rules")
        self.msg(user, "Notes about process: http://bit.ly/pycon-pc-format")

    def private_current(self, user):
        """Report on the current talk, and provide the link to view the talk
        on the PyCon PC website. Also, report where we are in the proceedings.
        """
        # Sanity check: are we on a talk at all?
        if not self.current or not self.segment:
            self.msg(user, 'There is no current talk in the system.')
            return

        # Okay, there is a current talk; show it.
        self.msg(user, 'We are currently reviewing:')
        self.msg(user, '    #{id}: {title} ({speaker})'.format(
            id=self.current.id,
            title=self.current.title,
            speaker=self.current.speakers[0]['name'],
        ))
        self.msg(user, '    %s' % self.current.review_url)
        if self.segment == 'champion':
            self.msg(user, ' '.join((
                'Currently, the talk is being championed.',
                'Please refrain from speaking until debate.',
            )))
        elif self.segment == 'debate':
            self.msg(user, ' '.join((
                'Currently, we are in debate.',
                'Feel free to participate.',
            )))
        elif self.segment == 'voting':
            self.msg(user, 'Currently, we are voting.')

    def private_next(self, user):
        """Report the next talk, and provide the link to view the talk
        on the PyCon PC website.
        """
        # Sanity check: is there a next talk in the system?
        if not self.next:
            message = 'There is no upcoming talk.'
            if self.current:
                message += ' We will be done after this talk.'
            self.msg(user, message)
            return

        # Report on the talk coming next.
        self.msg(user, 'The next talk to be discussed will be:')
        self.msg(user, '    #{id}: {title} ({speaker})'.format(
            id=self.next.id,
            title=self.next.title,
            speaker=self.next.speakers[0]['name'],
        ))
        self.msg(user, '    %s' % self.next.review_url)

    def private_agenda(self, user):
        """Print out the agenda. Attempt to assess how many talks are left
        and print out the expected agenda appropriately."""

        # Determine how many talks we expect to be left.
        # First, we start with the expected number of talks; we'll be
        # pessimistic and go with 12.
        talk_count = 12

        # Now, if we're more than 15 minutes into the meeting, then
        # we can use the number of talks decided to guess how many we think
        # will actually be left.
        if hasattr(self, '_talks_remaining'):
            talk_count = self._talks_remaining + 1
        elif self.meeting:
            meeting_end = self.meeting.start + timedelta(minutes=65)
            time_left = meeting_end - datetime.now()
            talk_count = int(round(time_left.seconds / 300))

        # Get the list of talks.
        # Hodge-podge it together from the full list that
        # the API provides.
        talks_from_api = Proposal.objects.filter(status='undecided',
                                                 type='talk')
        talks = []
        for talk in talks_from_api:
            if talk.id <= (self.current.id if self.current else self.next.id):
                continue
            talks.append(talk)
            if len(talks) >= talk_count:
                break

        # Sanity check: do we have any talks up to bat at all?
        if not talks:
            self.msg(user, ' '.join((
                'There are no talks on the agenda.',
                "Clearly, we shouldn't be here.",
            )))
            return

        # okay, show the talks coming next
        next_up = talks[0]
        subsequent_talks = talks[1:talk_count]

        # Are we printing the current or next talk?
        status = 'next'
        if self.current and self.current.id == next_up.id:
            status = 'current'

        # Print out the current/next talk to the channel.
        self.msg(user, 'The {0} talk on the table is:'.format(status))
        self.msg(user, next_up.review_url)

        # What about later talks? print them too.
        upcoming_talks = ", ".join([str(t.id) for t in subsequent_talks])
        if upcoming_talks:
            self.msg(user, 'Subsequent talks will be: %s.' % upcoming_talks)
        else:
            self.msg(user, 'The are no subsequent talks for today.')

    def handler_user_vote(self, user, channel, message):
        message = message.strip().lower()
        if message == 'y' or message.startswith(AYE_VOTES):
            self.current_votes[user] = 'aye'
        elif message == 'n' or message.startswith(NAY_VOTES):
            self.current_votes[user] = 'nay'
        elif message.startswith(ABSTAIN_VOTES):
            tokens = message.split(' ')
            if tokens[-1] in ABSTAIN_REASONS:
                self.current_votes[user] = 'abstain'
            else:
                self.msg(channel, ' '.join((
                    '%s: If you must abstain, please state your reason',
                    'for doing so in a way I understand (e.g. "abstain coi").',
                    '\nUnderstood reasons are:',
                    '\n  afk: You were away during the debate.',
                    '\n  coi: Conflict of Interest',
                    '\nIf you are simply unsure, please vote aye or nay.',
                )) % user)
        else:
            self.msg(channel, "%s: Please vote aye, nay, or abstain.", user)

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

    def handler_user_champion(self, user, channel, message):
        """Handle the baton pass where a user declares that he/she will
        champion a talk, and give him time to do it. Gripe at anyone who
        goes off script unless it's a superuser.
        """
        # If this message is "me", add the person to the champion list
        # and address appropriately.
        message = message.lower().strip().rstrip('.')
        if message == 'me':
            # Add this user to the champion queue.
            if user not in self.champions:
                self.champions.append(user)

                # Should this user champion immediately, or is he/she
                # in queue behind someone?
                if len(self.champions) == 1:
                    self.chair_next_champion(user, channel, _initial=True)
                else:
                    # Tell this user to hold off for a bit...
                    self.msg(channel, ' '.join((
                        '%s: Excellent. Please champion #%d, but wait',
                        'until %s is finished.',
                    )) % (user, self.current.id, self.champions[0]))
        else:
            # If this isn't the championing user, tell them to STFU.
            if not self.champions or user != self.champions[0]:
                # Is this user in queue later?
                instructions = ' '.join((
                    '%s: Please do not speak during the championing',
                    'process. If you want to champion #%d, please say "me".',
                ))
                if user in self.champions:
                    instructions = ' '.join((
                        '%s: You are in line to champion #%d, but please',
                        'be quiet until it is your turn.',
                    ))
                self.msg(channel, instructions % (user, self.current.id))

            # If this is the championing user, check to see if he/she's done.
            if self.champions and user == self.champions[0]:
                if message.rstrip().endswith(('done', 'done.', 'done!')):
                    # Okay, this person is done; pop him off
                    # the champion list.
                    self.msg(channel, '%s: Thank you.' % user)

                    # Is there anyone else in line to champion? If so, move on
                    # to that person, otherwise move to debate.
                    if len(self.champions) > 1:
                        self.chair_next_champion(user, channel)
                    else:
                        debate_time = DEBATE_MINUTES
                        if self.current.status == 'hold':
                            debate_time -= 1
                        self.chair_debate(user, channel,
                                          debate_time=debate_time)

    def event_user_joined(self, user, channel):
        """React to a user's joining the channel when a meeting is
        already in progress."""

        # Sanity check: If we're not in a meeting, then no need
        # to do anything at all.
        if not self._in_meeting:
            return

        # Sanity check: If the user is already in the non-voter list,
        # then this is a red herring; ignore it.
        if user in self.nonvoters:
            return

        # Spit out a welcome, and a request for a name, to the meeting channel,
        # but tailor the request to where we are.
        if self.segment in ('champion', 'voting'):
            self.msg(channel, ' '.join((
                'Howdy %s. Right now we are in the %s segment',
                'on talk #%d. Please print your name for the record,',
                'but wait until this segment concludes.',
            )) % (user, self.segment, self.current.id))
        else:
            self.msg(channel, 'Howdy %s; name for the record, please?' % user)

        # Also, send the user a welcome with information about
        # where we are and what's going on.
        self.msg(user, ' '.join((
            'Thanks for coming, %s!',
            'This meeting has already begun.',
        )) % user)
        if self.current:
            self.msg(user, ' '.join((
                'Currently, we are on talk #%d (%s).',
                'We are in the %s segment.',
            )) % (self.current.id, self.current.review_url, self.segment))
        else:
            self.msg(user, 'There is no talk under consideration right now.')

        # Now give a quick overview of bot abilities.
        self.msg(user, ' '.join((
            'You may issue me commands via. private message if you like.',
            'Issue `help` at any time for a list.',
        )))

    def log_message(self, user, channel, message):
        """Save a transcript for debate along with each talk."""
        return  # FIXME
        if self.meeting:
            self.meeting.add_to_transcript(datetime.now(), user, message)
        if self.current:
            self.current.add_to_transcript(datetime.now(), user, message)
            self.bot.log_target.log(self.current.id, user, message)

    def _make_decision(self, user, channel, decision, message,
                       alternative=None):
        """Make a given decision, and save it to the database."""

        # Clear any timer and any user mode.
        self.bot.clear_timer()
        self.bot.state_handler = None
        self.segment = None

        # Actually make the decision.
        if not self.current:
            return
        self.msg(channel, "=== %s ===" % message, self.current.id)
        # self.current.status = decision
        # self.current.kittendome_result = decision
        # if decision == 'rejected' and alternative:
            # self.current.alternative = alternative

        # Save the new status for this talk on the PyCon website.
        # FIXME: Make this better.
        self.current.write({
            'status': decision,
            'alternative': alternative,
        })

        # Place the talk into the meeting's `talks_decided` list.
        if self.meeting:
            # Sanity check: Don't push the same talk onto a meeting twice.
            # Duplication basically always means operator error.
            # meeting_copy = Meeting.objects.get(id=self.meeting.id)
            # if self.current not in meeting_copy.talks_decided:
            #     Meeting.objects(id=self.meeting.id).update_one(
            #         push__talks_decided=self.current,
            #     )

            # If this is the last talk, end.
            if getattr(self, '_talks_remaining', 3.14159) == 0:
                self.chair_end(user, channel)
