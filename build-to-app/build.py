#!/usr/bin/env python

from rich.logging import RichHandler
import logging

FORMAT = "%(message)s"
logging.basicConfig(
	level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler(
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

os.chdir("..")

PyInstaller.config.CONF['noconfirm'] = True
PyInstaller.config.CONF['pathx'] = ['../src/LevityDash']


def get_sig():
	def inputSig():
		sig = input('Enter Apple ID for app signature: ')
		with open('build/.signature', 'w') as f:
			f.write(sig)
		return sig

	try:
		with open('build/.signature', 'r') as f:
			sig = f.read()
		return sig or inputSig()
	except FileNotFoundError:
		return inputSig()


try:
	if platform.system() == "Darwin":
		sig = get_sig()
		os.environ['CODE_SIGN_IDENTITY'] = sig
		main.run(
			[
				"./build/macOS.spec",
				'--noconfirm',
			]
		)
	elif platform.system() == "Windows":
		pass
	elif platform.system() == "Linux":
		main.run(
			[
				"./build/linux.spec",
				'--noconfirm'
			]
		)
	else:
		print("Unsupported platform")
except Exception as e:
	print(e)
	print("Error")
else:
	print("Success")
