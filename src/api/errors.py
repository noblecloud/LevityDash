class APIError(Exception):
	pass


class RateLimitExceeded(APIError):
	pass


class InvalidCredentials(APIError):
	pass
