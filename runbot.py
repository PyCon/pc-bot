"""
Run the bot.
"""

import os
import sys
import argparse
import pycon_bot.driver
import mongoengine
import urlparse
from twisted.python import log
from twisted.internet import reactor

def run_bot(irc_server, irc_port, irc_channel, bot_name, logfile=None):
    log.startLogging(logfile)
    bot = pycon_bot.driver.PyConBotFactory([irc_channel], bot_name)
    reactor.connectTCP(irc_server, irc_port, bot)
    reactor.run()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--server', default='irc.freenode.net')
    p.add_argument('--port', type=int, default=6667)
    p.add_argument('--channel', default='#pycon-pc')
    p.add_argument('--name', default='pycon_bot')
    p.add_argument('--dsn', default=None)
    args = p.parse_args()
    dsn = args.dsn or os.environ.get('MONGO_DSN', None)
    if not dsn:
        sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
        sys.exit(1)

    # Connect to mongo. Have to parse out the DSN which is gross, but better
    # than using 6 env vars/flags.
    p = urlparse.urlparse(dsn)
    db = p.path.strip('/')
    userpass, hostport = p.netloc.rsplit('@', 1)
    username, password = userpass.split(':', 1)
    host, port = hostport.split(':', 1)
    mongoengine.connect(db, host=host, port=int(port), username=username, password=password)

    # Run ze bot!
    run_bot(args.server, args.port, args.channel, args.name, sys.stderr)
