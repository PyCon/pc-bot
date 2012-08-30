import os
import math
import flask
import barrel.cooper
import mongoengine
import mongoengine.queryset
from flask.ext.bootstrap import Bootstrap
from pycon_bot import mongo
from pycon_bot.models import Meeting, TalkProposal

app = flask.Flask(__name__)
app.debug = 'DEBUG' in os.environ
Bootstrap(app)
mongo.connect()
if 'PCBOT_AUTH' in os.environ:
    users = [os.environ['PCBOT_AUTH'].split(':', 2)]
    auth = barrel.cooper.basicauth(users=users, realm='PCbot')
    app.wsgi_app = auth(app.wsgi_app)

@app.route('/')
def index():
    total = len(TalkProposal.objects)
    reviewed = len(TalkProposal.objects(status__ne='unreviewed'))
    remaining = total - reviewed
    accepted = len(TalkProposal.objects(status__in=('thunderdome', 'accepted')))
    rejected = len(TalkProposal.objects(status__in=('rejected', 'posted')))
    number_of_meetings = len(Meeting.objects)
    talks_per_meeting = float(reviewed) / number_of_meetings
    return flask.render_template('index.html',
        total = total,
        reviewed = reviewed,
        remaining = remaining,
        percent_reviewed = float(reviewed) / total,
        accepted = accepted,
        percent_accepted = (float(accepted) / reviewed) if reviewed else 0,
        rejected = rejected,
        percent_rejected = (float(rejected) / reviewed) if reviewed else 0,
        number_of_meetings = number_of_meetings,
        talks_per_meeting = talks_per_meeting,
        meetings_left = int(math.ceil(float(remaining) / talks_per_meeting))
    )

@app.route('/meetings')
def meeting_list():
    return flask.render_template('meeting_list.html',
        meetings = Meeting.objects.order_by('number'),
        meeting = None)

@app.route('/meetings/<int:n>')
def meeting_detail(n):
    return flask.render_template('meeting_detail.html',
        meetings = Meeting.objects.order_by('number'),
        meeting = get_or_404(Meeting.objects, number=n))

@app.route('/talks')
def talk_list():
    return flask.render_template('talk_list.html',
        talks=TalkProposal.objects.order_by('talk_id'))

@app.route('/talks/<int:n>')
def talk_detail(n):
    return flask.render_template('talk_detail.html',
        talk=get_or_404(TalkProposal.objects, talk_id=n))

def get_or_404(qs, *args, **kwargs):
    try:
        return qs.get(*args, **kwargs)
    except mongoengine.queryset.DoesNotExist:
        flask.abort(404)

if __name__ == '__main__':
    app.run()
