# Tested on 3.7.7 64 bit with:
#Package            Version
#------------------ ---------
#certifi            2020.6.20  !! BEWARE DID NOT BUILD
#certifi            2019.9.11 WORKS
#certifi            2020.11.8 WORKS
#chardet            3.0.4
#idna               2.9
#importlib-metadata 1.6.1
#keyring            21.2.1
#pathtools          0.1.2
#pip                19.2.3
#py2exe             0.9.3.2     https://github.com/albertosottile/py2exe    pip install  py2exe-0.9.3.2-cp37-none-win_amd64.whl
#pywin32-ctypes     0.2.0
#requests           2.24.0
#setuptools         41.2.0
#urllib3            1.25.9
#watchdog           0.10.2
#zipp               3.1.0
#
#run: delete dist^py setup.py py2exe

from distutils.core import setup
import py2exe
from config import appname as APPNAME, applongname as APPLONGNAME, appversion as VERSION
import os
from os.path import exists, isdir, join
import sys

import requests.certs

MAINPROG = 'eddedmc.py'
ICONAME = 'EDDEDMC.ico'
WINNAME = 'eddedmcwin'
CONSOLENAME = 'eddedmc'

DATA_FILES = [
    ('', [
        ICONAME,
        '%s/DLLs/sqlite3.dll' % (sys.base_prefix),
    ]),
    ('L10n', [join('L10n',x) for x in os.listdir('L10n') if x.endswith('.strings')]),
]

OPTIONS =  { 'py2exe':
                {
                    'dist_dir': "dist",
                    'optimize': 2,
                    'packages': [
                        'certifi',
                        'requests',
                        'keyring.backends',
                        'sqlite3',	# Included for plugins
                    ],
                    'includes': [
                        'shutil',         # Included for plugins
                        'zipfile',        # Included for plugins
                        'csv'
                    ],
                    'excludes': [
                        'distutils', '_markerlib', 'optparse', 'PIL', 'pkg_resources', 'simplejson', 'unittest'
                    ],
                }
            }

setup(
        name=APPLONGNAME,
        version=VERSION,
        data_files = DATA_FILES,
        options = OPTIONS,

        console = [
                    {   'dest_base': CONSOLENAME,
                        'script': MAINPROG,
                        'company_name': 'EDDiscovery',
                        'product_name': APPNAME,
                        'version': VERSION,
                        'copyright': '(c) 2020 Robby, (c) 2015-2019 Jonathan Harris, (c) 2020 EDCD',
                    }
                  ],


        windows = [
                    {'dest_base': WINNAME,
                     'script': MAINPROG,
                     'icon_resources': [(0, ICONAME)],
                     'company_name': 'EDDiscovery',
                     'product_name': APPNAME,
                     'version': VERSION,
                     'copyright': '(c) 2020 Robby, 2015-2019 Jonathan Harris, 2020 EDCD',
                     #'other_resources': [(24, 1, open(APPNAME+'.manifest').read())],
                     }
                    ],

        )

