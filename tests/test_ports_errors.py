import pytest
from quodeq.data.ports.data_errors import AuthError, NotFoundError, NetworkError, ServerError, InvalidDataError


def test_data_errors_are_distinct_types():
    """Each error type is a distinct Exception subclass."""
    assert issubclass(AuthError, Exception)
    assert issubclass(NotFoundError, Exception)
    assert issubclass(NetworkError, Exception)
    assert issubclass(ServerError, Exception)
    assert issubclass(InvalidDataError, Exception)


def test_data_errors_can_be_raised_and_caught():
    """Each error can be raised with a message and caught by its type."""
    for cls in (AuthError, NotFoundError, NetworkError, ServerError, InvalidDataError):
        with pytest.raises(cls, match="test message"):
            raise cls("test message")


def test_data_errors_carry_message():
    """Error instances preserve the message passed at construction."""
    err = NetworkError("connection refused")
    assert str(err) == "connection refused"
    assert isinstance(err, Exception)
