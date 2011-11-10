import sys

from twisted.internet import defer, protocol, reactor
from twisted.python import log
from twisted.words.protocols import irc


class BasePyConBot(irc.IRCClient):
    accepted_users = ["Alex_Gaynor", "jnoller", "VanL", "tlesher", "jacobkm"]

    def __init__(self):
        self.state_handler = None
        self._namescallback = {}

    def talk_url(self, talk):
        return "http://us.pycon.org/2012/review/%s/" % talk

    @property
    def nickname(self):
        return self.factory.nickname

    def signedOn(self):
        for channel in self.factory.channels:
            self.join(channel)

    def joined(self, channel):
        log.msg("Joined %s" % channel)
        self.msg(channel, "Hello denizens of %s, I am your god." % channel)
        self.msg(channel, "To contribute to me: https://github.com/alex/THUNDERDOME-BOT")

    def privmsg(self, user, channel, message):
        user = user.split("!")[0]
        if not message.startswith(","):
            if self.state_handler is not None:
                self.state_handler(channel, user, message)
            return
        if user not in self.accepted_users:
            return
        message = message[1:]
        command_parts = message.split()
        command, command_args = command_parts[0], command_parts[1:]
        if command not in self.commands:
            self.msg(channel, "%s: I don't recognize that command" % user)
            return
        action = getattr(self, "handle_%s" % command)
        action(channel, *command_args)

    def names(self, channel):
        channel = channel.lower()
        d = defer.Deferred()
        self._namescallback.setdefault(channel, [[], []])[0].append(d)
        self.sendLine("NAMES %s" % channel)
        return d

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
        
class BasePyConBotFactory(protocol.ClientFactory):
    def __init__(self, channels, nickname):
        self.channels = channels
        self.nickname = nickname


    def clientConnectionLost(self, connector, reason):
        log.msg("Lost connection: %s" % reason)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        log.msg("Connection failed: %s" % reason)

def main(bot_cls):
    class PyConBotFactory(BasePyConBotFactory):
        protocol = bot_cls

    log.startLogging(sys.stdout)
    reactor.connectTCP(
        "irc.freenode.net", 6667,
        PyConBotFactory(["#pycon-pc"], "pycon_bot")
    )
    reactor.run()
