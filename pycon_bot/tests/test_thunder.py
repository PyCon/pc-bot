from pycon_bot.thunder import PyConThunderdomeBot


class MockThunderdomeBot(PyConThunderdomeBot):
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

class TestBot(object):
    def test_handle_user_vote(self):
        bot = MockThunderdomeBot()
        bot.idx = 0
        bot.handle_user_vote("#test", "alex", "none")
        assert bot.current_votes == {"alex": []}
        bot.handle_user_vote("#test", "alex", "1")
        assert bot.current_votes == {"alex": [1]}
        bot.handle_user_vote("#test", "alex", "1, 2")
        assert bot.current_votes == {"alex": [1, 2]}