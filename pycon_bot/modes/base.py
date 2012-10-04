from __future__ import division


class BaseBotMode(object):
    """
    Base class for all modes, handling all the base commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.reported_in = set()
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
        
    def handle_names(self, channel):
        """Prompt everyone in the channel to write their names.
        Note who has done so in order to easily compile a non-voter list."""
        
        self.msg(channel, 'Please write your full name in the channel, for the meeting records.')
        self.bot.state_handler = self.handle_user_names
        
    def handle_user_names(self, channel, user, message):
        """As users write their names, note that they've reported in,
        so we can see who isn't here and set them as non-voters."""
        
        # this user has now reported in
        self.reported_in.add(user)
        
        # if this user is in the non-voter list, fix that
        if user in self.nonvoters and user not in self.bot.superusers:
            self.handle_voter(channel, user)
            
    def handle_nonvoter(self, channel, *users):
        # this is a special command if we're in the "reporting in" phase;
        # set as a non-voter everyone who hasn't reported in yet
        if self.bot.state_handler == self.handle_user_names and not users:
            def _(names):
                laggards = set(names) - self.reported_in - self.nonvoters
                laggards.remove(self.bot.nickname)
                if laggards:
                    self.nonvoters.update(laggards)
                    self.msg(channel, 'Will no longer pester %s.' % ', '.join(laggards))
            self.bot.names(channel).addCallback(_)
            return
        
        # run normally
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
        """Pester the laggards."""
        
        # special case: if we're in the "reporting in" phase, then check for that
        # instead of checking for votes like we'd normally do
        if self.bot.state_handler == self.handle_user_names:
            def _(names):
                laggards = set(names) - self.reported_in - self.nonvoters
                laggards.remove(self.bot.nickname)
                if laggards:
                    self.msg(channel, '%s: ping' % ', '.join(laggards))
                else:
                    self.msg(channel, 'Everyone is accounted for!')
            self.bot.names(channel).addCallback(_)
            return
        else:
            # okay, this is the normal situation case
            def _(names):
                laggards = (set(names) - set(self.current_votes.keys()) - self.nonvoters)
                laggards.remove(self.bot.nickname)
                if laggards:
                    self.msg(channel, "Didn't vote: %s.", ", ".join(laggards))
                else:
                    self.msg(channel, "Everyone voted.")
        
        # actually do the pestering
        self.bot.names(channel).addCallback(_)
        
    def _seconds_to_text(self, seconds):
        """Convert a number of seconds, specified as an int or string,
        to a pretty string."""
        
        # let's get started
        seconds = int(seconds)
        time_text = ''

        # sanity check: 0 seconds is a corner case; just return it back statically
        if seconds == 0:
            return '0 seconds'
            
        # deal with the minutes portion
        if seconds // 60 > 0:
            time_text += '%d minute' % (seconds // 60)
            if seconds // 60 != 1:
                time_text += 's'
            if seconds % 60:
                time_text += ', '
                
        # deal with the seconds portion
        if seconds % 60:
            time_text += '%d second' % (seconds % 60)
            if seconds % 60 != 1:
                time_text += 's'
        return time_text
            
    def _minutes_to_text(self, minutes):
        """Convert a number of minutes, specified as a float, int, or string,
        to a pretty string."""
        
        seconds = int(float(minutes) * 60)
        return self._seconds_to_text(seconds)