class APIError(Exception):
	def __init__(self, *args, **kwargs):
		self.data = args
		super(APIError, self).__init__(*args)


class RateLimitExceeded(APIError):
	pass


class RequestTimeout(APIError, TimeoutError):
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
