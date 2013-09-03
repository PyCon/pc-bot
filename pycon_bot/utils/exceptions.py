class APIError(Exception):
    pass

class AuthenticationError(APIError):
    pass

class NotFound(APIError):
    pass
