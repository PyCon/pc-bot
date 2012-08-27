import mongoengine

class SiteVotes(mongoengine.EmbeddedDocument):
    """
    Votes on a talk on the site. Duplicated here for reporting purposes, should
    be considered read-only for the bots.
    """
    plus_1 = mongoengine.IntField(min_value=0)
    plus_0 = mongoengine.IntField(min_value=0)
    minus_0 = mongoengine.IntField(min_value=0)
    minus_1 = mongoengine.IntField(min_value=0)

class KittendomeVotes(mongoengine.EmbeddedDocument):
    """
    Records the votes on a talk in a Kittendome session.
    """
    yay = mongoengine.IntField(min_value=0)
    nay = mongoengine.IntField(min_value=0)
    abstain = mongoengine.IntField(min_value=0)

class TalkProposal(mongoengine.Document):
    STATUSES = [
        ('unreviewed',      'Unreviewed'),
        ('pre-rejected',    'Rejected at pre-season Kittendome'),
        ('rejected',        'Rejected'),
        ('thunderdome',     'Accepted into Thunderdome'),
        ('accepted',        'Accepted'),
        ('damaged',         'Damaged'),
    ]

    id = mongoengine.IntField(unique=True)
    title = mongoengine.StringField()
    status = mongoengine.StringField(choices=STATUSES)
    site_votes = mongoengine.EmbeddedDocumentField(SiteVotes)
    kittendome_votes = mongoengine.EmbeddedDocumentField(KittendomeVotes)
    debate_transcript = mongoengine.StringField()
