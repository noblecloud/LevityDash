"""The default dashboard with two rooms indoors, a bedroom and a terrarium, each a Govee sensor named by identity."""
from default import *  # noqa: F403
import default

FREEZE = default.FREEZE
LEVITY = None  # beside this file, not over the shipped template
ROOMS = [('BEDROOM', '#bedroom', '$series-2'), ('TERRARIUM', '#terrarium', '$good')]

HEADER = default.HEADER.replace('The default dashboard for OpenMeteo, the forecast LevityDash starts with.',
                                'The default dashboard with a bedroom and a terrarium indoors (Govee sensors named bedroom and terrarium).')


def data():
	# Planes over the house, so the render shows the tracker: the radar scenario's aircraft, as the plugin publishes them.
	d = default.data(ROOMS, 'home')
	import yaml
	from pathlib import Path
	near = yaml.safe_load((Path(__file__).parent.parent / 'scenarios' / 'aircraft-near.yaml').read_text())['keys']
	d.keys.update({k: v for k, v in near.items() if k.startswith('aircraft.')})
	d.keys['aircraft.active'] = {'value': 1, 'unit': 'int', 'title': 'A plane is near'}
	return d


def board():
	return default.board(ROOMS)


if __name__ == '__main__':
	write('home', HEADER, board(), data(), FREEZE)  # noqa: F405
