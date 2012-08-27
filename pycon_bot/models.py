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

class TalkProposal(mongoengine.Document):
    STATUSES = [
        ('unreviewed',      'Unreviewed'),
        ('hold',            'On hold'),
        ('poster',          'Rejected, suggest poster session'),
        ('rejected',        'Rejected'),
        ('thunderdome',     'Accepted into Thunderdome'),
        ('accepted',        'Accepted'),
        ('damaged',         'Damaged'),
    ]

    talk_id = mongoengine.IntField(unique=True)
    speaker = mongoengine.StringField()
    title = mongoengine.StringField()
    category = mongoengine.StringField()
    status = mongoengine.StringField(choices=STATUSES)
    site_votes = mongoengine.EmbeddedDocumentField(SiteVotes)
    kittendome_votes = mongoengine.EmbeddedDocumentField(KittendomeVotes)
    debate_transcript = mongoengine.StringField()

    def __unicode__(self):
        return u"#%s: %s" % (self.talk_id, self.title)

    @property
    def review_url(self):
        return 'http://us.pycon.org/2013/reviews/review/%s/' % self.talk_id
