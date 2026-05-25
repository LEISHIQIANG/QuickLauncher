"""Shared service exceptions."""


class ServicesError(Exception):
    """Base exception for service modules."""


class UpdateError(ServicesError):
    """Raised when an update operation fails."""


CommercialError = ServicesError
