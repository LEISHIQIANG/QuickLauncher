"""Tests for services/errors.py exceptions."""

import pytest

from services.errors import CommercialError, ServicesError, UpdateError


def test_services_error_is_exception():
    assert issubclass(ServicesError, Exception)


def test_services_error_can_be_raised_and_caught():
    with pytest.raises(ServicesError):
        raise ServicesError("something went wrong")


def test_services_error_message():
    err = ServicesError("test message")
    assert str(err) == "test message"


def test_update_error_inherits_from_services_error():
    assert issubclass(UpdateError, ServicesError)


def test_update_error_can_be_raised_and_caught():
    with pytest.raises(UpdateError):
        raise UpdateError("update failed")


def test_update_error_caught_as_services_error():
    with pytest.raises(ServicesError):
        raise UpdateError("update failed")


def test_commercial_error_is_services_error():
    assert CommercialError is ServicesError


def test_commercial_error_caught_as_services_error():
    with pytest.raises(ServicesError):
        raise CommercialError("commercial issue")


def test_commercial_error_and_services_error_are_same():
    err = CommercialError("test")
    assert isinstance(err, ServicesError)
    assert type(err) is ServicesError
