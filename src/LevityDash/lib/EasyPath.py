from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass
class FileLocation:
	path: Path
	name: str
	extension: str = '.levity'

	def __post_init__(self):
		if self.path.is_file():
			self.path = self.path.parent
		if self.name.endswith(self.extension):
			self.name = self.name[:-len(self.extension)].strip('.')
			self.extension = self.extension.strip('.')
		elif '.' in self.name:
			path = self.name.split('.')
			self.name = '.'.join(path[:-1])
			self.extension = '.' + path[-1]

	@property
	def fullPath(self) -> Path:
		return self.path.joinpath(self.fileName)

	@property
	def fileName(self):
		return f'{self.name.rstrip(".")}.{self.extension.lstrip(".")}'

	@property
	def asTuple(self) -> Tuple[Path, str]:
		return self.path, self.fileName


class EasyPath:
	__basePath: Path

	def __new__(cls, path: Path):
		if hasattr(path, 'path'):
			path = path.path
		path = Path(path)
		cls = EasyPath if path.is_dir() else EasyPathFile
		return super().__new__(cls)

	def __init__(self, path: str | Path):
		if hasattr(path, 'path'):
			path = path.path
		self.__basePath = Path(path)

	def __getattr__(self, name: str):
		if name in dir(self) or name.startswith('_'):
			return super().__getattribute__(name)
		path = self.__basePath.joinpath(name)
		if path.exists():
			return EasyPath(path)
		return getattr(super().__getattribute__('path'), name)

	def __getitem__(self, name: str):
		if isinstance(name, int):
			return
		path = self.__basePath.joinpath(name)
		if path.is_dir():
			return EasyPath(path)
		return EasyPathFile(path)

	@property
	def path(self) -> Path:
		return self.__basePath

	def up(self, n: int = 1) -> 'EasyPath':
		if n < 1:
			n = 1
		up = self.__basePath
		for _ in range(n):
			up = up.parent
		return EasyPath(up)

	def ls(self):
		return [EasyPath(x) for x in self.__basePath.iterdir()]

	@property
	def isDir(self):
		return self.__basePath.is_dir()

	@property
	def isFile(self):
		return self.__basePath.is_file()

	def __repr__(self):
		return f'EasyPath(dir={self.__basePath.name})'

	def __str__(self):
		return str(self.__basePath.name)

	def asDict(self, recursive: bool = True, depth: int = 5, hiddenFiles: bool = False):
		if depth <= 0:
			return self
		return {item.name: item if item.isFile else item.asDict(recursive=recursive, depth=depth - 1) for item in self.ls() if not item.name.startswith('.') or hiddenFiles}

	def __contains__(self, item):
		if self.isDir:
			if isinstance(item, str) and any(i not in item for i in ('.', '..', '/', '\\')):
				return self.path.joinpath(item).exists()

	def __eq__(self, other):
		own = self.__basePath.absolute()
		match other:
			case EasyPath() | EasyPathFile():
				return own == other.path.absolute()
			case str():
				return own == Path(other).absolute()
			case Path():
				return own == other.absolute()
			case None:
				return False
			case _:
				raise TypeError(f'{repr(other)} is not a valid type for comparison')


class EasyPathFile(EasyPath):
	def __init__(self, basePath: str | Path):
		super().__init__(basePath)
		self.__basePath = basePath
		if not self.__basePath.is_file():
			raise FileNotFoundError(f'{self.__basePath} is not a file')

	def __repr__(self):
		return f'EasyPath(file={self.__basePath.name})'
