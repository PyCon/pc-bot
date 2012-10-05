import barrel.cooper
import flask
import json
import math
import mongoengine
import mongoengine.queryset
import os
from datetime import datetime
from flask.ext.bootstrap import Bootstrap
from pycon_bot import mongo
from pycon_bot.models import Meeting, TalkProposal, Group

app = flask.Flask(__name__)
app.debug = 'PYCONBOT_DEBUG' in os.environ
Bootstrap(app)
mongo.connect()
if 'PYCONBOT_BASIC_AUTH' in os.environ:
    users = [os.environ['PYCONBOT_BASIC_AUTH'].split(':', 2)]
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
    talks_by_status = TalkProposal.objects.item_frequencies('status').items()
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
        meetings_left = int(math.ceil(float(remaining) / talks_per_meeting)),
        talks_by_status_json = json.dumps(talks_by_status),
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
        title = "All talks",
        talks = TalkProposal.objects.order_by('talk_id'))

@app.route('/talks/<int:n>')
def talk_detail(n):
    """View returning detailed information about a talk."""

    # set constants that should be outside the boundaries
    # of anything we ever actually care about
    LONG_TIME_AGO = datetime(1900, 1, 1, 0, 0, 0)
    LONG_TIME_FROM_NOW = datetime(2031, 12, 31, 23, 59, 59)

    # retrieve the talk
    talk = get_or_404(TalkProposal.objects, talk_id=n)
    transcripts = []

    # the transcripts are just stored by time, but I want
    #   to have some semblance of how to separate transcripts by
    #   various meetings
    # to do this, I need to divide up the transcript lines according
    #   to which meeting they belong to
    # TODO: Alter the data format to make this a more straightforward task.
    #   (because the current implementation is harder to read than it needs to be)
    meetings = list(Meeting.objects.all())
    cursor = -1
    dividing_line = LONG_TIME_AGO

    # iterate over each line in the transcript and assess
    # where it belongs
    for line in talk.kittendome_transcript:
        # first, check and make sure this isn't something
        # that actually belongs in the *next* meeting
        while line.timestamp > dividing_line:
            cursor += 1
            if len(meetings) > cursor:
                dividing_line = meetings[cursor].start
            else:
                dividing_line = LONG_TIME_FROM_NOW

            # also add a new list to `transcripts` so that the append
            # mechanism below hits the newest item
            if not len(transcripts) or len(transcripts[-1]):
                transcripts.append([])

        # at this point, we know that `transcripts` is a list of lists,
        # and that the last item in the list is where our line belongs,
        # so just shove it onto the stack
        transcripts[-1].append(line)

    return flask.render_template('talk_detail.html',
        talk=talk,
        transcripts=transcripts,
    )

@app.route('/talks/<string:status>')
def talks_by_status(status):
    statuses = dict(TalkProposal.STATUSES)
    if status not in statuses:
        flask.abort(404)
    return flask.render_template('talk_list.html',
        title = statuses[status],
        talks = TalkProposal.objects.filter(status=status).order_by('talk_id'))

@app.route('/tdome/groups')
def tdome_groups():
    return flask.render_template('tdome_groups.html',
        groups = Group.objects.all().select_related(),
        ungrouped = TalkProposal.objects.filter(status="thunderdome", grouped__ne=True).order_by('talk_id')
    )

@app.route('/tdome/groups/add')
def tdome_add_group():
    g, created = Group.objects.get_or_create(title=flask.request.form['title'])
    return flask.jsonify({'group': g.id})

@app.route('/tdome/groups/assign')
def tdome_assign_talk():
    g = Group.objects.get(id=flask.request.form['group'])
    t = TalkProposal.objects.get(talk_id=flask.request.form['talk'])
    g.talks.append(t)
    g.save()
    flask.abort(204)

def get_or_404(qs, *args, **kwargs):
    try:
        return qs.get(*args, **kwargs)
    except mongoengine.queryset.DoesNotExist:
        flask.abort(404)

if __name__ == '__main__':
    app.run()
