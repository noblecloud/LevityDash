
from .. import LevityDashboard

from . import config
LevityDashboard.config = config.userConfig
LevityDashboard.plugin_config = config.pluginConfig

from . import log
LevityDashboard.log = log.LevityLogger
config.log = log.LevityLogger.getChild('config')

from . import utils
from . import plugins
from . import ui
