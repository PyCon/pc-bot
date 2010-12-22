import re
import sys

from twisted.internet import protocol, reactor
from twisted.python import log
from twisted.words.protocols import irc


class PyConBot(irc.IRCClient):
    accepted_users = ["Alex_Gaynor", "jnoller", "VanL", "brettcannon"]
    commands = frozenset(["next", "debate", "vote", "report"])
    vote_re = re.compile(r"[, ]")
    talk_groups = [
        {
            "name": "Storage",
            "talks": [156, 157, 220],
#            "discussion_time": 5,
#            "debate_time": 5,
        }
    ]

    def __init__(self):
        self.idx = -1
        self.state_handler = None

    def talk_url(self, talk):
        return "http://us.pycon.org/2011/review/%s/" % talk

    @property
    def nickname(self):
        return self.factory.nickname

    def signedOn(self):
        for channel in self.factory.channels:
            self.join(channel)

    def joined(self, channel):
        log.msg("Joined %s" % channel)
        self.msg(channel, "Hello denizens of %s, I am your god." % channel)

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

    def handle_next(self, channel):
        self.idx += 1
        self.state_handler = None
        try:
            group = self.talk_groups[self.idx]
        except IndexError:
            self.msg(channel, "Out of talk groups")
            return
        self.msg(channel, "Group: %s up next.  Talks: %s" % (
            group["name"], ", ".join(map(str, group["talks"]))
        ))
        for talk in group["talks"]:
            self.msg(channel, "Talk %s: %s" % (talk, self.talk_url(talk)))
        self.msg(channel, "We will now talk %d minutes to review the talks "
            "before debate" % (group.get("discussion_time", 5))
        )

    def handle_debate(self, channel):
        group = self.talk_groups[self.idx]
        self.msg(channel, "The floor is now open for debate, we'll have %d "
            "minutes before voting" % (group.get("debate_time", 5))
        )

    def handle_vote(self, channel):
        self.msg(channel, 'Voting time!  Enter your vote in the form 1, 2, 3.  '
            'You may vote for as many talks as you feel should be accepted, '
            'however keep in mind we have a limited number of slots.'
        )
        self.current_votes = {}
        self.state_handler = self.handle_user_vote

    def handle_user_vote(self, channel, user, message):
        self.current_votes[user] = message

    def handle_report(self, channel):
        group = self.talk_groups[self.idx]
        talks = group["talks"]
        talk_votes = dict.fromkeys(talks, 0)
        for vote in self.current_votes.itervalues():
            votes = self.vote_re.split(vote)
            for vote in votes:
                try:
                    vote = int(vote)
                except ValueError:
                    pass
                else:
                    if vote in talk_votes:
                        talk_votes[vote] += 1
        self.msg(channel, "The scores are in! From the East German judge...: %s" % (
            ", ".join(
                "talk #%s: %s votes" % (k, v)
                for k, v in sorted(talk_votes.iteritems(), key=lambda (k, v): v, reverse=True)
            )
        ))


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


def main():
    log.startLogging(sys.stdout)
    reactor.connectTCP(
        "irc.freenode.net", 6667,
        PyConBotFactory(["#pycon-pc"], "pycon_bot")
    )
    reactor.run()


if __name__ == "__main__":
    main()
