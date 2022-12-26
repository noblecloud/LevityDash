
def load_all():
	"""
	Loads all modules.
	"""

	import importlib
	import pkgutil
	import pkginfo
	from pathlib import Path

	# find all the modules in the builtin plugins directory
	for module in pkgutil.iter_modules([str(Path(__file__).absolute())]):
		if not hasattr(module, '__plugin__'):
			continue
		# import the module
		importlib.import_module(module.name)
		# get the module's metadata
		metadata = pkginfo.get_metadata(f'LevityDash.lib.plugins.builtin.{module.name}')
		# add the module's metadata to the list of plugins
		# if the module has a load function, call it

