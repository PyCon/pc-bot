$(function() {

//
// Models
//

// Base class for handling flask.jsonify-style JSON.
var FlaskCollection = Backbone.Collection.extend({
    parse: function(resp, xhr) {
        return resp.objects;
    }
});

// An individual Talk object.
var Talk = Backbone.Model.extend({});

// A list of talks.
var TalkList = FlaskCollection.extend({
    model: Talk,
    url: '/api/talks/ungrouped',
    comparator: function(talk) {
        return talk.get('talk_id');
    }
});

// A thunderdome group.
var Group = Backbone.Model.extend({
    initialize: function() {
        this.talks = new TalkList();
        this.talks.url = this.url() + '/talks';
        // this.talks.on("reset", ...)
    }
});

// The list of groups.
var GroupList = FlaskCollection.extend({
    model: Group,
    url: '/api/groups',
    comparator: function(group) {
        return group.get('number');
    }
});

//
// Views
//

// A single talk row.
var TalkView = Backbone.View.extend({
    tagName: "tr",
    template: _.template($('#talk-row-template').html()),

    events: {
        "click": "toggleSelect"
    },

    render: function() {
        this.$el.html(this.template(this.model.toJSON()));
        return this;
    },

    toggleSelect: function() {
        this.$el.toggleClass('selected');
    }
});

// The list of ungrouped talks down the side.
var UngroupedTalkListView = Backbone.View.extend({
    el: $("#select-talks"),

    initialize: function() {
        UngroupedTalks.bind('add', this.addOne, this);
        UngroupedTalks.bind('reset', this.addAll, this);
        UngroupedTalks.bind('all', this.render, this);
    },

    addOne: function(talk) {
        var tv = new TalkView({model: talk});
        UngroupedTalkList.$el.append(tv.render().el);
    },
    addAll: function() {
        UngroupedTalks.each(this.addOne);
    }
});

// A single group list item.
var GroupView = Backbone.View.extend({
    tagName: "li",
    template: _.template($('#talk-row-template').html()),

    render: function() {
        this.$el.html(this.template(this.model.toJSON()));

    }
});

//
// main, as it were
//
var UngroupedTalks = new TalkList();
var UngroupedTalkList = new UngroupedTalkListView();
UngroupedTalks.fetch();

});
