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
import os
import sys
import time
import pycon_bot.mongo
from pycon_bot.models import TalkProposal, doc2dict
from django.conf import settings
from django.core import mail

p = argparse.ArgumentParser()
p.add_argument('template')
p.add_argument('--dsn', help="Mongo DSN")
p.add_argument('--dry-run', action='store_true', default=False, help="Do everything except send email")
p.add_argument('--test', metavar="EMAIL", default=False, help="Instead of sending email, send just one formatted email directly to EMAIL")
p.add_argument('--smtp-host', default='localhost', help='SMTP host')
p.add_argument('--smtp-user', default=os.getlogin(), help='SMTP username')
p.add_argument('--smtp-password', default='', help='SMTP password')
p.add_argument('--smtp-no-tls', dest='smtp_tls', action='store_false', default=True, help="Don't use SMTP TLS")
p.add_argument('--from-email', default='jacob@jacobian.org', help='From email address')
p.add_argument('--sleep', type=float, default=1, help='Amount of time (seconds) to sleep in between sending (to avoid getting throttled).')
p.add_argument('--id', metavar='ID', dest='talk_ids', type=int, nargs='*', help='Only email specific talk IDs')
p.add_argument('--status', choices=[c[0] for c in TalkProposal.STATUSES], help='Only email talks with status of STATUS')
args = p.parse_args()

# Configure...
if not pycon_bot.mongo.connect(args.dsn):
    p.error("Need to pass --dsn or set env[MONGO_DSN].")
settings.configure(
    EMAIL_HOST = args.smtp_host,
    EMAIL_USE_TLS = args.smtp_tls,
    EMAIL_HOST_USER = args.smtp_user,
    EMAIL_HOST_PASSWORD = args.smtp_password
)

# Figure out which talks to send emails about.
if args.talk_ids and args.status:
    p.error("Can't pass both --id and --status.")
if args.talk_ids:
    talks = TalkProposal.objects.filter(talk_id__in=args.talk_ids).order_by('talk_id')
elif args.status:
    talks = TalkProposal.objects.filter(status=args.status).order_by('talk_id')
else:
    p.error("Pass either --id or --status; I won't email all authors.")

# Read and parse the template.
try:
    template = io.open(args.template, encoding='utf8').read()
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
    t = doc2dict(talk)
    sys.stdout.write(u"Emailing {speaker_email} about #{talk_id} - {title} ... ".format(**t))
    sys.stdout.flush()
    subject = subject_template.format(**t)
    message = body_template.format(**t)
    if args.test:
        mail.send_mail(subject=subject, message=message, from_email=args.from_email, recipient_list=[args.test])
        print "OK - sent test email instead."
        break
    if not args.dry_run:
        mail.send_mail(subject=subject, message=message, from_email=args.from_email, recipient_list=[talk.speaker_email])
        time.sleep(args.sleep)
    print "OK"
