import os

# Interaction with the PyCon website
WEBSITE_HOST = os.environ.get('PYCON_WEBSITE_HOST', 'us.pycon.org')
API_KEY = os.environ.get('PYCON_API_KEY', '')
API_SECRET = os.environ.get('PYCON_API_SECRET', '')

# Interaction with IRC
IRC_SUPERUSERS = os.environ.get('PYCONBOT_SUPERUSERS', '').split(',')
IRC_NICK = os.environ.get('PYCONBOT_NICK', 'pycon_bot')
IRC_CHANNEL = os.environ.get('PYCONBOT_CHANNEL', '#pycon-pc')
