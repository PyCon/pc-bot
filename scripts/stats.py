"""
Print some overview/stats about talks.
"""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal

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
accepted = len(TalkProposal.objects(status='thunderdome'))
percent_accepted = float(accepted) / reviewed if reviewed else 0
rejected = len(TalkProposal.objects(status='rejected'))
percent_rejected = float(rejected) / reviewed if reviewed else 0

print """{reviewed}/{total} talks reviewed ({percent_reviewed:.0%}); {remaining} talks remaining.
{accepted} talks accepted ({percent_accepted:.0%}); {rejected} talks rejected ({percent_rejected:.0%}).""".format(**locals())
