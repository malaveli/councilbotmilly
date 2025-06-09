# exceptions.py

# Custom Exceptions
class APIError(Exception):
    """Base class for API errors"""
    pass

class AuthenticationError(APIError):
    pass

class OrderRejectedError(APIError):
    pass

class PositionError(APIError):
    pass

class HistoricalDataError(APIError):
    pass

class ConnectionError(APIError):
    pass

class AccountError(APIError):
    pass

class RateLimitError(APIError):
    pass