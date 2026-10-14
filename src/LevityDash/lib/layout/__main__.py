from . import REGISTRY, pending

todo = pending()
for name, section in sorted(REGISTRY.items(), key=lambda item: (item[1].spec, item[0])):
	mark = ' ' if name in todo else 'x'
	print(f'[{mark}] {name.removeprefix("LevityDash.lib.layout.")}  <-  {section}')
print(f'{len(REGISTRY) - len(todo)} of {len(REGISTRY)} done')
