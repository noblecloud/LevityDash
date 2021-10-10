#!/usr/bin/env python3
from json import loads

from bs4 import BeautifulSoup
import requests
import pickle as p

from field import Field

# @dataclass(eq=True, frozen=True)
# class IndexItem:
# 	name: str
# 	range: Range = None
#
# 	def __init__(self, value: str):
# 		if '(' in value:
# 			i = value.index('(')
# 			self.name = value[:i - 1]
# 			self.range = Range(value[i:])
# 		else:
# 			self.name = value
# 			# self.range = Range(inf)
