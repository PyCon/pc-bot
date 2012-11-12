#!/usr/bin/env python
"""Generate an agenda for the next meeting.

Skips over any talks already reviewed, then prints out a simple agenda of the
next [number] talks."""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, Group

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
        """Actually run the command. Find the appropriate handler, run it, and return the result."""

        # sanity check: do I have a mode at all?
        if not self.args.mode:
            print >> sys.stderr, 'You must print an agenda for a particular mode. Modes are: {modes}\n'.format(
                modes=', '.join(self._modes),
            )

        # sanity check: does the mode I was asked to run have a handler?
        method = 'handle_{mode}'.format(mode=self.args.mode)
        if not hasattr(self, method):
            print >> sys.stderr, 'No handler for {mode}. Modes are: {modes}\n'.format(
                mode=self.args.mode,
                modes=', '.join(self._modes),
            )

        # run the appropriate handler
        return getattr(self, method)()

    def handle_review(self):
        """Print out an agenda for a single kittendome meeting."""

        talks = TalkProposal.objects(status__in=('unreviewed', 'hold')).order_by('talk_id')[:self.args.num]
        overflow = TalkProposal.objects(status__in=('unreviewed', 'hold')).order_by('talk_id')[self.args.num:self.args.num + self.args.overflow]

        print "=== AGENDA ==="
        print
        for t in talks:
            print t.agenda_format
        if overflow:
            print "=== OVERFLOW ==="
            print
            for t in overflow:
                print t.agenda_format

    def handle_thunder(self):
        """Print out an agenda for a single thunderdome meeting."""

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
    p.add_argument('--dsn')
    p.add_argument('-n', '--num', type=int, default=6)
    p.add_argument('-o', '--overflow', type=int, default=2)
    args = p.parse_args()

    # sanity check: do we have a MONGO_DSN -- this is the database to connect
    # to; it doesn't make sense to run the script without it
    if not pycon_bot.mongo.connect(args.dsn):
        sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
        sys.exit(1)

    # run my agenda commnad
    command = Command(args)
    command.run()