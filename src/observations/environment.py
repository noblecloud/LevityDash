from ._observations import Observation, ObservationForecast, ObservationForecastItem, ObservationRealtime

__all__ = ["EnvironmentObservation", "EnvironmentObservationForecast", "EnvironmentObservationForecastItem", "EnvironmentObservationRealtime"]


class EnvironmentObservation(Observation, category='environment'):
	pass


class EnvironmentObservationForecastItem(ObservationForecastItem, category='environment'):
	pass


class EnvironmentObservationRealtime(ObservationRealtime, category='environment'):
	pass


class EnvironmentObservationForecast(ObservationForecast, category='environment'):
	pass
