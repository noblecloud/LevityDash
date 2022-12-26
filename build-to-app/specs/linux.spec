import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

if TYPE_CHECKING:
	from PyInstaller.building.api import PYZ, EXE
	from PyInstaller.building.build_main import Analysis

block_cipher = None

datas = []

src = Path.cwd().absolute()

sys.path.append(str(src))

datas += collect_data_files('WeatherUnits')
datas += collect_data_files('aiohttp')
datas += collect_data_files('certifi')

os.chdir(src)

# add the resources folder
datas.extend(
	collect_data_files(
		"LevityDash",
		include_py_files=True,
		includes=['**/resources/*'],
		excludes=['**/__pycache__/*', '**/.DS_Store', '**/*.ignore', '**/build-to-app/*'],
	)
)

hiddenimports = collect_submodules('LevityDash', filter=lambda x: not x.startswith('LevityDash.lib.plugins.builtin'))

# # add the lib folder
datas.extend(
	collect_data_files(
		"LevityDash",
		include_py_files=True,
		includes=['**/lib/*'],
		excludes=['**/__pycache__/*', '**/.DS_Store', '**/*.ignore'],
	)
)

# add the shims folder
datas.extend(
	collect_data_files(
		"LevityDash",
		include_py_files=True,
		includes=['**/shims/*'],
		excludes=['**/__pycache__/*', '**/.DS_Store', '**/*.ignore'],
	)
)

a = Analysis(
	['../src/LevityDash/__main__.py'],
	binaries=[],
	datas=datas,
	hiddenimports=hiddenimports,
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	win_no_prefer_redirects=False,
	win_private_assemblies=False,
	cipher=block_cipher,
	noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# exe = EXE(
# 	pyz,
# 	a.scripts,
# 	a.binaries,
# 	a.zipfiles,
# 	a.datas,
# 	[],
# 	name='LevityDash',
# 	debug=False,
# 	bootloader_ignore_signals=False,
# 	strip=False,
# 	upx=True,
# 	upx_exclude=[],
# 	runtime_tmpdir=None,
# 	console=False,
# 	disable_windowed_traceback=False,
# 	argv_emulation=False,
# 	target_arch=None,
# 	icon='windows.ico',
# 	exclude_binaries=False,
# )

cli = EXE(
	pyz,
	a.scripts,
	a.binaries,
	a.zipfiles,
	a.datas,
	[],
	name='LevityDashCLI',
	debug=False,
	bootloader_ignore_signals=False,
	strip=False,
	upx=True,
	upx_exclude=[],
	runtime_tmpdir=None,
	console=True,
	disable_windowed_traceback=False,
	argv_emulation=True,
	icon='assets/windows.ico',
	exclude_binaries=False,
)

