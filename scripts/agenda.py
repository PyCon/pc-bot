"""
Generate an agenda for the next meeting.

Skips over any talks already reviewed, then prints out a simple agenda of the
next [number] talks.
"""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal

p = argparse.ArgumentParser()
p.add_argument('--dsn')
p.add_argument('-n', '--num', type=int, default=10)
p.add_argument('-o', '--overflow', type=int, default=2)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

talks = TalkProposal.objects(status='unreviewed').order_by('talk_id')[:args.num]
overflow = TalkProposal.objects(status='unreviewed').order_by('talk_id')[args.num:args.num+args.overflow]

def pt(t):
    return "#%s - %s - %s\n%s\n" % (t.talk_id, t.title, t.speaker, t.review_url)

print "=== AGENDA ==="
print
for t in talks:
    print pt(t)
if overflow:
    print "=== OVERFLOW ==="
    print
    for t in overflow:
        print pt(t)
