"""
Dump the transcript for a particular talk.
"""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal

p = argparse.ArgumentParser()
p.add_argument('--dsn')
p.add_argument('talk_id', type=int)
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

for m in TalkProposal.objects.get(talk_id=args.talk_id).kittendome_transcript:
    print m
