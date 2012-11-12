import barrel.cooper
import flask
import functools
import json
import math
import mongoengine
import mongoengine.queryset
import os
from datetime import datetime
from flask.ext.bootstrap import Bootstrap
from pycon_bot import mongo
from pycon_bot.models import Meeting, TalkProposal, Group, doc2dict

app = flask.Flask(__name__)
app.debug = 'PYCONBOT_DEBUG' in os.environ
Bootstrap(app)
mongo.connect()

#
# Auth.
#
# If PYCONBOT_BASIC_AUTH is set, then it's a list of user/pass
# pairs (of the form "user:pass;user2:pass2") to protect the app with basic
# auth. If any of those users match users in PYCONBOT_SUPERUSERS, they're
# admins and can do awesome admin stuff.
#
if 'PYCONBOT_BASIC_AUTH' in os.environ:
    users = [userpass.split(':', 1) for userpass in os.environ['PYCONBOT_BASIC_AUTH'].split(';')]
    auth = barrel.cooper.basicauth(users=users, realm='PCbot')
    app.wsgi_app = auth(app.wsgi_app)

    SUPERUSERS = os.environ.get('PYCONBOT_SUPERUSERS', '').split(',')

    def requires_superuser(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            if flask.request.authorization['username'] not in SUPERUSERS:
                flask.abort(403)
            return func(*args, **kwargs)

        return inner

    @app.context_processor
    def inject_superuser():
        return {'user_is_superuser': flask.request.authorization['username'] in SUPERUSERS}

else:
    def requires_superuser(func):
        return func

    @app.context_processor
    def inject_superuser():
        return {'user_is_superuser': True}

@app.route('/')
def index():
    total = len(TalkProposal.objects)
    reviewed = len(TalkProposal.objects(status__ne='unreviewed'))
    remaining = total - reviewed
    accepted = len(TalkProposal.objects(kittendome_result='thunderdome'))
    rejected = len(TalkProposal.objects(kittendome_result='rejected'))
    number_of_meetings = len(Meeting.objects)
    talks_per_meeting = float(reviewed) / number_of_meetings

    groups_total = len(Group.objects)
    groups_reviewed = len(Group.objects(decided=True))
    tdome_results = {}
    for result in ('accepted', 'damaged', 'rejected'):
        c = len(TalkProposal.objects(thunderdome_result=result))
        tdome_results[result] = {
            'count': c,
            'percent': float(c)/accepted
        }

    talks_by_status = TalkProposal.objects.item_frequencies('status')
    talks_by_status.update(TalkProposal.objects.item_frequencies('alternative'))
    talks_by_status.pop(None)
    talks_by_status['rejected'] -= sum(talks_by_status.get(k, 0) for k,v in TalkProposal.TALK_ALTERNATIVES)
    talks_by_status = sorted(talks_by_status.items())

    return flask.render_template('index.html',
        total = total,
        reviewed = reviewed,
        remaining = remaining,
        kittendome_complete = (remaining == 0),
        percent_reviewed = float(reviewed) / total,
        accepted = accepted,
        percent_accepted = (float(accepted) / reviewed) if reviewed else 0,
        rejected = rejected,
        percent_rejected = (float(rejected) / reviewed) if reviewed else 0,
        number_of_meetings = number_of_meetings,
        talks_per_meeting = talks_per_meeting,
        meetings_left = int(math.ceil(float(remaining) / talks_per_meeting)),
        talks_by_status_json = json.dumps(talks_by_status),
        groups_total = groups_total,
        groups_reviewed = groups_reviewed,
        groups_remaining = groups_total - groups_reviewed,
        groups_reviewed_percent = float(groups_reviewed) / groups_total,
        thunderdome_results = tdome_results,
    )


@app.route('/meetings')
def meeting_list():
    return flask.render_template('meeting_list.html',
        meetings = Meeting.objects.order_by('-number').exclude('transcript', 'talks_decided'),
        meeting = None)


@app.route('/meetings/<int:n>')
def meeting_detail(n):
    return flask.render_template('meeting_detail.html',
        meetings = Meeting.objects.order_by('-number').exclude('transcript', 'talks_decided'),
        meeting = get_or_404(Meeting.objects, number=n))


@app.route('/talks')
def talk_list():
    talks = TalkProposal.objects.exclude('notes', 'kittendome_transcript') \
                                .order_by('talk_id')
    return flask.render_template('talk_list.html',
        title = "All talks",
        talks = talks,
        statuses = sorted(TalkProposal.STATUSES + TalkProposal.TALK_ALTERNATIVES),
    )

@app.route('/talks/<int:n>')
def talk_detail(n):
    """View returning detailed information about a talk."""

    # retrieve the talk
    talk = get_or_404(TalkProposal.objects, talk_id=n)

    return flask.render_template('talk_detail.html',
        talk=talk,
    )

@app.route('/talks/<string:status>')
def talks_by_status(status):

    if status in [k for k,v in TalkProposal.STATUSES]:
        talks = TalkProposal.objects.filter(status=status)
    elif status in [k for k,v in TalkProposal.TALK_ALTERNATIVES]:
        talks = TalkProposal.objects.filter(alternative=status)
    else:
        flask.abort(404)

    talks = talks.order_by('talk_id').exclude('notes', 'kittendome_transcript').order_by('talk_id')
    statuses = dict(TalkProposal.STATUSES + TalkProposal.TALK_ALTERNATIVES)

    return flask.render_template('talk_list.html',
        title = statuses[status],
        talks = talks,
        statuses = TalkProposal.STATUSES + TalkProposal.TALK_ALTERNATIVES,
        current_status = status
    )

@app.route('/thunderdome/groups')
def thunderdome_group_list():
    return flask.render_template('thunderdome_group_list.html',
        groups = Group.objects.order_by('number').select_related(),
        title = "all groups",
    )

@app.route('/thunderdome/groups/undecided')
def thunderdome_undecided_groups():
    return flask.render_template('thunderdome_group_list.html',
        groups = Group.objects.filter(decided__ne=True).order_by('number').select_related(),
        title = "undecided groups",
    )

@app.route('/thunderdome/groups/decided')
def thunderdome_decided_groups():
    return flask.render_template('thunderdome_group_list.html',
        groups = Group.objects.filter(decided=True).order_by('number').select_related(),
        title = "decided groups",
    )

@app.route('/thunderdome/groups/<int:g>')
def thunderdome_group_detail(g):
    return flask.render_template('thunderdome_group_detail.html',
        group = get_or_404(Group.objects, number=g)
    )

@app.route('/thunderdome/manage')
@requires_superuser
def manage_thunderdome():
    ungrouped = _get_ungrouped_talks()
    return flask.render_template('manage_thunderdome.html',
        groups = Group.objects.all().select_related(),
        ungrouped = ungrouped
    )

@app.route('/api/talks/ungrouped')
def api_talks_ungrouped():
    return _jsonify_talks(_get_ungrouped_talks())

@app.route('/api/groups')
def api_groups():
    return flask.jsonify(objects=[
        doc2dict(g, fields=('number', 'name'))
        for g in Group.objects.all()
    ])

@app.route('/api/groups', methods=['POST'])
@requires_superuser
def new_group():
    g = Group.objects.create(name=flask.request.json['name'])
    for talk_id in flask.request.json['talks']:
        g.add_talk_id(talk_id)
    return flask.jsonify(doc2dict(g, fields=('number', 'name')))

@app.route('/api/groups/<int:n>', methods=['PUT'])
@requires_superuser
def update_group(n):
    g = get_or_404(Group.objects, number=n)

    # Update name if given. Note that we don't update the number because
    # that's weird and I don't want to think through the ramifications.
    if 'name' in flask.request.json:
        g.update(set__name=flask.request.json['name'])

    # For each talk we have to remove it from an exsting group, if neccisary,
    # add it to this group, and make sure to mark it grouped.
    for talk_id in flask.request.json.get('talks', []):
        g.add_talk_id(talk_id)

    return flask.jsonify(doc2dict(g, fields=('number', 'name')))

@app.route('/api/groups/<int:n>', methods=['DELETE'])
@requires_superuser
def delete_group(n):
    g = get_or_404(Group.objects, number=n)
    for t in g.talks:
        t.grouped = False
        t.save()
    g.delete()
    return ("", 204)

@app.route('/api/groups/<int:n>/talks')
def api_group_talks(n):
    g = get_or_404(Group.objects, number=n)
    return _jsonify_talks(g.talks)

def _get_ungrouped_talks():
    return TalkProposal.objects.filter(status="thunderdome", grouped__ne=True) \
                               .only('talk_id', 'title') \
                               .order_by('talk_id')

def _jsonify_talks(tl):
    return flask.jsonify(objects=[
        doc2dict(t, fields=('talk_id', 'title')) for t in tl
    ])

def get_or_404(qs, *args, **kwargs):
    try:
        return qs.get(*args, **kwargs)
    except mongoengine.queryset.DoesNotExist:
        flask.abort(404)

# Force debug if run as main (i.e. python -m pycon_bot.web.app)
if __name__ == '__main__':
    app.debug = True
    app.run()
