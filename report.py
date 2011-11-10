"""
Report on a meeting's decisions::

    python report.py talks.json [first]

Prints a summarized report of the votes on each talk starting at the talk with
ID ``first``. If not given, sumarize all talks.

Originally written by Luciano Ramalho and Steve Holden (see
https://gist.github.com/1354185).
"""

import sys
import json
from textwrap import TextWrapper

wrapper = TextWrapper(width=55)

LINE_FORMAT = '{id:>3} {mark:>8} {yay:>3} {nay:>3} {abstain:>3}  {name}'

with open(sys.argv[1]) as json_in:
    talks = json.load(json_in)

index = 0
try:
    first = int(sys.argv[2])
except (IndexError, ValueError):
    pass
else:
    while talks[index]['id'] != first:
        index += 1

print LINE_FORMAT.format(id='ID', mark='DECISION', yay='YAY', nay='NAY', abstain='ABS', name='TITLE')
for talk in talks[index:]:
    if 'decision' not in talk:
        break
    else:
        mark = {'rejected': 'reject', 'accepted': 'accept', 'poster': 'poster'}[talk['decision']]
        votes = talk['votes'] if 'votes' in talk else dict(yay=0, nay=0, abstain=0)
        talk.update(votes)
        namelist = wrapper.wrap(talk['name'])
        talk['name'] = namelist[0]
        print LINE_FORMAT.format(mark=mark, **talk)
        for name in namelist[1:]:
            print " "*25, name
