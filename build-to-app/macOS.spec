# -*- mode: python ; coding: utf-8 -*-
from os import environ

block_cipher = None
from PyInstaller.utils.hooks import collect_data_files
from LevityDash import __lib__, __resources__, __version__

datas = [('../src/LevityDash', '.'), ('../src/LevityDash', 'LevityDash'), ('../src/LevityDash/example-config', 'example-config')]
datas += collect_data_files('WeatherUnits', 'aiohttp', 'certifi')

a = Analysis(
	['../src/LevityDash/__main__.py'],
	binaries=[],
	datas=datas,
	hiddenimports=['bleak', 'WeatherUnits', 'certifi', 'aiohttp'],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	win_no_prefer_redirects=False,
	win_private_assemblies=False,
	cipher=block_cipher,
	noarchive=True,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
	pyz,
	a.scripts,
	[],
	exclude_binaries=True,
	name='LevityDashApp',
	debug=False,
	bootloader_ignore_signals=False,
	strip=True,
	upx=True,
	console=False,
	disable_windowed_traceback=False,
	argv_emulation=False,
	target_arch=None,
	codesign_identity=environ['CODE_SIGN_IDENTITY'],
	entitlements_file='build-to-app/entitlements.plist',
	icon='macOS.icns',
)
coll = COLLECT(
	exe,
	a.binaries,
	a.zipfiles,
	a.datas,
	strip=False,
	upx=True,
	upx_exclude=[],
	name='LevityDashApp',
)
app = BUNDLE(
	coll,
	name='LevityDash.app',
	icon='macOS.icns',
	bundle_identifier='dev.noblecloud.levity',
	version=__version__,
	info_plist={
		'NSBluetoothAlwaysUsageDescription':     'LevityDash would like to use your bluetooth for connecting to devices',
		'NSBluetoothPeripheralUsageDescription': 'LevityDash would like to use your bluetooth for connecting to devices',
		'NSRequiresAquaSystemAppearance':        'No',
		'NSHighResolutionCapable':               'True',
	},
)
