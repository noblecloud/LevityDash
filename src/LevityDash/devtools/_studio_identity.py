"""Dev-only: make the Studio a program of its own: a name and an icon that differ from the LevityDash display's.

Without this the Studio runs as `python` and shows the Python rocket in the Dock. `apply` sets, best effort and never
fatal:

- Linux: the kernel's process name (`prctl`, 15 characters), which `top` and `ps -o comm` show.
- macOS: the process name (`NSProcessInfo`), the bundle name the menu bar and Dock use (`CFBundleName` and
  `CFBundleDisplayName` in the main bundle's info dictionary), and the Dock icon (`NSApplication`), all through the
  Objective-C runtime with `ctypes`, so no new dependency. Activity Monitor lists the executable's own name for a
  process that is not an app bundle; the Dock and the menu bar show the name set here.
"""
import ctypes
import ctypes.util
import sys
from pathlib import Path

NAME = 'LevityDash Studio'


def apply(icon: Path, name: str = NAME) -> bool:
	"""Name the process and set its Dock icon. True if the platform took it."""
	try:
		if sys.platform == 'darwin':
			return _darwin(icon, name)
		if sys.platform.startswith('linux'):
			return _linux(name)
	except Exception:  # noqa: BLE001  cosmetic: never stop the Studio for it
		return False
	return False


def _linux(name: str) -> bool:
	libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6')
	return libc.prctl(15, name.replace(' ', '')[:15].encode(), 0, 0, 0) == 0  # PR_SET_NAME


def _darwin(icon: Path, name: str) -> bool:
	objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
	ctypes.cdll.LoadLibrary(ctypes.util.find_library('AppKit'))
	objc.objc_getClass.restype = ctypes.c_void_p
	objc.objc_getClass.argtypes = [ctypes.c_char_p]
	objc.sel_registerName.restype = ctypes.c_void_p
	objc.sel_registerName.argtypes = [ctypes.c_char_p]
	send = objc.objc_msgSend

	def call(target, selector, *args, result=ctypes.c_void_p, argtypes=None):
		send.restype = result
		send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *(argtypes or [ctypes.c_void_p] * len(args))]
		return send(target, objc.sel_registerName(selector.encode()), *args)

	def string(text: str):
		return call(objc.objc_getClass(b'NSString'), 'stringWithUTF8String:', text.encode(), argtypes=[ctypes.c_char_p])

	text = string(name)
	call(call(objc.objc_getClass(b'NSProcessInfo'), 'processInfo'), 'setProcessName:', text)
	info = call(call(objc.objc_getClass(b'NSBundle'), 'mainBundle'), 'infoDictionary')
	if info:
		for key in ('CFBundleName', 'CFBundleDisplayName'):
			call(info, 'setObject:forKey:', text, string(key))
	image = call(call(objc.objc_getClass(b'NSImage'), 'alloc'), 'initWithContentsOfFile:', string(str(icon)))
	if image:
		call(call(objc.objc_getClass(b'NSApplication'), 'sharedApplication'), 'setApplicationIconImage:', image)
	return True
