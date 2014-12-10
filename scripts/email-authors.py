#!/usr/bin/env python
"""
Sends email to authors.

To use this, first you need a template. A template is a text file. The first
line should be "Subject: ..." and then the subject of the email, followed by
two newlines, then the body of the email. For example::

    Subject: [PyCon 2013] Hello, {speaker}!

    Hello {speaker}, I just wanted to say hi!

As you can see, the message can contain {format}-style formatting which'll be
interpolated against the TalkProposal object's fields.

Then, send the message; see --help for all the options.

This requires Django because sending email using the stdlib is harder than
it should be and I'm lazy.
"""

import argparse
import io
import json
import os
import sys
import time
from pycon_bot.models import Proposal
from django.conf import settings
from django.core import mail

p = argparse.ArgumentParser()
p.add_argument('template')
p.add_argument('--dry-run', action='store_true', default=False, help="Do everything except send email")
p.add_argument('--test', metavar="EMAIL", default=False, help="Instead of sending email, send just one formatted email directly to EMAIL")
p.add_argument('--smtp-host', default='localhost', help='SMTP host')
p.add_argument('--smtp-user', default=os.getlogin(), help='SMTP username')
p.add_argument('--smtp-password', default='', help='SMTP password')
p.add_argument('--smtp-ssl', dest='smtp_ssl', action='store_true', default=False, help="Use implicit SMTP TLS (SSL)")
p.add_argument('--smtp-no-tls', dest='smtp_tls', action='store_false', default=True, help="Do not use explicit SMTP TLS")
p.add_argument('--from-email', default='Luke Sneeringer <luke@sneeringer.com>', help='From email address')
p.add_argument('--cc', default='', nargs='*', help='CC e-mail address. Can be used multiple times.')
p.add_argument('--sleep', type=float, default=2, help='Amount of time (seconds) to sleep in between sending (to avoid getting throttled).')
p.add_argument('--id', metavar='ID', dest='talk_ids', type=int, nargs='*', help='Only email specific talk IDs')
p.add_argument('--status', choices=['accepted', 'rejected', 'undecided', 'standby'], help='Only email talks with status of STATUS')
p.add_argument('--start-at', dest='start_at', default=None, type=int, help='Do not mail talks below the given ID. Useful if you get rate limited.')
args = p.parse_args()

# Configure...
settings.configure(
    EMAIL_HOST=args.smtp_host,
    EMAIL_HOST_USER=args.smtp_user,
    EMAIL_HOST_PASSWORD=args.smtp_password,
    EMAIL_USE_SSL=args.smtp_ssl,
    EMAIL_USE_TLS=args.smtp_tls,
    EMAIL_PORT=587 if args.smtp_tls else 25,
)

# Figure out which talks to send emails about.
if args.talk_ids and args.status:
    p.error("Can't pass both --id and --status.")
if args.talk_ids:
    talk_ids = [int(i) for i in args.talk_ids]
    talks = [p for p in Proposal.objects.all() if p.id in talk_ids]
elif args.status:
    talks = Proposal.objects.filter(status=args.status)
else:
    p.error("Pass either --id or --status; I won't email all authors.")

# Read and parse the template.
try:
    template = io.open(args.template, encoding='utf-8').read()
    subject_line, body_template = template.split('\n\n', 1)
except IOError:
    p.error("Template doesn't exist.")
except ValueError:
    p.error("Template is malformed; must be 'Subject: ...\n\nBody ...")
if not subject_line.startswith('Subject:'):
    p.error("Template doesn't start with 'Subject: ...")
subject_template = subject_line.replace('Subject:', '').strip()

# Send ye olde emailes.
for talk in talks:
    # Sanity check: If there is a --start-at above this number,
    # skip this one.
    if args.start_at and args.start_at > talk.id:
        continue

    # Put together the template.
    t = talk.template_context
    sys.stdout.write(u'Emailing {speaker} about #{id} - {title}...'.format(**t))
    sys.stdout.flush()
    subject = subject_template.format(**t)
    message = body_template.format(**t)

    # If this is a test, send a single test e-mail and then stop.
    if args.test:
        message = mail.EmailMessage(
            body=message,
            cc=args.cc,
            from_email=args.from_email,
            subject='[TEST] %s' % subject,
            to=[args.test],
        )
        message.send()
        print "OK - sent test email instead."
        break

    # Now send the actual email (unless this is a dry run).
    if not args.dry_run:
        message = mail.EmailMessage(
            body=message,
            cc=args.cc,
            from_email=args.from_email,
            subject=subject,
            to=['%s <%s>' % (s['name'], s['email']) for s in talk.speakers],
        )
        message.send()
        time.sleep(args.sleep)
    print "OK"
