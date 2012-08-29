"""
Report on a meeting's decisions::

    python report.py meeting_id

Prints a summarized report of the votes on each talk decided in a meeting.

Originally written by Luciano Ramalho and Steve Holden (see
https://gist.github.com/1354185), then updated over the years by JKM, Alex
Gaynor, and others.
"""

import argparse
import pycon_bot.mongo
import sys
from pycon_bot.models import Meeting, TalkProposal
from textwrap import TextWrapper

p = argparse.ArgumentParser()
p.add_argument('--dsn')
p.add_argument('--all', action='store_true', default=False)
p.add_argument('meeting_id', type=int, nargs='?')
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

wrapper = TextWrapper(width=55)
LINE_FORMAT = '{id:>3} {mark:>8} {yay:>3} {nay:>3} {abstain:>3}  {title}'
print LINE_FORMAT.format(id='ID', mark='DECISION', yay='YAY', nay='NAY', abstain='ABS', title='TITLE')

if args.meeting_id:
    talks = Meeting.objects.get(number=args.meeting_id).talks_decided
elif args.all:
    talks = TalkProposal.objects.order_by('talk_id')
else:
    talks = TalkProposal.objects(status__ne='unreviewed').order_by('talk_id')

for t in talks:
    mark = t.status[0:6]
    v = t.kittendome_votes
    if v:
        y, n, a = v.yay, v.nay, v.abstain
    else:
        y = n = a = '-'
    titlelist = wrapper.wrap(t.title.encode('utf-8'))
    title = titlelist[0]
    print LINE_FORMAT.format(id=t.talk_id, mark=mark, yay=y, nay=n, abstain=a, title=title)
    for l in titlelist[1:]:
        print " "*25, l
