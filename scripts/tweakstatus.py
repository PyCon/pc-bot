#!/usr/bin/env python
"""
Manually tweak a talk's status, leaving a note about why.
"""

import sys
import argparse
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, Note

p = argparse.ArgumentParser()
p.add_argument('talk_id', type=int)
p.add_argument('new_status', choices=[c[0] for c in TalkProposal.STATUSES])
p.add_argument('note')
p.add_argument('--dsn')
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
    sys.exit(1)

t = TalkProposal.objects.get(talk_id=args.talk_id)
t.update(
    push__notes = Note(text=args.note),
    set__status = args.new_status
)
