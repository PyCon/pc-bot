"""
Scrape the schedule for accepted talks.

Produces a JSON file suitable for passing as a --data argument to email-authors.
I use this to to send a preview of when their talks are scheduled (see
email-templates/check-schedule-template.txt).
"""

import argparse
import dateutil.parser
import json
import lxml.html
import sys
import urllib
import pycon_bot.mongo
from pycon_bot.models import TalkProposal

# Where's the schedue list?
URL = 'https://us.pycon.org/2013/schedule/talks/list/'

# Map and normalize days to datetimes
DAY_MAP = {
    'Friday': 'Friday, March 15th',
    'Saturday': 'Saturday, March 16th',
    'Sunday': 'Sunday, March 17th',
}

p = argparse.ArgumentParser()
p.add_argument('--dsn', help="Mongo DSN")
args = p.parse_args()
if not pycon_bot.mongo.connect(args.dsn):
    p.error("Need to pass --dsn or set env[MONGO_DSN].")

doc = lxml.html.parse(urllib.urlopen('https://us.pycon.org/2013/schedule/talks/list/')).getroot()
data = {}

for div in doc.cssselect('div.presentation'):
    # Find the link so we can look up which talk_id this refers to
    link = 'https://us.pycon.org' + div.find('h3/a').attrib['href']
    talk = TalkProposal.objects.get(public_url=link)

    # Parse out the scheduled timeslot
    schedule_text = div.findall('h4')[-1].text.strip()
    day, startstop, _, _ = [t.strip() for t in schedule_text.split('\n')]
    start, stop = startstop.replace('noon', '12:00 pm').split(u'\u2013')
    slot_length = dateutil.parser.parse(stop) - dateutil.parser.parse(start)

    data[talk.talk_id] = {
        'day': DAY_MAP[day],
        'start': start,
        'stop': stop,
        'length': '%i minutes' % (slot_length.total_seconds() / 60),
    }

json.dump(data, sys.stdout, indent=2)
