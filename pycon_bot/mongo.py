import os
import urlparse
import mongoengine

def connect(dsn=None):
    """
    Connect to mongo from a given dsn flag or by reading env.
    """
    dsn = dsn or os.environ.get('MONGO_DSN', None)
    if not dsn:
        return None

    # Connect to mongo. Have to parse out the DSN which is gross, but better
    # than using 6 env vars/flags.
    p = urlparse.urlparse(dsn)
    db = p.path.strip('/')
    userpass, hostport = p.netloc.rsplit('@', 1)
    username, password = userpass.split(':', 1)
    host, port = hostport.split(':', 1)
    return mongoengine.connect(db, host=host, port=int(port), username=username, password=password)
