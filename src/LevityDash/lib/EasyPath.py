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
	_basePath: Path

	def __new__(cls, path: Path, make: bool = False):
		if hasattr(path, 'path'):
			path = path.path
		path = Path(path)
		if make and not path.exists():
			if path.suffix:
				path.parent.mkdir(parents=True, exist_ok=True)
				path.touch()
			else:
				path.mkdir(parents=True)
		cls = EasyPath if path.is_dir() else EasyPathFile
		return super().__new__(cls)

	def __init__(self, path: str | Path, make: bool = False):
		if hasattr(path, 'path'):
			path = path.path
		self._basePath = Path(path)

	def __getattr__(self, name: str):
		if name in dir(self) or name.startswith('_'):
			return super().__getattribute__(name)
		path = self._basePath.joinpath(name)
		if path.exists():
			return EasyPath(path)
		return getattr(super().__getattribute__('path'), name)

	def __getitem__(self, name: str):
		if isinstance(name, int):
			return
		path = self._basePath.joinpath(name)
		if path.is_dir():
			return EasyPath(path)
		return EasyPathFile(path)

	def __truediv__(self, other) -> 'EasyPath':
		if isinstance(self, EasyPathFile):
			raise TypeError('Cannot divide a file by a directory')
		p = self._basePath / other
		return EasyPath(p) if p.is_dir() else EasyPathFile(p)

	@property
	def path(self) -> Path:
		return self._basePath

	@property
	def parent(self) -> 'EasyPath':
		return EasyPath(self._basePath.parent)

	def up(self, n: int = 1) -> 'EasyPath':
		if n < 1:
			n = 1
		up = self._basePath
		for _ in range(n):
			up = up.parent
		return EasyPath(up)

	def ls(self):
		return [EasyPath(x) for x in self._basePath.iterdir()]

	@property
	def isDir(self):
		return self._basePath.is_dir()

	@property
	def isFile(self):
		return self._basePath.is_file()

	def __repr__(self):
		return f'EasyPath(dir={self._basePath.name})'

	def __str__(self):
		return str(self._basePath.name)

	def asDict(self, recursive: bool = True, depth: int = 5, hiddenFiles: bool = False):
		if depth <= 0:
			return self
		return {item.name: item if item.isFile else item.asDict(recursive=recursive, depth=depth - 1) for item in self.ls() if not item.name.startswith('.') or hiddenFiles}

	def __contains__(self, item) -> bool:
		if self.isDir:
			if isinstance(item, str):
				if any(i not in item for i in ('.', '..', '/', '\\')):
					return self.path.joinpath(item).exists()
				path = Path(item).absolute().as_posix()
			elif isinstance(item, Path):
				path = item.absolute().as_posix()
			elif isinstance(item, EasyPath):
				path = item.path.absolute().as_posix()
			else:
				raise TypeError(f'{repr(item)} is not a valid type for comparison')
			return path.startswith(self.path.absolute().as_posix())
		return False

	def __eq__(self, other):
		own = self._basePath.absolute()
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

	def __init__(self, basePath: str | Path, make: bool = False):
		super().__init__(basePath)
		if not self._basePath.is_file():
			raise FileNotFoundError(f'{self._basePath} is not a file')

	def __repr__(self):
		return f'EasyPath(file={self._basePath.name})'

	@property
	def extension(self) -> str:
		return self._basePath.suffix[1:]
