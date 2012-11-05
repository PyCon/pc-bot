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

    def __unicode__(self):
        return u"#%s: %s" % (self.talk_id, self.title)

    @property
    def review_url(self):
        return 'http://us.pycon.org/2013/reviews/review/%s/' % self.talk_id

    @property
    def decision(self):
        if self.status == 'rejected' and self.alternative:
            return "rejected (%s)" % self.alternative
        else:
            return self.status

    @property
    def kittendome_decision(self):
        if self.kittendome_result == 'rejected' and self.alternative:
            return "rejected (%s)" % self.alternative
        else:
            return self.kittendome_result

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
