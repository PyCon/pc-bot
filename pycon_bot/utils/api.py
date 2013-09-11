from calendar import timegm
from datetime import datetime
from hashlib import sha1
from pycon_bot import settings
from pycon_bot.utils.exceptions import APIError, AuthenticationError
from requests.compat import quote
import json
import os
import pytz
import requests


class API(object):
    def __init__(self, api_key=None, api_secret=None, host=None):
        self.api_key = api_key or settings.API_KEY
        self.api_secret = api_secret or settings.API_SECRET
        self.host = host or settings.WEBSITE_HOST

    def get(self, endpoint, **kwargs):
        return self.request('GET', endpoint, **kwargs)

    def post(self, endpoint, body):
        return self.request('POST', endpoint, json.dumps(body))

    def request(self, method, endpoint, body='', **kwargs):
        """Make a request to the PyCon website, and return the result."""
        # Construct the full URL.
        url = 'http://{host}/2014/pycon_api/{endpoint}/'.format(
            endpoint=endpoint,
            host=self.host,
        )

        # If keyword arguments are provided, append them to
        # the URL.
        if kwargs:
            url += '?' + '&'.join(
                ['%s=%s' % (k, quote(v)) for k, v in kwargs.items()],
            )

        # Generate the appropriate request signature to certify
        # that this is a valid request.
        signature = self._sign_request(url, method, body)

        # Make the actual request to the PyCon website.
        r = requests.request(method, url, data=body, headers=signature,
                                          verify=False)

        # Sanity check: Did we get a bad request of some kind?
        if r.status_code >= 400:
            # What exception class shall I use?
            exc_class = APIError
            if r.status_code == 403:
                exc_class = AuthenticationError
            if r.status_code == 404:
                exc_class = NotFound

            # Create and raise the exception
            ex = exc_class(r.json()['error'])
            ex.request = r
            raise ex

        # OK, all is well; return the response.
        return r.json()

    def _sign_request(self, url, method, body=''):
        """Return a dictionary with the appropriate headers with which
        to sign this request.
        """
        # What time is it right now? We use the current timestamp
        # as part of the request signature.
        timestamp = timegm(datetime.now(tz=pytz.UTC).timetuple())

        # Create the "base string", and then SHA1 hash it.
        base_string = unicode(''.join((
            self.api_secret,
            unicode(timestamp),
            method.upper(),
            url,
            body,
        )))

        # Return a signature dictionary.
        return {
            'X-API-Key': self.api_key,
            'X-API-Signature': sha1(base_string.encode('utf-8')).hexdigest(),
            'X-API-Timestamp': timestamp,
        }
