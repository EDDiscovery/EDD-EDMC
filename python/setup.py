#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to build to .exe and .msi package.

.exe build is via py2exe on win32.
.msi packaging utilises Windows SDK.
"""

import os
import shutil
import sys
from py2exe import freeze
from os.path import isdir, join
from config import (
    applongname, appname, appversion, copyright, git_shorthash_from_head
)
from constants import GITVERSION_FILE

if sys.version_info[0:2] != (3, 11):
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
semver = appversion(False)
appversion_str = str(semver)
base_appversion = str(semver.truncate('patch'))

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
            'asyncio',  # No longer auto as of py3.10+py2exe 0.11
            'multiprocessing',  # No longer auto as of py3.10+py2exe 0.11
            'pkg_resources._vendor.platformdirs',  # Necessary 2023-01-17
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
            'simplejson',
            'unittest'
        ],
    }
}

DATA_FILES = [
    ('', [
        '.gitversion',  # Contains git short hash
        ICONAME,
        'EUROCAPS.TTF',
    ]),
    ('L10n', [join('L10n', x) for x in os.listdir('L10n') if x.endswith('.strings')]),
    ('plugins', PLUGINS),
]

freeze(
    version_info={
        'description': 'Conversion of EDMC to use EDDiscovery harness',
        'company_name': 'EDCD',  # Used by WinSparkle
        'product_name': appname,  # Used by WinSparkle
        'version': base_appversion,
        'product_version': appversion_str,
        'copyright': copyright,
        'language': 'English (United States)',
    },
    windows=[
        {
            'dest_base': WIN,
            'script': APP,
            'icon_resources': [(0, ICONAME)]
        }
    ],
    console=[
        {
            'dest_base': CMD,
            'script': APP
        }
    ],
    data_files=DATA_FILES,
    options=OPTIONS,
)

