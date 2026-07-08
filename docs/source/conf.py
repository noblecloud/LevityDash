# Configuration file for Sphinx documentation builder.

import os
import sys

# Add the project directory to the system path
sys.path.insert(0, os.path.abspath('../../src'))
sys.path.append(os.path.abspath("./_ext"))

# -- Project information -----------------------------------------------------

project = 'LevityDashboard'
copyright = '2023, noblecloud'
author = 'noblecloud'

# -- General configuration ---------------------------------------------------

extensions = [
	'sphinx.ext.autodoc',
	'sphinx.ext.napoleon',
	'sphinx.ext.viewcode',
	'sphinx.ext.duration',
	# 'numpydoc',
	'stateful_docmenter',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------

html_theme = 'alabaster'
html_static_path = ['_static']

# -- Options for autodoc extension -------------------------------------------

autodoc_member_order = 'bysource'
autodoc_default_options = {
	'members': True,
	'undoc-members': True,
	'private-members': True,
	'special-members': False,
	'show-inheritance': True,
}

autodoc_modules = [
	'LevityDash.lib.stateful_mixins',
]

# -- Options for napoleon extension ------------------------------------------

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = False
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
