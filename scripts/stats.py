"""
Print some overview/stats about talks.
"""

import math
import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, Meeting

p = argparse.ArgumentParser()
p.add_argument('--dsn')
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

total = len(TalkProposal.objects)
reviewed = len(TalkProposal.objects(status__ne='unreviewed'))
remaining = total - reviewed
percent_reviewed = float(reviewed) / total
accepted = len(TalkProposal.objects(status__in=('thunderdome', 'accepted')))
percent_accepted = (float(accepted) / reviewed) if reviewed else 0
rejected = len(TalkProposal.objects(status__in=('rejected', 'posted')))
percent_rejected = (float(rejected) / reviewed) if reviewed else 0

number_of_meetings = len(Meeting.objects)
talks_per_meeting = float(reviewed) / number_of_meetings
meetings_left = int(math.ceil(float(remaining) / talks_per_meeting))

print """\
{reviewed}/{total} talks reviewed ({percent_reviewed:.0%}); {remaining} talks remaining.
{accepted} talks accepted ({percent_accepted:.0%}); {rejected} talks rejected ({percent_rejected:.0%}).

{number_of_meetings} meetings held so far, on average {talks_per_meeting} talks per meeting.
In theory, {meetings_left} meetings remain.\
""".format(**locals())
