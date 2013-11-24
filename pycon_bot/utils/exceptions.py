class APIError(Exception):
    pass

class AuthenticationError(APIError):
    pass

class NotFound(APIError):
    pass

class InternalServerError(Exception):
    def __init__(self, r):
        self.r = r
