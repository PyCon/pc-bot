"""
Dump the transcript for a particular talk.
"""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, Meeting

p = argparse.ArgumentParser()
p.add_argument('--dsn')
p.add_argument('talk_or_meeting', choices=['talk', 'meeting'])
p.add_argument('id', type=int)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

if args.talk_or_meeting == 'talk':
    transcript = TalkProposal.objects.get(talk_id=args.id).kittendome_transcript
elif args.talk_or_meeting == 'meeting':
    transcript = Meeting.objects.get(number=args.id).transcript
print "\n".join(map(unicode, transcript))
