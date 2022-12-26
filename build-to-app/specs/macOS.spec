# -*- mode: python ; coding: utf-8 -*-
import os
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

if TYPE_CHECKING:
	from PyInstaller.building.api import PYZ, EXE, COLLECT
	from PyInstaller.building.build_main import Analysis
	from PyInstaller.building.osx import BUNDLE

src = Path.cwd().absolute()

datas = []
datas += collect_data_files('WeatherUnits')
datas += collect_data_files('aiohttp')
datas += collect_data_files('certifi')

# add the resources folder
datas.extend(
	collect_data_files(
		"LevityDash",
		include_py_files=True,
		includes=['**/resources/*'],
		excludes=['**/__pycache__/*', '**/.DS_Store', '**/*.ignore', '**/build-to-app/*'],
	)
)

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

os.chdir(src)


a = Analysis(
	['../src/LevityDash/__main__.py'],
	binaries=[],
	datas=datas,
	hiddenimports=[*collect_submodules('LevityDash', filter=lambda x: not x.startswith('LevityDash.lib.plugins.builtin'))],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	win_no_prefer_redirects=False,
	win_private_assemblies=False,
	cipher=None,
	noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)


cli = EXE(
	pyz,
	a.scripts,
	a.binaries,
	a.zipfiles,
	a.datas,
	[],
	exclude_binaries=False,
	name='LevityDashCLI',
	debug=True,
	bootloader_ignore_signals=False,
	strip=False,
	upx=True,
	upx_exclude=[],
	runtime_tmpdir=None,
	console=True,
	disable_windowed_traceback=False,
	argv_emulation=True,
	codesign_identity=environ['CODE_SIGN_IDENTITY'],
	entitlements_file='../assets/entitlements.plist',
	target_arch='x86_64',
	icon='assets/macOS.icns',
)

# exe = EXE(
# 	pyz,
# 	a.scripts,
# 	a.binaries,
# 	a.zipfiles,
# 	a.datas,
# 	[],
# 	name='LevityDashboard',
# 	debug=False,
# 	bootloader_ignore_signals=False,
# 	strip=False,
# 	upx=True,
# 	upx_exclude=[],
# 	runtime_tmpdir=None,
# 	console=False,
# 	disable_windowed_traceback=False,
# 	argv_emulation=True,
# 	target_arch='x86_64',
# 	codesign_identity=environ['CODE_SIGN_IDENTITY'],
# 	entitlements_file='../build-to-app/entitlements.plist',
# 	icon='macOS.icns',
# 	exclude_binaries=False,
# )
#
# from LevityDash import __version__
#
# # app = BUNDLE(
# # 	exe,
# # 	a.binaries,
# # 	a.datas,
# # 	name='LevityDash.app',
# # 	icon='macOS.icns',
# # 	bundle_identifier='dev.noblecloud.levitydash',
# # 	version=__version__,
# # 	info_plist={
# # 		'NSBluetoothAlwaysUsageDescription': 'LevityDash would like to use your bluetooth for connecting to devices',
# # 		'NSBluetoothPeripheralUsageDescription': 'LevityDash would like to use your bluetooth for connecting to devices',
# # 		'NSRequiresAquaSystemAppearance': 'No',
# # 		'NSHighResolutionCapable': 'True',
# # 		# 'UIRequiresPersistentWiFi': 'True',
# # 	},
# # )

