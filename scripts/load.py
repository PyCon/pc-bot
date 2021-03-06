#!/usr/bin/env python
"""
Load data into the bot.

Works off the CSV export available at
https://us.pycon.org/2013/reviews/section/talks/. Download it to a file,
then run `python load.py fname.csv`
"""

import re
import csv
import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, SiteVotes

p = argparse.ArgumentParser()
p.add_argument('csvfile')
p.add_argument('--dsn')
p.add_argument('--clear', action='store_true', default=False)
p.add_argument('--dry-run', action='store_true', default=False)
p.add_argument('-v', '--verbose', action='store_true', default=False)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

if args.clear:
    TalkProposal.objects.delete()

for r in csv.DictReader(open(args.csvfile)):
    # We're not using get_or_create so that we can support --dry-run.
    try:
        talk = TalkProposal.objects.get(talk_id=int(r['#']))
        created = False
    except TalkProposal.DoesNotExist:
        talk = TalkProposal(talk_id=int(r['#']), status='unreviewed')
        created = True

    talk.category = r['Category']
    talk.speaker, talk.title = re.split(r'\s{4,}', r['Speaker / Title'], 1)

    talk.site_votes = SiteVotes(plus_1=r['+1'], plus_0=r['+0'], minus_0=r['-0'], minus_1=r['-1'])

    if not args.dry_run:
        talk.save()

    if args.verbose:
        print "%s #%s - %s" % ("Created" if created else "Updated", talk.talk_id, talk.title)
