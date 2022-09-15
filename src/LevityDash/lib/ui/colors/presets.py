from collections import ChainMap
from typing import MutableMapping

from WeatherUnits import Probability, Temperature
from WeatherUnits.derived.precipitation import Hourly
from WeatherUnits.derived.rate import MilesPerHour
from WeatherUnits.length import Millimeter
from WeatherUnits.others.light import Irradiance, Lux
from LevityDash.lib.utils.data import AttrDict

from .color import Color
from .gradient import Gradient


class Presets:
	__slots__ = ('_values', '_named_groups_')
	_values: ChainMap[str, Color | Gradient]
	_named_groups_: dict[str, int]

	def __init__(self, *presets: dict[str, Color | Gradient], **named_groups: dict[str, Color | Gradient]):
		self._values = ChainMap(*[AttrDict(i) for i in presets])
		self._named_groups_ = {}
		self.addNamedGroups(**named_groups)

	def add(self, *presets: dict[str, Color | Gradient]):
		self._values.maps += presets

	def __getitem__(self, item: str) -> Color | Gradient | AttrDict:
		if item in self._named_groups_:
			index = self._named_groups_[item]
			return self.groups[index]
		return self._values[item]

	def __getattr__(self, item: str) -> Color | Gradient | AttrDict:
		try:
			return self.__getattribute__('_values')[item]
		except KeyError:
			raise AttributeError(f'No preset named "{item}"')

	def addNamedGroup(self, name: str, group: dict[str, Color | Gradient]):
		index = len(self._values.maps)
		if not isinstance(group, AttrDict):
			group = AttrDict(group)
		self._values.maps.append(group)
		self._named_groups_[name] = index

	def addNamedGroups(self, **named_groups: dict[str, Color | Gradient]):
		for name, group in named_groups.items():
			self.addNamedGroup(name, group)

	@property
	def grups(self) -> list[MutableMapping[str, Color | Gradient]]:
		return self._values.maps


TemperatureGradient = Gradient[Temperature.Celsius](
	name='TemperatureGradient',
	freezing=(-10, '#94B7FF'),
	cold=(7, '#B2CBFF'),
	chilly=(12, '#F2F2FF'),
	comfortableStart=(17, '#F2F2FF'),
	comfortable=(22, '#FFFEFA'),
	hot=(28, '#ffb75d'),
	veryHot=(30, '#f3a469'),
	a=(32, '#f18271'),
	b=(38, '#cc6b8e'),
	c=(40, '#a86aa4'),
	d=(50, '#8f6aae'),
)

FabledSunsetGradientLux = Gradient[Lux](
	'FabledSunsetGradientLux',
	(0, '#23155700'),
	(3600, '#44107A55'),
	(6000, '#8F6AAEAA '),
	(7200, '#CC6B8E'),
	(10800, '#F3A469'),
	(18000, '#F7B731'),
	(36000, '#FFFEFA'),
)

FabledSunsetGradientWattsPerSquareMeter = Gradient[Irradiance](
	'FabledSunsetGradientWattsPerSquareMeter',
	(0, '#23155700'),
	(30, '#44107A55'),
	(50, '#8F6AAEAA '),
	(60, '#CC6B8E'),
	(90, '#F3A469'),
	(150, '#F7B731'),
	(300, '#FFFEFA'),
)
RipeMalinkaGradient = Gradient[MilesPerHour](
	'RipeMalinkaGradient',
	(0, '#f093fb'),
	(10, '#f5576c'),
	(20, '#f7b731'),
	(30, '#f9f64f'),
	(40, '#a9f7a9'),
	(50, '#5ff781'),
	(60, '#00e756'),
	(70, '#00b7eb'),
	(80, '#0052f3'),
	(90, '#0f00f9'),
	(100, '#7b00d4'),
)

PrecipitationProbabilityGradient = Gradient[Probability](
	name='PrecipitationProbabilityGradient',
	none=(0, '#00c6fb00'),
	Low=(.10, '#00c6fb'),
	high=(1, '#005bea'),
	one=(1, '#7b00d4'),
)

# Source https://webgradients.com/ 061 Sweet PeriodGet
PrecipitationRateGradient = Gradient[Hourly[Millimeter]](
	name='PrecipitationRateGradient',
	none=(0.1, '#3f51b100'),
	veryLight=(0.2, '#3f51b1'),
	light=(1, '#5a55ae'),
	moderate=(1.5, '#7b5fac'),
	heavy=(3, '#8f6aae'),
	veryHeavy=(5, '#a86aa4'),
	extreme=(12, '#cc6b8e'),
	storm=(24, '#f18271'),
	hurricane=(30, '#f3a469'),
	tornado=(35, '#f7c978'),
)

webcolors = {
	'aliceblue':            Color(name='aliceblue', red=240, blue=248, green=255),
	'antiquewhite':         Color(name='antiquewhite', red=250, blue=235, green=215),
	'aqua':                 Color(name='aqua', red=0, blue=255, green=255),
	'aquamarine':           Color(name='aquamarine', red=127, blue=255, green=212),
	'azure':                Color(name='azure', red=240, blue=255, green=255),
	'beige':                Color(name='beige', red=245, blue=245, green=220),
	'bisque':               Color(name='bisque', red=255, blue=228, green=196),
	'black':                Color(name='black', red=0, blue=0, green=0),
	'blanchedalmond':       Color(name='blanchedalmond', red=255, blue=235, green=205),
	'blue':                 Color(name='blue', red=0, blue=0, green=255),
	'blueviolet':           Color(name='blueviolet', red=138, blue=43, green=226),
	'brown':                Color(name='brown', red=165, blue=42, green=42),
	'burlywood':            Color(name='burlywood', red=222, blue=184, green=135),
	'cadetblue':            Color(name='cadetblue', red=95, blue=158, green=160),
	'chartreuse':           Color(name='chartreuse', red=127, blue=255, green=0),
	'chocolate':            Color(name='chocolate', red=210, blue=105, green=30),
	'coral':                Color(name='coral', red=255, blue=127, green=80),
	'cornflowerblue':       Color(name='cornflowerblue', red=100, blue=149, green=237),
	'cornsilk':             Color(name='cornsilk', red=255, blue=248, green=220),
	'crimson':              Color(name='crimson', red=220, blue=20, green=60),
	'cyan':                 Color(name='cyan', red=0, blue=255, green=255),
	'darkblue':             Color(name='darkblue', red=0, blue=0, green=139),
	'darkcyan':             Color(name='darkcyan', red=0, blue=139, green=139),
	'darkgoldenrod':        Color(name='darkgoldenrod', red=184, blue=134, green=11),
	'darkgray':             Color(name='darkgray', red=169, blue=169, green=169),
	'darkgrey':             Color(name='darkgrey', red=169, blue=169, green=169),
	'darkgreen':            Color(name='darkgreen', red=0, blue=100, green=0),
	'darkkhaki':            Color(name='darkkhaki', red=189, blue=183, green=107),
	'darkmagenta':          Color(name='darkmagenta', red=139, blue=0, green=139),
	'darkolivegreen':       Color(name='darkolivegreen', red=85, blue=107, green=47),
	'darkorange':           Color(name='darkorange', red=255, blue=140, green=0),
	'darkorchid':           Color(name='darkorchid', red=153, blue=50, green=204),
	'darkred':              Color(name='darkred', red=139, blue=0, green=0),
	'darksalmon':           Color(name='darksalmon', red=233, blue=150, green=122),
	'darkseagreen':         Color(name='darkseagreen', red=143, blue=188, green=143),
	'darkslateblue':        Color(name='darkslateblue', red=72, blue=61, green=139),
	'darkslategray':        Color(name='darkslategray', red=47, blue=79, green=79),
	'darkslategrey':        Color(name='darkslategrey', red=47, blue=79, green=79),
	'darkturquoise':        Color(name='darkturquoise', red=0, blue=206, green=209),
	'darkviolet':           Color(name='darkviolet', red=148, blue=0, green=211),
	'deeppink':             Color(name='deeppink', red=255, blue=20, green=147),
	'deepskyblue':          Color(name='deepskyblue', red=0, blue=191, green=255),
	'dimgray':              Color(name='dimgray', red=105, blue=105, green=105),
	'dimgrey':              Color(name='dimgrey', red=105, blue=105, green=105),
	'dodgerblue':           Color(name='dodgerblue', red=30, blue=144, green=255),
	'firebrick':            Color(name='firebrick', red=178, blue=34, green=34),
	'floralwhite':          Color(name='floralwhite', red=255, blue=250, green=240),
	'forestgreen':          Color(name='forestgreen', red=34, blue=139, green=34),
	'fuchsia':              Color(name='fuchsia', red=255, blue=0, green=255),
	'gainsboro':            Color(name='gainsboro', red=220, blue=220, green=220),
	'ghostwhite':           Color(name='ghostwhite', red=248, blue=248, green=255),
	'gold':                 Color(name='gold', red=255, blue=215, green=0),
	'goldenrod':            Color(name='goldenrod', red=218, blue=165, green=32),
	'gray':                 Color(name='gray', red=128, blue=128, green=128),
	'grey':                 Color(name='grey', red=128, blue=128, green=128),
	'green':                Color(name='green', red=0, blue=128, green=0),
	'greenyellow':          Color(name='greenyellow', red=173, blue=255, green=47),
	'honeydew':             Color(name='honeydew', red=240, blue=255, green=240),
	'hotpink':              Color(name='hotpink', red=255, blue=105, green=180),
	'indianred':            Color(name='indianred', red=205, blue=92, green=92),
	'indigo':               Color(name='indigo', red=75, blue=0, green=130),
	'ivory':                Color(name='ivory', red=255, blue=255, green=240),
	'khaki':                Color(name='khaki', red=240, blue=230, green=140),
	'lavender':             Color(name='lavender', red=230, blue=230, green=250),
	'lavenderblush':        Color(name='lavenderblush', red=255, blue=240, green=245),
	'lawngreen':            Color(name='lawngreen', red=124, blue=252, green=0),
	'lemonchiffon':         Color(name='lemonchiffon', red=255, blue=250, green=205),
	'lightblue':            Color(name='lightblue', red=173, blue=216, green=230),
	'lightcoral':           Color(name='lightcoral', red=240, blue=128, green=128),
	'lightcyan':            Color(name='lightcyan', red=224, blue=255, green=255),
	'lightgoldenrodyellow': Color(name='lightgoldenrodyellow', red=250, blue=250, green=210),
	'lightgray':            Color(name='lightgray', red=211, blue=211, green=211),
	'lightgrey':            Color(name='lightgrey', red=211, blue=211, green=211),
	'lightgreen':           Color(name='lightgreen', red=144, blue=238, green=144),
	'lightpink':            Color(name='lightpink', red=255, blue=182, green=193),
	'lightsalmon':          Color(name='lightsalmon', red=255, blue=160, green=122),
	'lightseagreen':        Color(name='lightseagreen', red=32, blue=178, green=170),
	'lightskyblue':         Color(name='lightskyblue', red=135, blue=206, green=250),
	'lightslategray':       Color(name='lightslategray', red=119, blue=136, green=153),
	'lightslategrey':       Color(name='lightslategrey', red=119, blue=136, green=153),
	'lightsteelblue':       Color(name='lightsteelblue', red=176, blue=196, green=222),
	'lightyellow':          Color(name='lightyellow', red=255, blue=255, green=224),
	'lime':                 Color(name='lime', red=0, blue=255, green=0),
	'limegreen':            Color(name='limegreen', red=50, blue=205, green=50),
	'linen':                Color(name='linen', red=250, blue=240, green=230),
	'magenta':              Color(name='magenta', red=255, blue=0, green=255),
	'maroon':               Color(name='maroon', red=128, blue=0, green=0),
	'mediumaquamarine':     Color(name='mediumaquamarine', red=102, blue=205, green=170),
	'mediumblue':           Color(name='mediumblue', red=0, blue=0, green=205),
	'mediumorchid':         Color(name='mediumorchid', red=186, blue=85, green=211),
	'mediumpurple':         Color(name='mediumpurple', red=147, blue=112, green=219),
	'mediumseagreen':       Color(name='mediumseagreen', red=60, blue=179, green=113),
	'mediumslateblue':      Color(name='mediumslateblue', red=123, blue=104, green=238),
	'mediumspringgreen':    Color(name='mediumspringgreen', red=0, blue=250, green=154),
	'mediumturquoise':      Color(name='mediumturquoise', red=72, blue=209, green=204),
	'mediumvioletred':      Color(name='mediumvioletred', red=199, blue=21, green=133),
	'midnightblue':         Color(name='midnightblue', red=25, blue=25, green=112),
	'mintcream':            Color(name='mintcream', red=245, blue=255, green=250),
	'mistyrose':            Color(name='mistyrose', red=255, blue=228, green=225),
	'moccasin':             Color(name='moccasin', red=255, blue=228, green=181),
	'navajowhite':          Color(name='navajowhite', red=255, blue=222, green=173),
	'navy':                 Color(name='navy', red=0, blue=0, green=128),
	'oldlace':              Color(name='oldlace', red=253, blue=245, green=230),
	'olive':                Color(name='olive', red=128, blue=128, green=0),
	'olivedrab':            Color(name='olivedrab', red=107, blue=142, green=35),
	'orange':               Color(name='orange', red=255, blue=165, green=0),
	'orangered':            Color(name='orangered', red=255, blue=69, green=0),
	'orchid':               Color(name='orchid', red=218, blue=112, green=214),
	'palegoldenrod':        Color(name='palegoldenrod', red=238, blue=232, green=170),
	'palegreen':            Color(name='palegreen', red=152, blue=251, green=152),
	'paleturquoise':        Color(name='paleturquoise', red=175, blue=238, green=238),
	'palevioletred':        Color(name='palevioletred', red=219, blue=112, green=147),
	'papayawhip':           Color(name='papayawhip', red=255, blue=239, green=213),
	'peachpuff':            Color(name='peachpuff', red=255, blue=218, green=185),
	'peru':                 Color(name='peru', red=205, blue=133, green=63),
	'pink':                 Color(name='pink', red=255, blue=192, green=203),
	'plum':                 Color(name='plum', red=221, blue=160, green=221),
	'powderblue':           Color(name='powderblue', red=176, blue=224, green=230),
	'purple':               Color(name='purple', red=128, blue=0, green=128),
	'red':                  Color(name='red', red=255, blue=0, green=0),
	'rosybrown':            Color(name='rosybrown', red=188, blue=143, green=143),
	'royalblue':            Color(name='royalblue', red=65, blue=105, green=225),
	'saddlebrown':          Color(name='saddlebrown', red=139, blue=69, green=19),
	'salmon':               Color(name='salmon', red=250, blue=128, green=114),
	'sandybrown':           Color(name='sandybrown', red=244, blue=164, green=96),
	'seagreen':             Color(name='seagreen', red=46, blue=139, green=87),
	'seashell':             Color(name='seashell', red=255, blue=245, green=238),
	'sienna':               Color(name='sienna', red=160, blue=82, green=45),
	'silver':               Color(name='silver', red=192, blue=192, green=192),
	'skyblue':              Color(name='skyblue', red=135, blue=206, green=235),
	'slateblue':            Color(name='slateblue', red=106, blue=90, green=205),
	'slategray':            Color(name='slategray', red=112, blue=128, green=144),
	'slategrey':            Color(name='slategrey', red=112, blue=128, green=144),
	'snow':                 Color(name='snow', red=255, blue=250, green=250),
	'springgreen':          Color(name='springgreen', red=0, blue=255, green=127),
	'steelblue':            Color(name='steelblue', red=70, blue=130, green=180),
	'tan':                  Color(name='tan', red=210, blue=180, green=140),
	'teal':                 Color(name='teal', red=0, blue=128, green=128),
	'thistle':              Color(name='thistle', red=216, blue=191, green=216),
	'tomato':               Color(name='tomato', red=255, blue=99, green=71),
	'turquoise':            Color(name='turquoise', red=64, blue=224, green=208),
	'violet':               Color(name='violet', red=238, blue=130, green=238),
	'wheat':                Color(name='wheat', red=245, blue=222, green=179),
	'white':                Color(name='white', red=255, blue=255, green=255),
	'whitesmoke':           Color(name='whitesmoke', red=245, blue=245, green=245),
	'yellow':               Color(name='yellow', red=255, blue=255, green=0),
	'yellowgreen':          Color(name='yellowgreen', red=154, blue=205, green=50),
}


def __getattr__(name):
	if name == 'gradients':
		return [i for i in locals() if isinstance(i, Gradient)]
	elif name == 'colors':
		return [i for i in locals() if isinstance(i, Color)]
	elif name in webcolors:
		return webcolors[name]


Color.presets = Presets(web=webcolors)
__all__ = tuple(i for i in locals() if isinstance(i, (Gradient, Color)))
