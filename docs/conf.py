"""Sphinx 文档配置"""

import os
import sys

sys.path.insert(0, os.path.abspath('..'))

project = 'QuickLauncher'
copyright = '2026, NAYTON'
author = 'NAYTON'
version = '1.5.6'
release = '1.5.6.5'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
language = 'zh_CN'

html_theme = 'alabaster'
html_static_path = ['_static']

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
