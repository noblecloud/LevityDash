from LevityDash.lib.ui.fontlist import curatedFamilies, parseExtra


def test_parse_extra():
	assert parseExtra(' Fira Code, "Comic Sans MS"\nUbuntu ,') == ['Fira Code', 'Comic Sans MS', 'Ubuntu']
	assert parseExtra(None) == []


def test_curated_only_installed_and_ordered():
	installed = ['Arial', 'Roboto Mono [GOOG]', 'Zapfino', 'Fira Code']
	assert curatedFamilies(installed, ['Roboto Mono'], ['fira code', 'Missing']) == ['Roboto Mono', 'Fira Code', 'Arial']
