class PopException(Exception):
    """Exception hierarchy base class."""


class StateException(PopException):
    """Incorrect state for required operation."""


class StateNotFound(StateException):
    """Missing node at path."""

    def __init__(self, path):
        self.path = path
