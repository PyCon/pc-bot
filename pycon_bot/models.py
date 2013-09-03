from pycon_bot.utils.api import API
from pycon_bot import settings


class ProposalManager(object):
    """Class that understands how to retrieve and filter proposals,
    acquired from the PyCon website.
    """
    def __init__(self):
        self.api = API()

    def filter(self, **kwargs):
        """Return a list of proposals."""
        kwargs.setdefault('type', 'talk')
        response = self.api.get('proposals', **kwargs)
        return [Proposal(**i) for i in response['data']]

    def get(self, id):
        """Return back a single proposal given the following ID.
        We do not filter on anything other than ID here.
        """
        response = self.api.get('proposals/%d' % int(id))
        return Proposal(**response['data'])

    def all(self):
        return self.filter()

    def talks(self):
        return self.filter(type='talk')

    def tutorials(self):
        return self.filter(type='tutorial')

    def lightning_talks(self):
        return self.filter(type='lightning_talk')

    def posters(self):
        return self.filter(type='poster')


class Proposal(object):
    """Object to represent proposal objects, which can be acted upon
    and saved back to the PyCon website.
    """
    objects = ProposalManager()

    def __init__(self, id, **kwargs):
        """Create a new proposal instance. This MUST have an ID
        to be valid; we do not create new proposals from nowhere
        for our purposes.
        """
        kwargs['id'] = int(id)
        self.__dict__.update({
            'api': API(),
            'data': kwargs,
        })

    def __getattr__(self, key):
        if key in self.data:
            return self.data[key]

    def __setattr__(self, key, value):
        raise AttributeError(''.join((
            'Attribute setting is not allowed.',
            'Write data with Proposal.write(). Note that, as of this writing,',
            'the *entire* data you save will replace what was in the "extra"',
            'dictionary before.',
        )))

    def __repr__(self):
        return repr(self.data)

    def write(self, data=None):
        """Write the given data to the PyCon API. If nothing is specified,
        the current value of self.extra is used.
        """
        data = data or self.extra
        if not isinstance(data, dict):
            raise TypeError(''.join((
                'Only JSON-serializable dictionaries may be written',
                'to the extra slot.',
            )))
        self.api.post('proposals/%d' % self.id, data)

