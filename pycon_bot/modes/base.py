from __future__ import division
import importlib
import re
import time


class SkeletonMode(object):
    """Skeleton (base) mode.
    
    This mode can take two commands:
      - change to another mode
      - print help
      
    It is also able to send messages to the channel.
    
    This mode must superclass all other modes, or you
    will likely get undesired behavior."""
    
    def __init__(self, bot):
        self.bot = bot
        
        # information about where we are in the meeting
        self._in_meeting = False
    
    def msg(self, channel, msg, *args):
        """Send a message to the given channel."""
        
        # FIXME: is hardcoded utf8 OK?
        self.bot.msg(channel, (msg % args).encode('utf-8'))
        time.sleep(0.1)
        
    def exec_command(self, command, command_type, user, channel, *args):
        """Execute an arbitrary command, provided it is found on the mode."""
        
        # if this is a command beginning with a comma,
        # then inform the user that the comma is superfluous
        if command.startswith(','):
            self.msg(user, 'A leading comma is only necessary for chair commands.')
            return
        
        # find the correct command and execute it
        method = '%s_%s' % (command_type, command)
        if hasattr(self, method):
            if command_type == 'chair':
                return getattr(self, method)(user, channel, *args)
            else:
                return getattr(self, method)(user, *args)
                
        # whups, we clearly weren't able to find the command...bork out
        help_command = 'help'
        if command_type == 'chair':
            help_command = ',' + help_command
            self.msg(channel, "Sorry, I don't recognize that command. Issue `%s` for a command list." % help_command)
        else:
            self.msg(user, "Sorry, I don't recognize that command. Issue `%s` for a command list." % help_command)

    def chair_mode(self, user, channel, new_mode=None, _silent=False):
        """Set the channel's mode. If no mode is provided,
        print out the mode we're in now.
        
        If the requested mode is "none", then set us into
        the base mode."""
        
        # if no argument is given, print out the mode that
        # we are in now
        if not new_mode:
            mode_name = self.bot.mode.__class__.__module__.__name__.lower()
            if mode_name == 'base':
                mode_name = '(none)'
            self.msg(channel, "Current mode: %s" % mode_name[:-4])
            return
    
        # okay, we were asked to *set* the mode -- do that now
        # sanity check: however, if we were given "none", that just
        #   means set in base mode
        if new_mode.lower() == 'none':
            self.bot.mode = SkeletonMode(self.bot)
            if not _silent:
                self.msg(channel, 'Mode deactivated.')
            return
            
        try:
            mod = importlib.import_module('pycon_bot.modes.%s' % new_mode)
            self.bot.mode = mod.Mode(self.bot)
            self.msg(channel, 'Activated %s mode.' % new_mode)
        except (ImportError, AttributeError) as e:
            self.msg(channel, 'Unable to load mode `%s`: %s' % (new_mode, e))
            
    def chair_help(self, user, channel, command=None):
        """Return a list of chair commands that we currently understand.
        If a specific command is given, print its docstring."""
        return self._help(user, channel, 'chair', command=command)
        
    def private_help(self, user, command=None):
        """Return a list of private message commands that we currently understand.
        If a specific command is specified, print its docstring."""
        return self._help(user, user, 'private', command=command)
            
    def _help(self, user, channel, command_type, command=None):        
        # if an argument is given, print help about that specific command
        if command:
            command = command.replace(',', '')
            method = getattr(self, '%s_%s' % (command_type, command), None)
            
            # sanity check: does this method actually exist?
            if not method:
                help_command = 'help'
                if command_type == 'chair':
                    help_command = ',%s' % help_command
                self.msg(channel, 'This command does not exist. Issue `%s` by itself for a command list.' % help_command)
                return
                
            # okay, now take the docstring and present it as help; however
            # we need to reformat my docstrings to be more IRC friendly -- specifically:
            #   - change single `\n` to just spaces
            #   - change double `\n` to single `\n`
            help_text = method.__doc__
            help_text = re.sub(r'\\n[ ]+\\n', '|---|', help_text)
            help_text = re.sub(r'\s+', ' ', help_text)
            help_text = help_text.replace('|---|', '\n')
            self.msg(channel, help_text)
            return
        
        # okay, give a list of the commands available
        commands = []
        for attr in dir(self):
            if callable(getattr(self, attr)) and attr.startswith('%s_' % command_type):
                if command_type == 'chair':
                    command_name = ',%s' % attr[len(command_type) + 1:]
                else:
                    command_name = attr[len(command_type) + 1:]
                commands.append(command_name)
        commands.sort()
        
        # now print out the list of commands to the channel
        self.msg(channel, 'I recognize the following %s commands:' % command_type)
        msg_queue = '   '
        for i in range(0, len(commands)):
            command = commands[i]
            msg_queue += command
            if i % 3 != 2 and i != len(commands) - 1:
                msg_queue += (' ' * (20 - (len(command) * 2)))
            else:
                self.msg(channel, msg_queue)
                msg_queue = '   '
                

class BaseMode(SkeletonMode):
    """Base class for all modes, handling all the base commands."""
    
    def __init__(self, bot):
        super(BaseMode, self).__init__(bot)
        self.reported_in = set()
        self.nonvoters = set()

    @property
    def nonvoter_list(self):
        return ', '.join(self.nonvoters) if self.nonvoters else 'none'
                        
    def names(self, channel):
        """Prompt everyone in the channel to write their names.
        Note who has done so in order to easily compile a non-voter list."""
        
        self.msg(channel, 'Please write your full name in the channel, for the meeting records.')
        self.bot.state_handler = self.handler_user_names
        
    def chair_nonvoter(self, user, channel, *users):
        """Set the given user to a non-voter. If no user is specified,
        then print the list of all non-voters.
        
        Exception: If we're just starting the meeting, then set anyone
        who has not reported in to be a non-voter."""
        
        # this is a special command if we're in the "reporting in" phase;
        #   set as a non-voter everyone who hasn't reported in yet
        # note: also adds as a non-voter the person who ran the command
        if self.bot.state_handler == self.handler_user_names and not users:
            def _(names):
                laggards = set(names) - self.reported_in - self.nonvoters
                laggards.remove(self.bot.nickname)
                laggards.add(user)
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

    def chair_voter(self, user, channel, *users):
        """Set a given user to be a voter. If no user is specified,
        print the list of all voters."""
        
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

    def chair_pester(self, user, channel):
        """Pester the laggards."""
        
        # special case: if we're in the "reporting in" phase, then check for that
        # instead of checking for votes like we'd normally do
        if self.bot.state_handler == self.handler_user_names:
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
        
    def handler_user_names(self, user, channel, message):
        """As users write their names, note that they've reported in,
        so we can see who isn't here and set them as non-voters."""
        
        # this user has now reported in
        self.reported_in.add(user)
        
        # if this user is in the non-voter list, fix that
        if user in self.nonvoters and user not in self.bot.superusers:
            self.chair_voter(user, channel, user)
        
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
        
    def _english_list(self, l, conjunction='and'):
        """Return a string with a comma-separated list, with an "and" between
        the penultimate and ultimate list items."""
        
        # sanity check: if there is only one list item, do nothing
        # except convert to a string
        if len(l) == 1:
            return '{0}'.format(*l)
            
        # sanity check: if there are two items, then join them with "and" but
        # don't use commas
        if len(l) == 2:
            return '{0} {conjunction} {1}'.format(*l, conjunction=conjunction)
            
        # okay, there are three or more items: I want the format to be
        # "a, b, c, and d"
        return '{initial}, {conjunction} {last}'.format(
            conjunction=conjunction,
            initial=', '.join(l[:-1]),
            last=l[-1],
        )
