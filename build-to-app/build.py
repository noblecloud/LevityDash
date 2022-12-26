#!/usr/bin/env python
from os import environ


def get_sig():
	def inputSig():
		sig = input('Enter Apple ID for app signature: ')
		with open('../build-to-app/.signature', 'w') as f:
			f.write(sig)
		return sig

	try:
		with open('../build-to-app/.signature', 'r') as f:
			sig = f.read()
		return sig or inputSig()
	except FileNotFoundError:
		return inputSig()


def get_valid_plugins() -> list[str]:
	import pkgutil
	from LevityDash import LevityDashboard

	return [i.name for i in pkgutil.iter_modules([str(LevityDashboard.paths.builtin_plugins.absolute())])]


def build():
	import argparse
	parser = argparse.ArgumentParser()
	parser.add_argument('--clean', action='store_true', help='Clean the build directory before building')
	parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARN', 'ERROR'], help='Set the logging level')
	parser.add_argument('--install', action='store_true', help='Install the app after building.  Only works on macOS and Linux. (Experimental)')
	parser.add_argument('--reinstall', action='store_true', help='Reinstall the app')
	parser.add_argument('--force-install', action='store_true', help='Overwrite existing installation')
	# parser.add_argument('--install-location', default=None, help='Location to install to.  Defaults to /Applications on macOS, /usr/bin on Linux, and None on Windows')

	args = parser.parse_args()

	environ['LEVITY_BUILDING'] = 'TRUE'

	from rich.logging import RichHandler
	import logging

	FORMAT = "%(message)s"
	logging.basicConfig(
		level=args.log_level,
		format=FORMAT,
		datefmt="[%X]",
		handlers=[RichHandler(
			rich_tracebacks=True,
			tracebacks_show_locals=True,
		)
		]
	)
	try:
		import PyInstaller.config
		import PyInstaller.__main__ as main
	except ImportError:
		logging.error(
			"PyInstaller is required for building. "
			"Please install it with 'pip install PyInstaller'"
			"or visit https://levitydash.app/building"
		)
		import sys

		sys.exit(1)

	import platform
	import os

	os.chdir("../src")

	try:
		pyinstaller_args = [
			'--noconfirm',
			f'--log-level={args.log_level}',
			'--workpath=../build-to-app/build',
		]

		if args.clean:
			pyinstaller_args.append('--clean')

		# Only install the app if it is already built
		if args.install and not args.clean and not args.reinstall:
			install(args)
			exit(0)

		if platform.system() == "Darwin":
			os.environ['CODE_SIGN_IDENTITY'] = get_sig()
			pyinstaller_args.insert(0, "../build-to-app/specs/macOS.spec")

		elif platform.system() == "Windows":
			pyinstaller_args.insert(0, "../build-to-app/specs/windows.spec")

		elif platform.system() == "Linux":
			pyinstaller_args.insert(0, "../build-to-app/specs/linux.spec")

		else:
			print("Unsupported platform")

		main.run(pyinstaller_args)
	except Exception as e:
		print("Build failed...")
		print(e)
	else:
		print("Build successful!")
		if args.install or args.reinstall:
			try:
				install(args)
			except Exception as e:
				print("Install failed...")
				print(e)
				exit(1)
			exit(0)
	finally:
		environ['LEVITY_BUILDING'] = 'FALSE'


def install(arg_parser, location=None):
	from pathlib import Path
	import platform
	import shutil

	dist = '../build-to-app/dist/LevityDash'
	if location is not None:
		if isinstance(location, str):
			location = Path(location)
		if not location.exists():
			print('Invalid location')
			exit(0)
	else:
		if platform.system() == "Darwin":
			location = '/Applications'
			dist += '.app'
		elif platform.system() == "Windows":
			print('Install not supported on this platform')
			print('Please copy the executable from build-to-app/dist/LevityDash.exe to your desired location')
			exit(0)
		elif platform.system() == "Linux":
			location = '/usr/bin'

	location = location or '/Applications'

	if not isinstance(location, Path):
		location = Path(location)

	print(f"Installing to... {location}")

	try:
		dist = Path(dist)
		file_name = dist.name
		if dist.suffixes and dist.is_file():
			file_name += ''.join(dist.suffixes)

		output = location / file_name

		if output.exists() and (arg_parser.force_install or arg_parser.reinstall):
			if output.is_dir():
				shutil.rmtree(output)
			else:
				output.unlink()

		if dist.is_file():
			shutil.copy(dist, location / file_name)
		else:
			shutil.copytree(dist, location / file_name)
	except FileExistsError:
		print('LevityDash already installed, use --force-install to overwrite')
		exit(0)
	except Exception as e:
		print("Install failed...")
		raise e


if __name__ == '__main__':
	build()
