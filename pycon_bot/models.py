from __future__ import unicode_literals, division
from datetime import datetime
import mongoengine

class SiteVotes(mongoengine.EmbeddedDocument):
    """
    Votes on a talk on the site. Duplicated here for reporting purposes, should
    be considered read-only for the bots.
    """
    plus_1 = mongoengine.IntField(min_value=0, default=0)
    plus_0 = mongoengine.IntField(min_value=0, default=0)
    minus_0 = mongoengine.IntField(min_value=0, default=0)
    minus_1 = mongoengine.IntField(min_value=0, default=0)

    def __unicode__(self):
        return u"%s/%s/%s/%s" % (self.plus_1, self.plus_0, self.minus_0, self.minus_1)

    @property
    def total(self):
        return self.plus_1 + self.plus_0 + self.minus_0 + self.minus_1

class KittendomeVotes(mongoengine.EmbeddedDocument):
    """Records the votes on a talk in a Kittendome session."""
    yay = mongoengine.IntField(min_value=0, default=0)
    nay = mongoengine.IntField(min_value=0, default=0)
    abstain = mongoengine.IntField(min_value=0, default=0)

    def __unicode__(self):
        return u"%s/%s/%s" % (self.yay, self.nay, self.abstain)


class ThunderdomeVotes(mongoengine.EmbeddedDocument):
    """Records the votes on a talk in a Thunderdome session."""

    supporters = mongoengine.IntField(min_value=0, default=0)
    attendees = mongoengine.IntField(min_value=0, default=0)

    def __unicode__(self):
        return u'{0:.1d}%'.format(self.percent)

    @property
    def percent(self):
        try:
            return 100 * self.supporters / self.attendees
        except ZeroDivisionError:
            return None

    @property
    def vote_result(self):
        """Return the expected the result based on the votes."""

        # return the appropriate result text
        # this is based solely on the votes; it may not
        #   and need not match the chair decision
        if self.percent >= 75.0:
            return 'accepted'
        if self.percent >= 50.0:
            return 'damaged'
        return 'rejected'


class TranscriptMessage(mongoengine.EmbeddedDocument):
    """
    A single IRC message - used for transcripts.
    """
    timestamp = mongoengine.DateTimeField()
    user = mongoengine.StringField()
    message = mongoengine.StringField()

    def __unicode__(self):
        return u"[%s] <%s> %s" % (self.timestamp.strftime('%H:%M:%S'), self.user, self.message)


class Note(mongoengine.EmbeddedDocument):
    """Notes left, usually manually, about a given talk. For record-keeping."""

    text = mongoengine.StringField()
    timestamp = mongoengine.DateTimeField(default=datetime.now)

    def __unicode__(self):
        return unicode(self.text)


class TalkProposal(mongoengine.Document):
    STATUSES = [
        ('accepted',    'Accepted'),
        ('damaged',     'Damaged'),
        ('hold',        'On hold'),
        ('rejected',    'Rejected'),
        ('unreviewed',  'Unreviewed'),
        ('thunderdome', 'In Thunderdome'),
    ]
    KITTENDOME_RESULT_CHOICES = [
        ('hold',        'Held for re-review'),
        ('rejected',    'Rejected'),
        ('thunderdome', 'Accepted to thunderdome'),
    ]
    THUNDERDOME_RESULT_CHOICES = [
        ('accepted', 'Accepted'),
        ('damaged', 'Damaged'),
        ('rejected', 'Rejected'),
        ('hold', 'On hold'),
    ]
    TALK_ALTERNATIVES = [
        ('lightning',  'Lightning Talk'),
        ('open_space', 'Open Space'),
        ('poster',     'Poster'),
    ]

    talk_id = mongoengine.IntField(unique=True)
    speaker = mongoengine.StringField()
    title = mongoengine.StringField()
    category = mongoengine.StringField()
    status = mongoengine.StringField(choices=STATUSES)
    alternative = mongoengine.StringField(choices=TALK_ALTERNATIVES)
    notes = mongoengine.ListField(mongoengine.EmbeddedDocumentField(Note))
    site_votes = mongoengine.EmbeddedDocumentField(SiteVotes)
    kittendome_votes = mongoengine.EmbeddedDocumentField(KittendomeVotes)
    kittendome_transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))
    kittendome_result = mongoengine.StringField(choices=KITTENDOME_RESULT_CHOICES)
    thunderdome_votes = mongoengine.EmbeddedDocumentField(ThunderdomeVotes)
    thunderdome_transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))
    thunderdome_result = mongoengine.StringField(choices=THUNDERDOME_RESULT_CHOICES)
    grouped = mongoengine.BooleanField(default=False)

    def __unicode__(self):
        return u"#%s: %s" % (self.talk_id, self.title)

    def __lt__(self, other):
        return self.talk_id < other.talk_id

    def __gt__(self, other):
        return self.talk_id > other.talk_id

    @property
    def review_url(self):
        return 'http://us.pycon.org/2013/reviews/review/{0}/'.format(self.talk_id)

    @property
    def decision(self):
        if self.status == 'rejected' and self.alternative:
            return 'rejected ({0})'.format(self.alternative)
        else:
            return self.status

    @property
    def kittendome_decision(self):
        if self.kittendome_result == 'rejected' and self.alternative:
            return "rejected (%s)" % self.alternative
        else:
            return self.kittendome_result

    @property
    def agenda_format(self):
        return "#%s - %s - %s\n%s\n" % (self.talk_id, self.title, self.speaker, self.review_url)

    @classmethod
    def next_unreviewed_talk(cls, after=None):
        qs = cls.objects(status__in=('unreviewed', 'hold')).order_by('talk_id')
        if after:
            qs = qs.filter(id__ne=after.id)
        return qs[0]

    def add_to_transcript(self, timestamp, user, message):
        """
        Convienience function to append a line to the Kittendome transcript.
        """
        t = TranscriptMessage(timestamp=timestamp, user=user, message=message)
        TalkProposal.objects(id=self.id).update_one(push__kittendome_transcript=t)

class Meeting(mongoengine.Document):
    """Records details about a meeting - when it starts/stops, which talks were
    debated, and the complete meeting transcript."""

    number = mongoengine.SequenceField()
    start = mongoengine.DateTimeField()
    end = mongoengine.DateTimeField()
    talks_decided = mongoengine.ListField(mongoengine.ReferenceField(TalkProposal))
    transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))

    def add_to_transcript(self, timestamp, user, message):
        t = TranscriptMessage(timestamp=timestamp, user=user, message=message)
        Meeting.objects(id=self.id).update_one(push__transcript=t)


class Group(mongoengine.Document):
    """A group of talks to be reviewed in one Thunderdome session."""

    number = mongoengine.SequenceField()
    name = mongoengine.StringField()
    talks = mongoengine.ListField(mongoengine.ReferenceField(TalkProposal))
    decided = mongoengine.BooleanField(default=False)
    transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))

    def __unicode__(self):
        return self.name if self.name else "Group #%s" % self.number

    @property
    def talk_ids(self):
        """Return a set with the talk IDs in this particular group."""
        return set([i.talk_id for i in self.talks])

    @property
    def undecided_talks(self):
        """Return a list of talks that do not have a `thunderdome_result` set."""
        return [i for i in self.talks if not i.thunderdome_result]

    @property
    def agenda_format(self):
        answer = '"{name}"\n\n'.format(name=self.name)
        for talk in self.talks:
            answer += '    {0}\n'.format(talk.agenda_format.replace('\n', '\n    '))
        return answer

    @classmethod
    def next_undecided_group(cls, after=None):
        """Return the next undecided group in the system."""

        queryset = cls.objects.filter(decided__ne=True)
        if after:
            queryset = queryset.filter(id__ne=after.id)
        return queryset[0]
        
    def add_to_transcript(self, timestamp, user, message):
        """Log the given message to the transcript for both
        this group and each individual talk proposal within the group."""

        # create the transcript message object itself
        t = TranscriptMessage(timestamp=timestamp, user=user, message=message)

        # log the message to the transcript for the group itself
        Group.objects(id=self.id).update_one(push__transcript=t)

        # log the message for each individual talk proposal within the group
        for talk in self.talks:
            TalkProposal.objects(id=talk.id).update_one(push__thunderdome_transcript=t)

    def talk_by_id(self, talk_id):
        """Return the talk represented by `talk_id`. If the talk is not
        in this group, raise ValueError."""
        talk_id = int(talk_id)
        for talk in self.talks:
            if talk.talk_id == talk_id:
                return talk
        raise ValueError, 'Talk #{0} not found in this group'.format(talk_id)

    def add_talk_id(self, talk_id):
        """Add the talk given by talk_id to this group, making sure it's not in
        another group and that it's marked "grouped" correctly. Do this as
        atomically as possible."""

        # from the talk id, retrieve the talk
        talk_id = int(talk_id)
        t = TalkProposal.objects.get(talk_id=talk_id)

        # Remove the talk from any existing groups
        Group.objects.filter(talks=t).update(pull__talks=t)

        # Add the talk to this group (but only if it's not already there)
        self.update(add_to_set__talks=t)

        # Set the "grouped" flag on the talk.
        t.update(set__grouped=True)

    def talks_by_decision(self):
        """
        Return a dict of {decision: [talk, talk, ...]} containing all the talks
        in this group. Keys will be one of TalkProposal.THUNDERDOME_RESULT_CHOICES,
        or "undecided".
        """
        d = {}
        for talk in self.talks:
            key = talk.thunderdome_result or "undecided"
            d.setdefault(key, []).append(talk)
        return d


def doc2dict(doc, fields=None):
    """
    Convert a doc to a dictionary suitable for JSON-encoding.
    """
    # Which fields to encode?
    if fields is None:
        fields = doc._fields.keys()

    d = {}
    for name in fields:
        field = doc._fields[name]
        value = getattr(doc, name)

        # Convert ObjectIDs to strings
        if value and isinstance(field, mongoengine.ObjectIdField):
            d[name] = str(value)

        # Handle embededded documents by recursively dict-ifying
        elif value and isinstance(field, mongoengine.EmbeddedDocumentField):
            d[name] = doc2dict(value)

        # List fields, two cases:
        elif value and isinstance(field, mongoengine.ListField):

            # If it's an embedded document or a ref, then the dict-ify
            # each item in the list.
            if isinstance(field.field, (mongoengine.EmbeddedDocumentField,
                                        mongoengine.ReferenceField)):
                d[name] = [doc2dict(v) for v in value]

            # Otherwise, just make a copy of the list.
            else:
                d[name] = list(value)

        # Everything else: hope json.dump can handle it :)
        else:
            d[name] = value

    return d