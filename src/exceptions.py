class TokenExpiredError(Exception):
    """Raised when an access token is expired and the refresh attempt failed."""


class ParseError(Exception):
    """Raised when a message cannot be parsed into a calendar event."""


class GoogleApiError(Exception):
    """Raised when the Google API returns an unexpected error."""


class EventNotFoundError(Exception):
    """Raised when an event cannot be found in the database."""
