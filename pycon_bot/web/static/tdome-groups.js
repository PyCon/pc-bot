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
var Talk = Backbone.Model.extend({
    idAttribute: "talk_id"
});

// A list of talks. The URL isn't set since this is used both to map to
// ungrouped talks (/api/talks/ungrouped) and also to talks within a group
// (/api/groups/{id}/talks).
var TalkCollection = FlaskCollection.extend({
    model: Talk,
    comparator: function(talk) {
        return talk.get('talk_id');
    }
});

// A thunderdome group.
var Group = Backbone.Model.extend({
    idAttribute: "number",
    initialize: function(attrs) {
        this.talks = new TalkCollection();
        this.talks.url = this.url() + '/talks';
    }
});

// The list of groups.
var GroupCollection = FlaskCollection.extend({
    model: Group,
    url: '/api/groups',
    comparator: function(group) {
        return group.get('number');
    }
});

//
// Views
//

// The set of selected talks. This is shared anywhere a TalkView might be
// rendered, so it needs to be a global. It's also not persisted anwyhere,
// so it hasn't got a URL.
selectedTalks = new TalkCollection();

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
        if (this.$el.hasClass('selected')) {
            selectedTalks.add(this.model);
        } else {
            selectedTalks.remove(this.model);
        }
    }
});

// The list of ungrouped talks down the side.
var TalkListView = Backbone.View.extend({
    el: $("#talks"),

    initialize: function() {
        this.collection.on('add', this.addOne, this);
        this.collection.on('reset', this.addAll, this);
        this.collection.on('all', this.render, this);
        this.collection.fetch();
    },

    addOne: function(talk) {
        var tv = new TalkView({model: talk});
        this.$('table').append(tv.render().el);
    },
    addAll: function() {
        this.collection.each(this.addOne, this);
    }
});

// A single group list item.
var GroupView = Backbone.View.extend({
    tagName: "li",
    attributes: {"class": "span5"},
    template: _.template($('#group-row-template').html()),

    events: {
        'click .add-talks': 'addTalksToGroup',
        'click .remove-group': 'removeThisGroup'
    },

    render: function() {
        this.$el.html(this.template(this.model.toJSON()));
        var tlv = new TalkListView({
            collection: this.model.talks,
            el: this.$el
        });
        return this;
    },

    addTalksToGroup: function() {
        alert('add ' + selectedTalks.pluck('talk_id') + ' to group ' + this.model.get('name'));
    },

    removeThisGroup: function() {
        this.$el.remove();
        this.model.destroy();
    }
});

// The group list view
var GroupListView = Backbone.View.extend({
    el: $("#groups"),

    events: {
        'click #new-group': 'addNewGroup'
    },

    initialize: function() {
        this.collection.bind('add', this.addOne, this);
        this.collection.bind('reset', this.addAll, this);
        this.collection.bind('all', this.render, this);
        this.collection.fetch();
    },

    addOne: function(group) {
        var gv = new GroupView({model: group, collection: this.collection});
        this.$('ul').append(gv.render().el);
    },

    addAll: function() {
        this.collection.each(this.addOne, this);
    },

    addNewGroup: function() {
        var g = {"name": "New Group", "talks": selectedTalks.toJSON()};
        this.collection.create(g);
        selectedTalks.reset([]);
    }
});

//
// main, as it were
//
var ungroupedTalks = new TalkCollection();
ungroupedTalks.url = '/api/talks/ungrouped';
var ungroupedTalksView = new TalkListView({collection: ungroupedTalks});
var groups = new GroupCollection();
var groupView = new GroupListView({collection: groups});

});
