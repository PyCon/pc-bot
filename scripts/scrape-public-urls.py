"""
Scrape the public URLs for accepted talks.

Unfortunately, the public URLs for accepted talks (e.g.
https://us.pycon.org/2013/schedule/presentation/{id}/) aren't predictable;
they get different IDs that the proposal IDs. So this script scrapes the
publically-viewable URLs off the PyCon site and into our DB. (These get used
in emails that go out to speakers.)
"""

import argparse
import HTMLParser
import os
import re
import sys
import time
import requests
import pycon_bot.mongo
from pycon_bot.models import TalkProposal

hp = HTMLParser.HTMLParser()

p = argparse.ArgumentParser()
p.add_argument('starturl')
p.add_argument('--dsn', help="Mongo DSN")
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    p.error("Need to pass --dsn or set env[MONGO_DSN].")

# Now I have two problems
pat = re.compile('<h3><a href="(.*)">(.*)</a></h3>')

for url, title in pat.findall(requests.get(args.starturl).content):
    title = hp.unescape(title)
    url = 'https://us.pycon.org' + url
    try:
        t = TalkProposal.objects.get(status='accepted', title=title)
    except TalkProposal.DoesNotExist:
        print "Crap, couldn't find a matching talk for %s (%s)" % (url, title)
    else:
        print "Found %s for #%s - %s" % (url, t.talk_id, t.title)
        t.update(set__public_url=url)

print "\nProposals still missing public URLs:"
for t in TalkProposal.objects.filter(status='accepted', public_url=None).order_by('talk_id'):
    print "* #%s - %s" % (t.talk_id, t.title)
