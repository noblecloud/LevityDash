import logging


class _SmartDictionary(dict):
	_flipped: dict

	# allow for property access to subscript keys
	def __getattr__(self, item):
		try:
			return self[item]
		except KeyError:
			try:
				return self.flat[item]
			except KeyError:
				try:
					return self.flat.flip[item]
				except KeyError:
					self.__getattribute__(item)
			# logging.warning('Invalid attribute ({}) of {}'.format(item, self.__class__))
			raise AttributeError

	def __getitem__(self, item):
		if isinstance(item, tuple):
			return [dict(self)[x] for x in item]
		try:
			return dict(self)[item]
		except KeyError:
			try:
				return dict(self.flat)[item]
			except KeyError:
				try:
					return dict(self.flat.flip)[item]
				except KeyError:
					self.__getattribute__(item)
			except TypeError:
				logging.warning('Invalid attribute ({}) of {}'.format(item, self.__class__))
			raise AttributeError

	def __init__(self, *args, **kwargs):
		super(_SmartDictionary, self).__init__(*args, **kwargs)

	def __repr__(self):
		return self.pretty(self).rstrip('\n')

	def __str__(self):
		return super().__str__()

	def update(self, values, **kwargs):
		super(_SmartDictionary, self).update(values, **kwargs)

	@staticmethod
	def pretty(d, indent=0):
		string = ''
		tab = '  '
		if len(d.items()) > 4:
			for key, value in d.items():
				string += '{}{}:'.format(tab * indent, str(key))
				if isinstance(value, dict):
					string += '\n' + d.pretty(value, indent + 1)
				else:
					string += ' {}\n'.format(str(value))
		else:
			# string += tab * indent
			for key, value in d.items():
				string += '{}{}:'.format(tab * indent, str(key))
				if isinstance(value, dict):
					string += d.pretty(value, indent + 1)
				else:
					string += ' {}\t'.format(str(value))
			string += '\n'
		return string

	def _flat(self):
		logging.debug("Attempting to flatten lowest dictionary is not possible:", self)
		return self

	def _flip(self):
		return {value: key for key, value in self.items()}

	@property
	def flat(self):
		return self._flat()

	@property
	def flip(self):
		return self._flip()


class SmartDictionary(_SmartDictionary):

	# def __getitem__(self, item):
	# 	try:
	# 		super().__getitem__(item)
	# 	except KeyError:
	# 		logging.warning('Improper key ({}) usage of {}'.format(item, self.__class__))
	# 		raise KeyError

	def __init__(self, *args, **kwargs):
		super(_SmartDictionary, self).__init__(*args, **kwargs)

	def _flat(self):
		flat = SmartDictionary()
		failed = False
		failedArray = []
		for key, value in self.items():
			if issubclass(key.__class__, dict):
				failed = True
				failedArray.append(key)
			else:
				try:
					flat.update(value.flat)
				except AttributeError:
					flat.update({key: value})
				# try:
				# 	flat.update({value: key})
				# except TypeError:
				# 	failed = True
				# 	failedArray.append(key)
				except TypeError:
					pass
		if failed:
			logging.warning('Some keys could not be flattened')
		if failedArray:
			logging.debug(failedArray)

		return flat

	@property
	def flat(self):
		return self._flat()

	@property
	def flip(self):
		return self._flip()

	def _flip(self):
		flip = self.copy()
		failed = False
		failedArray = []
		for key, value in self.items():
			if issubclass(key.__class__, _SmartDictionary):
				flip[key] = value.flip
				failedArray.append(key)
			elif isinstance(value, dict):
				flip[key] = _SmartDictionary({v: k for k, v in value.items()})
			else:
				try:
					flip.update(value.flip)
				except AttributeError:
					flip.update({value: key})
					# try:
					# 	flip.update({value: key})
					# except TypeError:
					# 	failed = True
					# 	failedArray.append(key)
				except TypeError:
					pass
		if failed:
			logging.warning('Some keys could not be flipped')
		if failedArray:
			logging.debug(failedArray)

		return SmartDictionary(flip)
