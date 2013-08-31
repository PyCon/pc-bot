from pycon_bot.modes import review
from pycon_bot.modes.test.dummy_bot import Bot
from pycon_bot.test.test_log import FakeLogTarget
from twisted.trial import unittest


class ThunderdomeLogTests(unittest.TestCase):
    def setUp(self):
        self.target = FakeLogTarget()
        self.mode = review.Mode(Bot(self.target))
        self.mode.current = DummyTalkProposal(1)

    def test_log(self):
        """Messages are logged to the right proposal.
        """
        self.mode.log_message("user", "#test", "message")
        talk_id, user, message = self.target.logged_messages[-1]
        self.assertEqual(talk_id, 1)
        self.assertEqual(user, "user")
        self.assertEqual(message, "message")


class DummyTalkProposal(object):
    def __init__(self, talk_id):
        self.talk_id = talk_id

    def add_to_transcript(self, *a, **kw):
        """
        NOP.
        """
