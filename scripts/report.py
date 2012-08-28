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
from pycon_bot.models import Meeting
from textwrap import TextWrapper

p = argparse.ArgumentParser()
p.add_argument('--dsn')
p.add_argument('meeting_id', type=int)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

wrapper = TextWrapper(width=55)
LINE_FORMAT = '{id:>3} {mark:>8} {yay:>3} {nay:>3} {abstain:>3}  {title}'
print LINE_FORMAT.format(id='ID', mark='DECISION', yay='YAY', nay='NAY', abstain='ABS', title='TITLE')

for t in Meeting.objects.get(number=args.meeting_id).talks_decided:
    if t.status == 'unreviewed':
        continue
    mark = t.status[0:6]
    v = t.kittendome_votes
    titlelist = wrapper.wrap(t.title)
    title = titlelist[0]
    print LINE_FORMAT.format(id=t.talk_id, mark=mark, yay=v.yay, nay=v.nay, abstain=v.abstain, title=title)
    for l in titlelist[1:]:
        print " "*25, l
