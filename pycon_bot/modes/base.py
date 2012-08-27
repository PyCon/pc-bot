class BaseBotMode(object):
    """
    Base class for all modes, handling all the base commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.nonvoters = set()

    @property
    def nonvoter_list(self):
        return ', '.join(self.nonvoters) if self.nonvoters else 'none'

    def handle_nonvoter(self, channel, *users):
        users = set(users)
        users.discard(self.nickname)
        if not users:
            self.bot.msg(channel, "Nonvoters: %s." % self.nonvoter_list)
            return
        self.nonvoters.update(users)
        self.bot.msg(channel, "Will no longer pester %s." % ', '.join(users))

    def handle_voter(self, channel, *users):
        users = set(users)
        users.discard(self.nickname)
        if not users:
            self.bot.msg(channel, "Nonvoters: %s." % self.nonvoter_list)
            return
        if '*' in users:
            self.nonvoters.clear()
            self.bot.msg(channel, "Will now pester everyone.")
        else:
            self.nonvoters.difference_update(users)
            self.bot.msg(channel, "Will now pester %s." % ', '.join(users))

    def handle_pester(self, channel):
        def names_callback(names):
            laggards = (set(names) - set(self.current_votes.keys()) - self.nonvoters)
            laggards.remove(self.nickname)
            if laggards:
                self.bot.msg(channel, "Didn't vote: %s." % (", ".join(laggards)))
            else:
                self.bot.msg(channel, "Everyone voted.")
        self.bot.names(channel).addCallback(names_callback)

    def talk_url(self, talk_id):
        return "http://us.pycon.org/2012/review/%s/" % talk_id
