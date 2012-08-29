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
p.add_argument('-n', '--num', type=int, default=12)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

nr = args.num
for p in TalkProposal.objects(status='unreviewed').order_by('talk_id'):
    if p.site_votes.total >= 3:
        print '%s - %s' % (p.review_url, p.title)
        nr -= 1
    if nr == 0:
        break
