class BaseBotMode(object):
    """
    Base class for all modes, handling all the base commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.nonvoters = set()

    def msg(self, channel, msg, *args):
        """
        Helper function to make sending a message to the channel easier.

        Properly str-ifies everything (thanks, twisted!) and also makes string
        formatting a bit easier.
        """
        # FIXME: is hardcoded utf8 OK?
        self.bot.msg(channel, (msg % args).encode('utf-8'))

    @property
    def nonvoter_list(self):
        return ', '.join(self.nonvoters) if self.nonvoters else 'none'

    def handle_nonvoter(self, channel, *users):
        users = set(users)
        users.discard(self.bot.nickname)
        if not users:
            self.msg(channel, "Nonvoters: %s.", self.nonvoter_list)
            return
        self.nonvoters.update(users)
        self.msg(channel, "Will no longer pester %s.", ', '.join(users))

    def handle_voter(self, channel, *users):
        users = set(users)
        users.discard(self.bot.nickname)
        if not users:
            self.msg(channel, "Nonvoters: %s.", self.nonvoter_list)
            return
        if '*' in users:
            self.nonvoters.clear()
            self.msg(channel, "Will now pester everyone.")
        else:
            self.nonvoters.difference_update(users)
            self.msg(channel, "Will now pester %s.", ', '.join(users))

    def handle_pester(self, channel):
        def names_callback(names):
            laggards = (set(names) - set(self.current_votes.keys()) - self.nonvoters)
            laggards.remove(self.bot.nickname)
            if laggards:
                self.msg(channel, "Didn't vote: %s.", ", ".join(laggards))
            else:
                self.msg(channel, "Everyone voted.")
        self.bot.names(channel).addCallback(names_callback)
