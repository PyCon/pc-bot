from pycon_bot.modes import thunder
from pycon_bot.modes.test.dummy_bot import Bot
from pycon_bot.test.test_log import FakeLogTarget
from twisted.trial import unittest


class ThunderdomeLogTests(unittest.TestCase):
    def setUp(self):
        self.target = FakeLogTarget()
        self.mode = thunder.Mode(Bot(self.target))
        self.mode.current_group = Group(set([1, 2, 3, 4]))

    def test_log_for_all_talks_in_group(self):
        """Log messages are logged for all talks in the current group.

        When a log message arrives (i.e. a channel message), it is
        logged for each talk in the current group.
        """
        user, channel, message = "user", "#test", "message"
        self.mode.log_message(user, channel, message)

        seen_ids = set()
        for proposal, nickname, line in self.target.logged_messages:
            self.assertEqual(nickname, user)
            self.assertEqual(line, message)
            seen_ids.add(proposal)

        self.assertEqual(seen_ids, self.mode.current_group.talk_ids)


class Group(object):
    def __init__(self, talk_ids):
        self.talk_ids = talk_ids

    def add_to_transcript(self, *a, **kw):
        """
        NOP.
        """
