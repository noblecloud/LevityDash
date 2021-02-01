

class APIError(Exception):
	pass


class RateLimitExceeded(APIError):
	pass


class InvalidCredentials(APIError):
	pass


class BadRequest(APIError):
	pass


class Unauthorized(APIError):
	pass


class Forbidden(APIError):
	pass


class TooManyRequests(APIError):
	pass
