from quodeq.data.ports.data_errors import AuthError, NotFoundError, NetworkError, ServerError, InvalidDataError


def test_data_errors_are_distinct_types():
    assert issubclass(AuthError, Exception)
    assert issubclass(NotFoundError, Exception)
    assert issubclass(NetworkError, Exception)
    assert issubclass(ServerError, Exception)
    assert issubclass(InvalidDataError, Exception)
