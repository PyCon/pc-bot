"""
The bot "driver" is the main twisted bit that actually runs the bot. It supports
a few basic commands, but in most cases it delegates commands to a "mode" so
that the bot can be switched among different running modes without restarting.
"""

import os
import re
import importlib
from twisted.internet import defer, protocol, reactor
from twisted.python import log
from twisted.words.protocols import irc

class PyConBot(irc.IRCClient):
    def __init__(self):
        self.state_handler = None
        self._namescallback = {}
        self.timer = None
        self.mode = None
        self.potential_superusers = os.environ.get('PYCONBOT_SUPERUSERS', '').split(',')
        self.superusers = set()

    #
    # "Public" API - stuff to be called by drivers.
    #

    @property
    def nickname(self):
        return self.factory.nickname

    def set_timer(self, channel, seconds, message='Time has ended.', callback=None, callback_kwargs={}):
        """Set a timer. By default, simply say `message` after `seconds` have elapsed.
        Additionally, if a callback is provided, run it."""
        
        seconds = int(seconds)
        
        def say_time(channel):
            self.timer = None
            if message:
                self.msg(channel, "=== %s ===" % message)
            if callback and callable(callback):
                callback(**callback_kwargs)
        self.clear_timer()
        self.timer = reactor.callLater(seconds, say_time, channel)

    def clear_timer(self):
        """
        Clear an already-set timer.
        """
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def names(self, channel):
        """
        List names in the channel.

        Returns a deferred. Because THIS IS TWISTED!
        """
        channel = channel.lower()
        d = defer.Deferred()
        self._namescallback.setdefault(channel, [[], []])[0].append(d)
        self.sendLine("NAMES %s" % channel)
        return d

    #
    # Bot commands supported by the driver itself
    #

    def handle_mode(self, channel, *args):
        """
        Handle switching modes.
        """
        self.check_auth()

        if not args:
            mname = (self.mode.__class__.__name__ if self.mode else "(none)")
            self.msg(channel, "Current mode: %s" % mname)
            return

        newmode = args[0]
        try:
            mod = importlib.import_module('pycon_bot.modes.%s' % newmode)
            self.mode = getattr(mod, '%sMode' % newmode.title())(self)
            self.msg(channel, "OK, now in %s mode." % newmode)
        except (ImportError, AttributeError) as e:
            self.msg(channel, "Can't load mode %s: %s" % (newmode, e))

    def handle_sleep(self, channel, *args):
        """
        Go to sleep (i.e. set no mode).
        """
        self.msg(channel, "Sleep tight, don't let the bedbugs bite.")
        self.mode = None

    #
    # Internals
    #

    # Auth.

    def check_auth(self):
        """
        Check that everyone in set as a superuser in the env is actually
        logged in (and not spoofing) by asking NickServ. This resets the
        superuser list each time it's called.

        NickServ will respond by sending a NOTICE (*not* a PRIVMSG), which
        gets picked up by the callback below, see that.
        """
        for username in self.potential_superusers:
            self.msg('NickServ', 'ACC %s' % username)

    def noticed(self, user, channel, message):
        # Only pay attention to ACC responses from NickServ
        user = user.split('!')[0]
        if channel != self.nickname or user != 'NickServ':
            return
        try:
            username, acc, status = message.split()[0:3]
        except ValueError:
            return
        if acc != 'ACC':
            return

        # Now add or remove superusers depending on the response. A code of "3"
        # means the user's identiied with services, so if they're in the allowed
        # SUs and NickServ gives us a "3", then that user is auth'd.
        if username in self.potential_superusers and status == '3':
            self.superusers.add(username)
        elif username in self.superusers and status != '3':
            self.superusers.discard(username)

    # Support functions for the NAMES command.

    def irc_RPL_NAMREPLY(self, prefix, params):
        channel = params[2].lower()
        if channel not in self._namescallback:
            return
        nicklist = [name.strip('@+') for name in params[3].split(' ')]
        self._namescallback[channel][1] += nicklist

    def irc_RPL_ENDOFNAMES(self, prefix, params):
        channel = params[1].lower()
        if channel not in self._namescallback:
            return
        callbacks, namelist = self._namescallback[channel]
        for cb in callbacks:
            cb.callback(namelist)
        del self._namescallback[channel]

    # Twisted callbacks and such.

    def signedOn(self):
        for channel in self.factory.channels:
            self.join(channel)

    def joined(self, channel):
        log.msg("Joined %s" % channel)
        self.msg(channel, "Hello, denizens of %s, I am your god." % channel)
        self.msg(channel, "To contribute to me: https://github.com/alex/THUNDERDOME-BOT")
        self.check_auth()

    def privmsg(self, user, channel, message):
        """
        Called whenever a message is recived.

        if the message starts with ",<cmd>", then dispatch to a `handle_<cmd>`
        function, either on self or on the bot mode object, but only if the
        user is a superuser.
        """
        # Ignore private messages.
        if not channel.startswith('#'):
            return

        user = user.split("!")[0]

        # Modes can define a log_message function which'll be called for each
        # message, command or not. This lets modes do logging.
        if hasattr(self.mode, 'log_message'):
            self.mode.log_message(user, channel, message)

        # Some times - voting - we want to record every command. In those cases,
        # the botmode will set state_handler and we'll call that. Othwewise,
        # we only care about ,-prefixed commands.
        if not message.startswith(","):
            if self.state_handler:
                self.state_handler(channel, user, message)
            # TODO: callback for logging every message.
            return

        if user not in self.superusers:
            return

        # Find the callback. First look on self, then look at the mode.
        message = message[1:]
        command_parts = message.split()
        command, command_args = command_parts[0], command_parts[1:]
        callback_name = 'handle_%s' % command
        if hasattr(self, callback_name):
            action = getattr(self, callback_name)
        elif hasattr(self.mode, callback_name):
            action = getattr(self.mode, callback_name)
        else:
            self.msg(channel, "%s: I don't recognize that command" % user)
            return

        action(channel, *command_args)

    def msg(self, channel, message):
        # Make sure things I say go into the transcript, too.
        if channel.startswith('#') and hasattr(self.mode, 'log_message'):
            self.mode.log_message(self.nickname, channel, message)
        irc.IRCClient.msg(self, channel, message)  # Scumbag old-style class.

class PyConBotFactory(protocol.ClientFactory):
    protocol = PyConBot

    def __init__(self, channels, nickname):
        self.channels = channels
        self.nickname = nickname

    def clientConnectionLost(self, connector, reason):
        log.msg("Lost connection: %s" % reason)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        log.msg("Connection failed: %s" % reason)
