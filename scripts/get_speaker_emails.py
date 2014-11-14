#!/usr/bin/env python
from pycon_bot.models import Proposal

answer = set()
for talk in Proposal.objects.filter(status='accepted'):
    for speaker in talk.speakers:
        # if speaker['name'].strip():
            # answer.add('%s <%s>' % (speaker['name'], speaker['email']))
        # else:
            answer.add(speaker['email'])

for cursor in range(0, 500, 10):
    if len(answer) < cursor:
        break
    print(','.join(sorted(answer)[cursor:cursor + 10]))
    print('---')
