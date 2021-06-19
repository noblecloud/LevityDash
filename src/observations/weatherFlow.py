from src.observations import ObservationSingle
from src.translators import WFStationTranslator


class WFObservationSingle(ObservationSingle):
	pass


# def __init__(self, data: dict):
# 	for measurement in data.keys():
# 		attrName, attrValue = self.localize(measurement, data[measurement])
# 		self._data[attrName] = attrValue


class WFStationObservation(WFObservationSingle):
	_translator = WFStationTranslator()
