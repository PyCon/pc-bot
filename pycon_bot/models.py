from __future__ import unicode_literals
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
    """
    Records the votes on a talk in a Kittendome session.
    """
    yay = mongoengine.IntField(min_value=0, default=0)
    nay = mongoengine.IntField(min_value=0, default=0)
    abstain = mongoengine.IntField(min_value=0, default=0)

    def __unicode__(self):
        return u"%s/%s/%s" % (self.yay, self.nay, self.abstain)

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
        ('unreviewed',      'Unreviewed'),
        ('hold',            'On hold'),
        ('poster',          'Rejected (suggest poster)'),
        ('rejected',        'Rejected'),
        ('thunderdome',     'In Thunderdome'),
        ('accepted',        'Accepted'),
        ('damaged',         'Damaged'),
    ]
    KITTENDOME_RESULT_CHOICES = [
        ('thunderdome', 'Accepted to thunderdome'),
        ('hold',        'Held for re-review'),
        ('rejected',    'Rejected'),
        ('poster',      'Rejected (suggest poster)'),
    ]

    talk_id = mongoengine.IntField(unique=True)
    speaker = mongoengine.StringField()
    title = mongoengine.StringField()
    category = mongoengine.StringField()
    status = mongoengine.StringField(choices=STATUSES)
    notes = mongoengine.ListField(mongoengine.EmbeddedDocumentField(Note))
    site_votes = mongoengine.EmbeddedDocumentField(SiteVotes)
    kittendome_votes = mongoengine.EmbeddedDocumentField(KittendomeVotes)
    kittendome_transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))
    kittendome_result = mongoengine.StringField(choices=KITTENDOME_RESULT_CHOICES)
    grouped = mongoengine.BooleanField(default=False)

    def __unicode__(self):
        return u"#%s: %s" % (self.talk_id, self.title)

    @property
    def review_url(self):
        return 'http://us.pycon.org/2013/reviews/review/%s/' % self.talk_id

    @classmethod
    def next_unreviewed_talk(cls, after=None):
        qs = cls.objects(status='unreviewed').order_by('talk_id')
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
    """
    Records details about a meeting - when it starts/stops, which talks were
    debated, and the complete meeting transcript.
    """
    number = mongoengine.SequenceField()
    start = mongoengine.DateTimeField()
    end = mongoengine.DateTimeField()
    talks_decided = mongoengine.ListField(mongoengine.ReferenceField(TalkProposal))
    transcript = mongoengine.ListField(mongoengine.EmbeddedDocumentField(TranscriptMessage))

    def add_to_transcript(self, timestamp, user, message):
        t = TranscriptMessage(timestamp=timestamp, user=user, message=message)
        Meeting.objects(id=self.id).update_one(push__transcript=t)

class Group(mongoengine.Document):
    """
    A group of talks to be reviewed in one T-dome session.
    """
    number = mongoengine.SequenceField()
    name = mongoengine.StringField()
    talks = mongoengine.ListField(mongoengine.ReferenceField(TalkProposal))

    def __unicode__(self):
        return self.name if self.name else "Group #%s" % self.number

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
