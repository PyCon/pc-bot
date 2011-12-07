from pycon_bot.thunder import PyConThunderdomeBot


class MockThunderdomeBot(PyConThunderdomeBot):
    def __init__(self, *args, **kwargs):
        PyConThunderdomeBot.__init__(self, *args, **kwargs)
        self.messages = []

    def load_talk_groups(self):
        self.talk_groups = [
            {
                "name": "Group #1",
                "talks": {
                    "1": "title 1",
                    "2": "title 2",
                    "3": "title 3",
                }
            }
        ]

    def msg(self, channel, message):
        self.messages.append((channel, message))

class TestBot(object):
    def test_start(self):
        bot = MockThunderdomeBot()
        bot.privmsg("jacobkm", "#pycon-pc", ",start")
        assert bot.messages == [
            ("#pycon-pc", "=== Ready (no groups to skip). ==="),
        ]

    def test_handle_user_vote(self):
        bot = MockThunderdomeBot()
        bot.idx = 0
        bot.handle_user_vote("#test", "alex", "none")
        assert bot.current_votes == {"alex": []}
        bot.handle_user_vote("#test", "alex", "1")
        assert bot.current_votes == {"alex": [1]}
        bot.handle_user_vote("#test", "alex", "1, 2")
        assert bot.current_votes == {"alex": [1, 2]}

    def test_handle_decision(self):
        bot = MockThunderdomeBot()
        bot.idx = 0

        bot.handle_in('#test', "1", "2")
        assert bot.talk_groups[0]['decision']['accepted'] == [1, 2]
        bot.handle_out('#test', '3')
        assert bot.talk_groups[0]['decision']['rejected'] == [3]

        # Changing a talk's status removes it from other groups
        bot.handle_dam('#test', '2')
        assert bot.talk_groups[0]['decision']['damaged'] == [2]
        assert bot.talk_groups[0]['decision']['accepted'] == [1]

        # Adding a talk to a status doesn't clear the existing ones
        bot.handle_in('#test', '2')
        assert bot.talk_groups[0]['decision']['accepted'] == [1, 2]
