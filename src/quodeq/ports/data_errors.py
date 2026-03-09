class DataError(Exception):
    pass


class AuthError(DataError):
    pass


class NotFoundError(DataError):
    pass


class NetworkError(DataError):
    pass


class ServerError(DataError):
    pass


class InvalidDataError(DataError):
    pass
