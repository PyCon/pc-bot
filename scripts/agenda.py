#!/usr/bin/env python
"""Generate an agenda for the next meeting.

Skips over any talks already reviewed, then prints out a simple agenda of the
next [number] talks.
"""
import sys
import argparse
from pycon_bot.models import Proposal  #, Group

class Command(object):
    def __init__(self, args):
        self.args = args

    @property
    def _modes(self):
        """Return a list of valid modes."""
        answer = []
        for i in dir(self):
            if i.startswith('handle_'):
                answer.append(i.replace('handle_', ''))
        return answer

    def run(self):
        """Actually run the command. Find the appropriate handler,
        run it, and return the result.
        """
        # Sanity check: Do I have a mode at all?
        if not self.args.mode:
            print >> sys.stderr, ' '.join((
                'You must print an agenda for a particular mode.',
                'Modes are: {modes}\n',
            )).format(modes=', '.join(self._modes))

        # Sanity check: does the mode I was asked to run have a handler?
        method = 'handle_{mode}'.format(mode=self.args.mode)
        if not hasattr(self, method):
            print >> sys.stderr, ' '.join((
                'No handler for {mode}.',
                'Modes are: {modes}\n'
            )).format(mode=self.args.mode, modes=', '.join(self._modes))

        # Run the appropriate handler.
        return getattr(self, method)()

    def handle_kitten(self):
        """Print out an agenda for a single kittendome meeting."""

        # Get a list of talks.
        talks = Proposal.objects.talks()
        counter = 0

        # Iterate over talks until we either run out of talks,
        # or have hit the number we are supposed to be reviewing.
        for talk in talks:
            # Sanity check: Does this talk belong?
            if self.args.start and talk.id < self.args.start:
                continue

            # If this is the first talk, print out an agenda header; if it's
            # the first talk of overflow, print out an overflow header.
            if counter == 0:
                print '=== AGENDA ==='
            if counter == self.args.num:
                print '=== OVERFLOW ==='

            # Okay, now print out the talk information.
            print talk.agenda_format

            # Increment the counter, so we know how far to go.
            # If we've printed out enough talks, stop.
            counter += 1
            if counter == self.args.num + self.args.overflow:
                return

    def handle_thunder(self):
        """Print out an agenda for a single thunderdome meeting."""

        # FIXME!
        return NotImplemented

        # get the agenda and the overflow groups
        agenda = Group.objects.filter(decided__ne=True).order_by('number')[:self.args.num]
        overflow = Group.objects.filter(decided__ne=True).order_by('number')[self.args.num:self.args.num + self.args.overflow]

        print '=== AGENDA ===\n'
        for group in agenda:
            print group.agenda_format
        if overflow:
            print '\n=== OVERFLOW ===\n'
            for group in overflow:
                print group.agenda_format


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', type=str)
    p.add_argument('-s', '--start', type=int, default=None)
    p.add_argument('-n', '--num', type=int, default=8)
    p.add_argument('-o', '--overflow', type=int, default=4)
    args = p.parse_args()

    # run my agenda commnad
    command = Command(args)
    command.run()
