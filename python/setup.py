#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to build to .exe and .msi package.

.exe build is via py2exe on win32.
"""

import codecs
import os
import platform
import re
import shutil
import sys
from distutils.core import setup
from os.path import exists, isdir, join
from tempfile import gettempdir
from typing import Any, Generator, Set
from config import (
    appcmdname, applongname, appname, appversion, appversion_nobuild, copyright, git_shorthash_from_head, update_feed,
    update_interval
)
from constants import GITVERSION_FILE

if sys.version_info[0:2] != (3, 9):
    raise AssertionError(f'Unexpected python version {sys.version}')

###########################################################################
# Retrieve current git short hash and store in file GITVERSION_FILE
git_shorthash = git_shorthash_from_head()
if git_shorthash is None:
    exit(-1)

with open(GITVERSION_FILE, 'w+', encoding='utf-8') as gvf:
    gvf.write(git_shorthash)

print(f'Git short hash: {git_shorthash}')
###########################################################################

if sys.platform == 'win32':
    #assert platform.architecture()[0] == '32bit', 'Assumes a Python built for 32bit'
    import py2exe  # noqa: F401 # Yes, this *is* used
    dist_dir = 'dist.win32'

elif sys.platform == 'darwin':
    dist_dir = 'dist.macosx'

else:
    assert False, f'Unsupported platform {sys.platform}'

# Split version, as py2exe wants the 'base' for version
semver = appversion()
appversion_str = str(semver)
base_appversion = str(semver.truncate('patch'))

print(f'Version: {base_appversion}')

if dist_dir and len(dist_dir) > 1 and isdir(dist_dir):
    shutil.rmtree(dist_dir)

# "Developer ID Application" name for signing
macdeveloperid = None

APP = 'eddedmc.py'
WIN = 'eddedmcwin'
CMD = 'eddedmc'
ICONAME = 'EDDEDMC.ico'
PLUGINS = [
    'plugins/coriolis.py',
    'plugins/eddb.py',
    'plugins/edsm.py',
    'plugins/edsy.py',
    'plugins/inara.py',
]

OPTIONS = {
    'py2exe': {
        'dist_dir': dist_dir,
        'optimize': 2,
        'packages': [
            'sqlite3',  # Included for plugins
        ],
        'includes': [
            'dataclasses',
            'shutil',  # Included for plugins
            'timeout_session',
            'zipfile',  # Included for plugins
        ],
        'excludes': [
            'distutils',
            '_markerlib',
            'optparse',
            'PIL',
            'pkg_resources',
            'simplejson',
            'unittest'
        ],
    }
}

DATA_FILES = [
    ('', [
        ICONAME,
        'EUROCAPS.TTF',
        'commodity.csv',
        'rare_commodity.csv',
        'snd_good.wav',
        'snd_bad.wav',
        'modules.p',
        'ships.p',
        'stations.p',
        'systems.p',
        '%s/DLLs/sqlite3.dll' % (sys.base_prefix),
    ]),
    ('L10n', [join('L10n', x) for x in os.listdir('L10n') if x.endswith('.strings')]),
    ('plugins', PLUGINS),
]

setup(
    name=applongname,
    version=appversion_str,
    windows=[
        {
            'dest_base': WIN,
            'script': APP,
            'icon_resources': [(0, ICONAME)],
            'company_name': 'EDDiscovery',
            'product_name': appname,
            'version': base_appversion,
            'product_version': appversion_str,
            'copyright': copyright,
            #'other_resources': [(24, 1, open(f'{appcmdname}.manifest').read())],
        }
    ],
    console=[
        {
            'dest_base': CMD,
            'script': APP,
            'company_name': 'EDDiscovery',
            'product_name': appname,
            'version': base_appversion,
            'product_version': appversion_str,
            'copyright': copyright,
        }
    ],
    data_files=DATA_FILES,
    options=OPTIONS,
)

