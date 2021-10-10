import logging

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

# The background is set with 40 plus the number of the color, and the foreground with 30

# These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"



def formatter_message(message, use_color=True):
	if use_color:
		message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
	else:
		message = message.replace("$RESET", "").replace("$BOLD", "")
	return message


COLORS = {
		'WARNING':  YELLOW,
		'INFO':     WHITE,
		'DEBUG':    BLUE,
		'CRITICAL': YELLOW,
		'ERROR':    RED
}


class ColoredFormatter(logging.Formatter):
	def __init__(self, msg, use_color=True):
		logging.Formatter.__init__(self, msg)
		self.use_color = use_color

	def format(self, record):
		levelName = record.levelname
		if self.use_color and levelName in COLORS:
			levelNameColor = COLOR_SEQ % (30 + COLORS[levelName]) + levelName + RESET_SEQ
			record.levelname = levelNameColor
		return logging.Formatter.format(self, record)


class ColoredLogger(logging.Logger):
	FORMAT = "[$BOLD%(name)-30s$RESET][%(levelname)-18s]  %(message)s ($BOLD%(filename)s$RESET:%(lineno)d)"
	COLOR_FORMAT = formatter_message(FORMAT, True)

	def __init__(self, name):
		logging.Logger.__init__(self, name, logging.DEBUG)

		color_formatter = ColoredFormatter(self.COLOR_FORMAT)

		console = logging.StreamHandler()
		console.setFormatter(color_formatter)

		self.addHandler(console)
		return
