from src.observations import Observation
from src.translators import WFStationTranslator


class WFObservation(Observation):
	pass
# def __init__(self, data: dict):
# 	for measurement in data.keys():
# 		attrName, attrValue = self.localize(measurement, data[measurement])
# 		self._data[attrName] = attrValue


class WFStationObservation(WFObservation):

	_translator = WFStationTranslator()
