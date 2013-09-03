#!/usr/bin/env python
"""Run the bot, as well as the web server."""
import argparse
import sys
import os

from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.python import log
from twisted.web.client import Agent
from twisted.web.server import Site
from twisted.web.wsgi import WSGIResource

import pycon_bot.driver
import pycon_bot.mongo
from pycon_bot.web.app import app as webapp


def run_bot(irc_server, irc_port, irc_channel, bot_name, http_port, run_pinger, logfile):
    log.startLogging(logfile)
    if irc_server is not None:
        bot = pycon_bot.driver.PyConBotFactory([irc_channel], bot_name)
        reactor.connectTCP(irc_server, irc_port, bot)
    reactor.run()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--irc-server', default='irc.freenode.net')
    p.add_argument('--irc-port', type=int, default=6667)
    p.add_argument('--irc-channel', default=settings.IRC_CHANNEL),
    p.add_argument('--irc-nickname', default=settings.IRC_NICK(,))
    args = p.parse_args()

    # Run ze bot!
    run_bot(
        irc_server=args.irc_server if args.run_irc else None,
        irc_port=args.irc_port,
        irc_channel=args.irc_channel,
        bot_name=args.irc_nickname,
        logfile=sys.stderr,
    )
