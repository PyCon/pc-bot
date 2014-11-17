from __future__ import division
from pycon_bot import settings
from pycon_bot.utils.api import API
from pycon_bot.utils.exceptions import NotFound


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
        try:
            response = self.api.get('proposals/%d' % int(id))
        except NotFound:
            raise Proposal.DoesNotExist('No proposal with ID %d.' % int(id))
        return Proposal(**response['data'])

    def next(self, type=None, status=None, after=None):
        """Return the next talk that should be reviewed.

        Right now the API has some limitations, so this is super bonus janky.
        It basically gets all the talks and then iterates until it finds
        the right one.
        """
        # First, what kind of talk are we looking at?
        manager_method = 'all'
        if type:
            manager_method = type + 's'

        # Get the list of talks.
        proposals = getattr(self, manager_method)()

        # Iterate over the proposals we got back until we get
        # the one we want.
        for proposal in proposals:
            # If the status isn't what I expect, keep going.
            if proposal.status != status:
                continue

            # If the proposal ID is too low, keep going.
            if proposal.id <= after:
                continue

            # Return this talk!
            return proposal

        # Whups, we didn't find what we wanted; complain.
        raise Proposal.DoesNotExist('No more talks!')

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

    class DoesNotExist(Exception):
        pass

    def __init__(self, id, **kwargs):
        """Create a new proposal instance. This MUST have an ID
        to be valid; we do not create new proposals from nowhere
        for our purposes.
        """
        kwargs['id'] = int(id)
        kwargs['thunderdome_votes'] = None
        kwargs['decided'] = False
        self.__dict__.update({
            'api': API(),
            'data': kwargs,
        })

    def __getattr__(self, key):
        if key in self.data:
            return self.data[key]
        raise KeyError('No key %s in proposal #%d.' % (key, self.id))

    def __setattr__(self, key, value):
        raise AttributeError('Attribute setting is not allowed.')

    def __repr__(self):
        return repr(self.data)

    @property
    def agenda_format(self):
        return u'#{id} - {title} - {author}\n{review_url}\n'.format(
            author=unicode(self.speakers[0]['name']),
            id=self.id,
            title=unicode(self.title),
            review_url=self.review_url,
        )

    @property
    def public_url(self):
        return 'https://us.pycon.org/2015/schedule/presentation/%d/' % self.id

    @property
    def review_url(self):
        return 'http://us.pycon.org/2015/reviews/review/%d/' % self.id

    @property
    def template_context(self):
        answer = {}
        answer.update(self.data)
        answer['public_url'] = self.public_url
        answer['speaker'] = self.speakers[0]['name']
        return answer

    def set_status(self, status):
        # Sanity check: Is this a valid status?
        if status not in ('accepted', 'standby', 'rejected', 'undecided'):
            raise ValueError('Bad status: %s.' % status)

        # Set the status on the PyCon site.
        self.api.post('proposals/%d' % self.id, {'status': status})

        # Denote that this talk has been decided.
        self.data['status'] = status
        self.data['decided'] = True

    def set_thunderdome_votes(self, supporters, total_voters):
        self.data['thunderdome_votes'] = ThunderdomeVotes(
            supporters=supporters,
            total_voters=total_voters,
        )

    def accept(self):
        return self.set_status('accepted')

    def reject(self):
        return self.set_status('rejected')

    def standby(self):
        return self.set_status('standby')

    def undecide(self):
        return self.set_status('undecided')


class ThunderdomeGroupManager(object):
    """Class that understands how to retrieve and filter thunderdome groups,
    acquired from the PyCon website.
    """
    def __init__(self):
        self.api = API()

    def all(self):
        return self.filter()

    def filter(self, undecided=False):
        """Return a list of thunderdome groups, optionally filtering out
        groups that have already been decided.
        """
        kwargs = {}
        if undecided:
            kwargs['undecided'] = undecided

        response = self.api.get('thunderdome_groups', **kwargs)
        return [ThunderdomeGroup(**i) for i in response['data']]

    def get(self, code):
        """Return back a single proposal given the following code.
        We do not filter on anything other than code here.
        """
        try:
            response = self.api.get('thunderdome_groups/%s' % code)
        except NotFound:
            raise ThunderdomeGroup.DoesNotExist('No group with code %s.'
                                                % code)
        return ThunderdomeGroup(**response['data'])

    def next(self, undecided=True):
        """Return the next thunderdome group that should be decided."""

        try:
            return self.filter(undecided=True)[1]
        except KeyError:
            return None


class ThunderdomeGroup(object):
    """Object to represent proposal objects, which can be acted upon
    and saved back to the PyCon website.
    """
    objects = ThunderdomeGroupManager()

    class DoesNotExist(Exception):
        pass

    def __init__(self, code, talks=(), **kwargs):
        """Create a new thunderdome group instance. This MUST have a code
        to be valid; we do not create new groups or proposals from nowhere
        for our purposes.
        """
        # Iterate over the talks and make Proposal objects from each.
        talks_ = []
        for t in talks:
            talks_.append(Proposal(**t))
        kwargs['talks'] = talks_

        # Set the code.
        kwargs['code'] = code

        # Set an empty decision object.
        kwargs['decision'] = {}

        # Write the things to the object.
        self.__dict__.update({
            'api': API(),
            'data': kwargs,
        })

    def __getattr__(self, key):
        if key in self.data:
            return self.data[key]
        raise KeyError('No key %s in proposal #%d.' % (key, self.id))

    def __setattr__(self, key, value):
        raise AttributeError('Attribute setting is not allowed.')

    def __repr__(self):
        return repr(self.data)

    @property
    def agenda_format(self):
        answer = u'  --- {label} ---\n'.format(label=self.label)
        for talk in self.talks:
            answer += '\n    ' + talk.agenda_format.replace('\n', '\n    ')
        return answer

    @property
    def talk_ids(self):
        return [i.id for i in self.talks]

    @property
    def undecided_talks(self):
        decided_talks = set(self.decision.keys())
        return set(self.talk_ids).difference(decided_talks)

    def certify(self):
        """Send the results to the PyCon server."""
        self.api.post('thunderdome_groups/%s' % self.code, {
            'talks': [[id, status.replace('damaged', 'standby')]
                      for id, status in self.decision.items()],
        })

    def decide_talk(self, talk_id, status):
        """Record a decision for a particular talk within this
        thunderdome group.
        """
        # Sanity check: Does this talk exist in this group?
        if talk_id not in self.talk_ids:
            raise ValueError('Invalid talk ID.')

        # Save the decision.
        self.data['decision'][talk_id] = status


class ThunderdomeVotes(object):
    def __init__(self, supporters, total_voters):
        self.supporters = supporters
        self.total_voters = total_voters

    @property
    def percent(self):
        return (self.supporters / self.total_voters) * 100

    @property
    def vote_result(self):
        if self.percent >= 80:
            return 'accepted'
        if self.percent >= 60:
            return 'damaged'
        else:
            return 'rejected'
