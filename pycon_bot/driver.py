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
from pycon_bot import settings

class PyConBot(irc.IRCClient):
    def __init__(self):
        # mode and state handler
        from pycon_bot.modes.base import SkeletonMode
        self.mode = SkeletonMode(self)
        self.state_handler = None
        
        # variables storing superuser information
        self.potential_superusers = settings.IRC_SUPERUSERS
        self.superusers = set()
        self._namescallback = {}
        
        # the timer running, if any
        self.timer = None
        
    #
    # "Public" API - stuff to be called by drivers.
    #

    @property
    def nickname(self):
        return self.factory.nickname

    def set_timer(self, channel, seconds, message='Time has ended.',
                        callback=None, callback_kwargs={}):
        """Set a timer. By default, simply say `message` after
        `seconds` have elapsed.

        Additionally, if a callback is provided, run it.
        """
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
        """Clear an already-set timer, and return it."""
        
        # get the timer so I can get data out of it, in case
        # I need to re-instutite the timer       
        if self.timer:
            self.timer.cancel()
            self.timer = None        
                    
    def names(self, channel):
        """List names in the channel.

        Returns a deferred. Because THIS IS TWISTED!
        """
        channel = channel.lower()
        d = defer.Deferred()
        self._namescallback.setdefault(channel, [[], []])[0].append(d)
        self.sendLine("NAMES %s" % channel)
        return d


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
        # means the user's identiied with services, so if they're in the
        # allowed SUs and NickServ gives us a "3", then that user is auth'd.
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
        log.msg('Joined %s' % channel)
        self.msg(channel, 'Hello, denizens of %s!' % channel)
        self.msg(channel, ' '.join((
            'To contribute to me:',
            'https://github.com/PyCon/pc-bot',
        )))
        self.check_auth()
        
    def userJoined(self, user, channel):
        """When a new user joins the channel, take appropriate action,
        and also ask the node what, if anything, it wants to do."""
        
        # is this a potential superuser? if so, we
        # need to refresh the superuser list
        if user in self.potential_superusers:
            self.check_auth()
        
        # now ship us off to the mode
        if hasattr(self.mode, 'event_user_joined'):
            self.mode.event_user_joined(user, channel)

    def privmsg(self, user, channel, message):
        """Called whenever a message is recived.
        
        If this is a private message, dispatch it to the private messaging
        command bank.

        If the message starts with ",<cmd>", then dispatch to a `handle_<cmd>`
        function, either on self or on the bot mode object, but only if the
        user is a superuser.
        """

        user = user.split("!")[0]

        # if this is a private message, then it uses the
        # private messaging commands rather than the chair commands
        if not channel.startswith('#'):
            command_parts = message.split()
            command, args = command_parts[0], command_parts[1:]
            self.mode.exec_command(command, 'private', user, channel, *args)
            return
        
        # Modes can define a log_message function which'll be called for each
        # message, command or not. This lets modes do logging.
        if hasattr(self.mode, 'log_message'):
            self.mode.log_message(user, channel, message)

        # Some times - voting - we want to record every command. In those cases,
        # the botmode will set state_handler and we'll call that. Othwewise,
        # we only care about ,-prefixed commands.
        if not message.startswith(','):
            if self.state_handler:
                user_message = message.lower().strip()
                if not user_message:
                    return
                self.state_handler(user, channel, user_message)
            return

        # only accept commands from superusers
        if user not in self.superusers:
            return

        # find the appropriate callback on the mode
        # (or one of its superclasses)
        message = message[1:]
        command_parts = message.split()
        command, command_args = command_parts[0], command_parts[1:]
        self.mode.exec_command(command, 'chair', user, channel, *command_args)

    def msg(self, channel, message):
        # Make sure things I say go into the transcript, too.
        if channel.startswith('#') and hasattr(self.mode, 'log_message'):
            self.mode.log_message(self.nickname, channel, message)
        irc.IRCClient.msg(self, channel, message)  # scumbag old-style class

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
