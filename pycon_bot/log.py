from datetime import datetime
from json import JSONEncoder
from treq import post
from twisted.internet import defer
from zope import interface


class ILogTarget(interface.Interface):
    """
    A target for IRC logs related to a proposal.
    """
    def log(proposal, nickname, message):
        """Logs a channel message related to a proposal.

        This might only buffer the message; see ``flush``.
        """

    def flush():
        """Flushes all logged channel messages.

        This should return a deferred that fires when the messages have been
        flushed. If this log target doesn't require flushing, it should return
        a deferred that is already fired.

        """

@interface.implementer(ILogTarget)
class PyConSiteLogTarget(object):
    """A log target that logs to the PyCon site.
    """
    _utcnow = staticmethod(datetime.utcnow)
    _post = staticmethod(post)

    def __init__(self, host, auth_key):
        """Initializes the PyCon site log target.
        """
        path = "/pycon_api/set_irc_logs/{key}/".format(key=auth_key)
        self._url = "https://" + host + path
        self._buffer = []
        self._encoder = JSONDateTimeEncoder()

    def log(self, proposal, nickname, message):
        """Buffers a message for logging.
        """
        self._buffer.append({
            u"proposal": proposal,
            u"user": nickname,
            u"line": message,
            u"timestamp": self._utcnow()
        })

    def flush(self):
        """Sends all buffered logs.
        """
        if not self._buffer:
            return defer.succeed(None)

        to_send, self._buffer = self._buffer, []
        return self._post(self._url, self._encoder.encode(to_send))


DATETIME_FORMAT = u"%Y-%m-%d %H:%M:%S.%f"


class JSONDateTimeEncoder(JSONEncoder):
    """JSON encoder that also encodes datetime objects.
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime(DATETIME_FORMAT)
        else:
            return JSONEncoder.encode(self, obj)
