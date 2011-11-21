"""
Generate an agenda for the next meeting::

    python agenda.py talks.json [number]

Skips over any talks already reviewed, then prints out a simple agenda of the
next [number] talks.

"""
import sys
import json

with open(sys.argv[1]) as fp:
    talks = json.load(fp)

try:
    num_talks = int(sys.argv[2])
except (IndexError, ValueError):
    num_talks = 12

index = 0
while "decision" in talks[index]:
    index += 1

for talk in talks[index:index+num_talks]:
    print u'http://us.pycon.org/2012/review/{id} - {name}'.format(**talk)
