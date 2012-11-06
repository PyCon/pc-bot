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
        this.talks = new TalkCollection(attrs.talks);
        this.talks.url = this.url() + '/talks';
    },

    toJSON: function() {
        var json = Backbone.Model.prototype.toJSON.call(this);
        json['talks'] = this.talks.pluck('talk_id');
        return json;
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
        this.collection.fetch();
    },

    addOne: function(talk) {
        var tv = new TalkView({model: talk});
        this.$('table').append(tv.render().el);
    },
    addAll: function() {
        this.$('table').empty();
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
        'click .remove-group': 'removeThisGroup',
        'blur h5 input': 'editTalkName'
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
        selectedTalks.each(function(t) { this.model.talks.add(t); }, this);
        selectedTalks.reset([]);
        this.model.save();
        this.model.trigger('change:talks');
    },

    removeThisGroup: function() {
        this.$el.remove();
        this.model.destroy();
    },

    editTalkName: function() {
        this.model.save({name: this.$('h5 input').val()});
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
        this.collection.fetch();
    },

    addOne: function(group) {
        var gv = new GroupView({
            model: group,
            collection: this.collection,
            id: 'group-view-' + group.get('number')
        });
        this.$('ul').append(gv.render().el);
    },

    addAll: function() {
        this.collection.each(this.addOne, this);
    },

    addNewGroup: function() {
        var g = this.collection.create({
            name: "New Group",
            talks: selectedTalks.toJSON()
        }, {wait: true});

        selectedTalks.reset([]);

        // For reasons I don't really understand, create() doesn't properly
        // set the group's number from returned POST until *after* calling
        // Group.initialize(). So we'll wait for sync to complete, then set
        // the talk URL correctly, then re-fetch the talks so the view renders
        // OK. There has got to be a better way, but I don't know it.
        g.on('sync', function() {
            g.talks.url = g.url() + '/talks';
            g.talks.fetch();
        });
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

// When adding or removing a group, make sure the ungrouped talks list re-
// renders. This feels very inelegent, but I'm not aware of a better way.
groups.on('add destroy change:talks', function(group, collection) {
    ungroupedTalks.fetch();
});

});
