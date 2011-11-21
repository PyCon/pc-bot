"""
Print some overview/stats about talks.
"""

import sys
import json

with open(sys.argv[1]) as fp:
    talks = json.load(fp)

total = len(talks)
reviewed = len([t for t in talks if 'decision' in t])
remaining = total - reviewed
percent_reviewed = float(reviewed) / total
accepted = len([t for t in talks if t.get('decision') == 'accepted'])
percent_accepted = float(accepted) / reviewed
rejected = len([t for t in talks if t.get('decision') in ('rejected', 'poster')])
percent_rejected = float(rejected) / reviewed

print """{reviewed}/{total} talks reviewed ({percent_reviewed:.0%}); {remaining} talks remaining.
{accepted} talks accepted ({percent_accepted:.0%}); {rejected} talks rejected ({percent_rejected:.0%}).""".format(**locals())
