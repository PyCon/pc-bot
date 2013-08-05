"""
Tests for IRC bot logging.
"""
from datetime import datetime, timedelta
from json import dumps, loads

from pycon_bot import log
from treq import post
from twisted.internet import defer, task
from twisted.trial import unittest
from zope.interface import verify

class PyConSiteLogTargetTests(unittest.TestCase):
    """
    Tests for a log target that targets the PyCon site.
    """
    def setUp(self):
        self.target = log.PyConSiteLogTarget("host", "key")

        self.target._utcnow = self._utcnow
        self._dates = dates()

        self.target._post = self._post
        self.request_body = None
        self.post_deferred = None

    def _utcnow(self):
        """A mock utcnow implementation for testing.
        """
        return next(self._dates)

    def _post(self, url, body):
        """A mock post implementation for testing.

        Asserts that the URL is the target's URL. Keeps track of the
        request body under ``self.request_body``. Sets ``self.post_deferred``
        to a new Deferred, and returns it. (The caller is expected to fire
        this at some point.)
        """
        self.assertEqual(url, self.target._url)
        self.request_body = body
        self.post_deferred = d = defer.Deferred()
        return d

    def test_default_implementations(self):
        """Default implementations of stub targets are what they should be.
        """
        self.assertEqual(log.PyConSiteLogTarget._utcnow, datetime.utcnow)
        self.assertIdentical(log.PyConSiteLogTarget._post, post)

    def test_url(self):
        """The log target determines the correct URL.
        """
        expected = "https://host/pycon_api/set_irc_logs/key/"
        self.assertEqual(self.target._url, expected)

    def test_interface(self):
        """The log target implements the log target interface.
        """
        verify.verifyObject(log.ILogTarget, self.target)

    def test_flush_empty(self):
        """Flushing works when the buffer is empty.

        Flushing with no buffered messages returns a deferred that is
        already fired, the buffer is unmodified, no request is made.

        """
        old_buffer = self.target._buffer
        d = self.target.flush()
        self.successResultOf(d)
        self.assertIdentical(self.target._buffer, old_buffer)

    def test_flush(self):
        """Flushing works when the buffer isn't empty.

        Flushing with buffered messages returns a deferred that fires
        when upload completes. A POST request is made to the API URL.
        The buffer is emptied synchronously when the flushing starts.

        """
        self.target.log(1, "user1", "message")
        self.target.log(1, "user2", "another message")
        d = self.target.flush()

        self.assertEqual(d.called, False)
        expected_body = [
            {
                u'proposal': 1,
                u'user': u'user1',
                u'line': u'message',
                u'timestamp': u'1989-02-07 00:30:00.000000'
            },
            {
                u'proposal': 1,
                u'user': u'user2',
                u'line': u'another message',
                u'timestamp': u'1989-02-07 00:30:01.000000'
            }
        ]
        self.assertEqual(loads(self.request_body), expected_body)
        self.assertEqual(self.target._buffer, [])

        self.post_deferred.callback(None)
        self.assertEqual(self.successResultOf(d), None)


EPOCH = datetime(1989, 2, 7, 00, 30)
ENCODED_EPOCH = u"1989-02-07 00:30:00.000000"
ONE_SECOND = timedelta(seconds=1)


def dates():
    """Generator that produces test dates.

    Starts at ``EPOCH``, adds one second each iteration.

    """
    date = EPOCH
    while True:
        yield date
        date += ONE_SECOND


class JSONDateTimeEncoderTests(unittest.TestCase):
    """Tests for datetime-aware JSON encoder.
    """
    def setUp(self):
        self.encoder = log.JSONDateTimeEncoder()

    def test_encode(self):
        encoded = self.encoder.encode({"datetime": EPOCH})
        expected = dumps({"datetime": ENCODED_EPOCH})
        self.assertEqual(encoded, expected)


class AutoFlushingLogTargetTests(unittest.TestCase):
    def setUp(self):
        self.wrapped_target = w = FakeLogTarget()
        self.clock = task.Clock()
        self.target = log.AutoFlushingLogTarget(w, _clock=self.clock)

    def test_log(self):
        """The log method is dispatched to the wrapped log target.
        """
        self.assertEqual(self.wrapped_target.logged_messages, [])
        args = 1, "nickname", "message"
        self.target.log(*args)
        self.assertEqual(self.wrapped_target.logged_messages, [args])

    def test_flush(self):
        """The flush method is dispatched to the wrapped log target.
        """
        self.assertEqual(self.wrapped_target.flushes, 0)
        d = self.target.flush()
        self.assertEqual(self.successResultOf(d), None)
        self.assertEqual(self.wrapped_target.flushes, 1)

    def test_autoflush(self):
        """The wrapped target is flushed automatically every 10 seconds.
        """
        self.assertEqual(self.wrapped_target.flushes, 0)
        self.clock.advance(10)
        self.assertEqual(self.wrapped_target.flushes, 1)
        self.clock.advance(5)
        self.assertEqual(self.wrapped_target.flushes, 1)
        self.clock.advance(5)
        self.assertEqual(self.wrapped_target.flushes, 2)


class FakeLogTarget(object):
    def __init__(self):
        self.logged_messages = []
        self.flushes = 0

    def log(self, proposal, nickname, message):
        self.logged_messages.append((proposal, nickname, message))

    def flush(self):
        self.flushes += 1
        return defer.succeed(None)
