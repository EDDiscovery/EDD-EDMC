#!/usr/bin/env python3
# requires pip install watchdog

import sys
import time
import logging
import re
import sys
import os
from os.path import dirname, expanduser, isdir, join
from time import gmtime, time, localtime, strftime, strptime
from sys import platform

import tkinter as tk
import tkinter.filedialog as tkfiledialog
import tkinter.font
import tkinter.messagebox
import plug

from config import appname, applongname, appversion, config
from l10n import Translations

from monitor import monitor
from ttkHyperlinkLabel import HyperlinkLabel

import prefs


class Application(object):

    def __init__(self, master=None):
        self.w = master
        self.w.title(appname)
        self.w.rowconfigure(0, weight=1)
        self.w.columnconfigure(0, weight=1)

        frame = tk.Frame(self.w, name=appname.lower())
        frame.grid(sticky=tk.NSEW)
        frame.columnconfigure(1, weight=1)

        self.cmdr_label = tk.Label(frame)
        self.ship_label = tk.Label(frame)
        self.system_label = tk.Label(frame)
        self.station_label = tk.Label(frame)

        self.cmdr_label.grid(row=1, column=0, sticky=tk.W)
        self.ship_label.grid(row=2, column=0, sticky=tk.W)
        self.system_label.grid(row=3, column=0, sticky=tk.W)
        self.station_label.grid(row=4, column=0, sticky=tk.W)

        self.cmdr    = tk.Label(frame, compound=tk.RIGHT, anchor=tk.W, name = 'cmdr')
        self.ship    = tk.Label(frame, compound=tk.RIGHT, name = 'ship')
        self.system  = tk.Label(frame, compound=tk.RIGHT, name = 'system')
        self.station = tk.Label(frame, compound=tk.RIGHT,  name = 'station')

        self.cmdr.grid(row=1, column=1, sticky=tk.EW)
        self.ship.grid(row=2, column=1, sticky=tk.EW)
        self.system.grid(row=3, column=1, sticky=tk.EW)
        self.station.grid(row=4, column=1, sticky=tk.EW)

        self.w.wm_iconbitmap(default='EDDEDMC.ico')

        #print(f'Working folder {os.getcwd()}')

        plug.load_plugins(master)

        #print('Getting app frames')

        for plugin in plug.PLUGINS:
            appitem = plugin.get_app(frame)
            if appitem:
                tk.Frame(frame, highlightthickness=1).grid(columnspan=2, sticky=tk.EW)	# separator
                if isinstance(appitem, tuple) and len(appitem)==2:
                    row = frame.grid_size()[1]
                    appitem[0].grid(row=row, column=0, sticky=tk.W)
                    appitem[1].grid(row=row, column=1, sticky=tk.EW)
                else:
                    appitem.grid(columnspan=2, sticky=tk.EW)

        self.status = tk.Label(frame, name='status', anchor=tk.W)
        self.status.grid(columnspan=2, sticky=tk.EW)

        self.menubar = tk.Menu()
        self.file_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)

        self.file_menu.add_command(command=lambda:prefs.PreferencesDialog(self.w, self.postprefs))
        self.menubar.add_cascade(menu=self.file_menu)
        self.file_menu.add_separator()
        self.file_menu.add_command(command=self.onexit)

        self.edit_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)
        self.edit_menu.add_command(accelerator='Ctrl+C', state=tk.DISABLED, command=self.copy)
        self.menubar.add_cascade(menu=self.edit_menu)

        self.help_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)
        self.help_menu.add_command(command=self.help_about)
        self.menubar.add_cascade(menu=self.help_menu)

        self.w.config(menu=self.menubar)

        if config.get('geometry'):
            match = re.match('\+([\-\d]+)\+([\-\d]+)', config.get('geometry'))
            if match:
                if platform == 'darwin':
                    if int(match.group(2)) >= 0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
                        self.w.geometry(config.get('geometry'))
                elif platform == 'win32':
                    # Check that the titlebar will be at least partly on screen
                    import ctypes
                    from ctypes.wintypes import POINT
                    # https://msdn.microsoft.com/en-us/library/dd145064
                    MONITOR_DEFAULTTONULL = 0
                    if ctypes.windll.user32.MonitorFromPoint(POINT(int(match.group(1)) + 16, int(match.group(2)) + 16), MONITOR_DEFAULTTONULL):
                        #print(f"Windows apply geo {config.get('geometry')}")
                        self.w.geometry(config.get('geometry'))
                else:
                    self.w.geometry(config.get('geometry'))
        self.w.attributes('-topmost', config.getint('always_ontop') and 1 or 0)

        self.postprefs()

        self.w.bind_all('<<JournalEvent>>', self.journal_event)	# Journal monitoring callback
        self.w.bind_all('<<PluginError>>', self.plugin_error)	# Statusbar
        self.w.bind_all('<<Quit>>', self.onexit)		# Updater
        self.w.protocol("WM_DELETE_WINDOW", self.onexit)

    def postprefs(self):
        self.set_labels()
        monitor.start(root)
        #print("Start tick")
        self.w.after(100,self.tick)
        self.status['text'] = 'Started'


    def set_labels(self):
        self.cmdr_label['text']    = _('Cmdr') + ':'	# Main window
        self.ship_label['text']    = (monitor.state['Captain'] and _('Role') or	# Multicrew role label in main window
                                      _('Ship')) + ':'	# Main window
        self.system_label['text']  = _('System') + ':'	# Main window
        self.station_label['text'] = _('Station') + ':'	# Main window

        self.menubar.entryconfigure(1, label=_('File'))	# Menu title
        self.menubar.entryconfigure(2, label=_('Edit'))	# Menu title
        self.menubar.entryconfigure(3, label=_('Help'))	# Menu title

        self.file_menu.entryconfigure(0, label=_('Settings'))	# Item in the File menu on Windows
        self.file_menu.entryconfigure(2, label=_('Exit'))	# Item in the File menu on Windows

        self.help_menu.entryconfigure(0, label=_('About'))	# Help menu item

    def tick(self):
        self.w.after(10000,self.tick)

    def journal_event(self, event):         # called by event <<JournalEvent>> by monitor when it places an event in the queue
        while True:
            entry = monitor.get_entry()
            if not entry:
                return
            print(f'JE {entry}')
            #print(f'..Monitor state {monitor.state}')

            if entry['event'] == 'ExitProgram':
                self.onexit()
                return

            self.updatedetails()

            if not entry['event'] or not monitor.mode:
                return	# Startup or in CQC

            # Export loadout
            if entry['event'] == 'Loadout' and not monitor.state['Captain'] and config.getint('output') & config.OUT_SHIP:
                monitor.export_ship()

            # Plugins
            err = plug.notify_journal_entry(monitor.cmdr, monitor.is_beta, monitor.system, monitor.station, entry, monitor.state)
            if err:
                self.status['text'] = err

    def updatedetails(self):
        if monitor.cmdr and monitor.state['Captain']:
            self.cmdr['text'] = '%s / %s' % (monitor.cmdr, monitor.state['Captain'])
            self.ship_label['text'] = _('Role') + ':'	# Multicrew role label in main window
            self.ship.configure(state = tk.NORMAL, text = crewroletext(monitor.state['Role']), url = None)
        elif monitor.cmdr:
            if monitor.group:
                self.cmdr['text'] = '%s / %s' % (monitor.cmdr, monitor.group)
            else:
                self.cmdr['text'] = monitor.cmdr
            self.ship_label['text'] = _('Ship') + ':'	# Main window
            self.ship['text'] = monitor.state['ShipName']
            self.system['text'] = monitor.system
            self.station['text'] = monitor.station
            #print(f"Set ship {monitor.state['ShipName']}")
        else:
            self.cmdr['text'] = ''
            self.ship_label['text'] = _('Ship') + ':'	# Main window
            self.ship['text'] = ''

    def onexit(self):
        print("on exit!")
        if platform!='darwin' or self.w.winfo_rooty()>0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
            print(f"Windows save geo {self.w.geometry()}")
            config.set('geometry', '+{1}+{2}'.format(*self.w.geometry().split('+')))
        self.w.withdraw()	# Following items can take a few seconds, so hide the main window while they happen
        monitor.close()
        plug.notify_stop()
        config.close()
        self.w.destroy()

    def copy(self):
        print("Copy sel")

    def help_about(self):
        print("PY Harness for EDD")

    # Display asynchronous error from plugin
    def plugin_error(self, event=None):
        if plug.last_error.get('msg'):
            self.status['text'] = plug.last_error['msg']
            self.w.update_idletasks()
            if not config.getint('hotkey_mute'):
                hotkeymgr.play_bad()

# Run Code

# Run the app
if __name__ == "__main__":
    import tempfile

    if sys.stdout is None:      # not running in a console
        sys.stdout = sys.stderr = open(join(tempfile.gettempdir(), '%s.log' % appname), 'wt', 1)	# unbuffered not allowed for text in python3, so use line buffering

    print('%s %s %s' % (applongname, appversion, strftime('%Y-%m-%dT%H:%M:%S', localtime())))

    Translations.install(config.get('language') or None)	# Can generate errors so wait til log set up

    root = tk.Tk()
    app = Application(root)
    root.mainloop()
