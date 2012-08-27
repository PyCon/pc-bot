"""
Run the bot.
"""

import sys
import argparse
import pycon_bot.driver
import pycon_bot.mongo
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
    if not pycon_bot.mongo.connect(args.dsn):
        sys.stderr.write("Need to pass --dsn or set env[MONGO_DSN].")
        sys.exit(1)

    # Run ze bot!
    run_bot(args.server, args.port, args.channel, args.name, sys.stderr)
