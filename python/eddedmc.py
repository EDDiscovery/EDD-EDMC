#!/usr/bin/env python3
# requires pip install watchdog

import os
import sys
import time
import logging
import re

from os.path import dirname, expanduser, isdir, join
from time import gmtime, time, localtime, strftime, strptime
from sys import platform
from theme import theme
from ttkHyperlinkLabel import openurl

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

import companion

#import commodity
#import td

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

        self.newversion_button = tk.Button(frame, text='NewVersion', width=28, default=tk.ACTIVE)	# Update button in main window
        row = frame.grid_size()[1]
        self.newversion_button.grid(row=row, columnspan=2, sticky=tk.NSEW)
        self.newversion_button.grid_remove();

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

        theme.register(self.menubar)	# menus and children aren't automatically registered
        theme.register(self.file_menu)
        theme.register(self.edit_menu)
        theme.register(self.help_menu)

        self.theme_icon = tk.PhotoImage(data = 'R0lGODlhFAAQAMZQAAoKCQoKCgsKCQwKCQsLCgwLCg4LCQ4LCg0MCg8MCRAMCRANChINCREOChIOChQPChgQChgRCxwTCyYVCSoXCS0YCTkdCTseCT0fCTsjDU0jB0EnDU8lB1ElB1MnCFIoCFMoCEkrDlkqCFwrCGEuCWIuCGQvCFs0D1w1D2wyCG0yCF82D182EHE0CHM0CHQ1CGQ5EHU2CHc3CHs4CH45CIA6CIE7CJdECIdLEolMEohQE5BQE41SFJBTE5lUE5pVE5RXFKNaFKVbFLVjFbZkFrxnFr9oFsNqFsVrF8RsFshtF89xF9NzGNh1GNl2GP+KG////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////yH5BAEKAH8ALAAAAAAUABAAAAeegAGCgiGDhoeIRDiIjIZGKzmNiAQBQxkRTU6am0tPCJSGShuSAUcLoIIbRYMFra4FAUgQAQCGJz6CDQ67vAFJJBi0hjBBD0w9PMnJOkAiJhaIKEI7HRoc19ceNAolwbWDLD8uAQnl5ga1I9CHEjEBAvDxAoMtFIYCBy+kFDKHAgM3ZtgYSLAGgwkp3pEyBOJCC2ELB31QATGioAoVAwEAOw==')
        self.theme_minimize = tk.BitmapImage(data = '#define im_width 16\n#define im_height 16\nstatic unsigned char im_bits[] = {\n   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,\n   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfc, 0x3f,\n   0xfc, 0x3f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };\n')
        self.theme_close    = tk.BitmapImage(data = '#define im_width 16\n#define im_height 16\nstatic unsigned char im_bits[] = {\n   0x00, 0x00, 0x00, 0x00, 0x0c, 0x30, 0x1c, 0x38, 0x38, 0x1c, 0x70, 0x0e,\n   0xe0, 0x07, 0xc0, 0x03, 0xc0, 0x03, 0xe0, 0x07, 0x70, 0x0e, 0x38, 0x1c,\n   0x1c, 0x38, 0x0c, 0x30, 0x00, 0x00, 0x00, 0x00 };\n')

        self.theme_menubar = tk.Frame(frame)
        self.theme_menubar.columnconfigure(2, weight=1)
        theme_titlebar = tk.Label(self.theme_menubar, text=applongname, image=self.theme_icon, cursor='fleur', anchor=tk.W, compound=tk.LEFT)
        theme_titlebar.grid(columnspan=3, padx=2, sticky=tk.NSEW)
        self.drag_offset = None
        theme_titlebar.bind('<Button-1>', self.drag_start)
        theme_titlebar.bind('<B1-Motion>', self.drag_continue)
        theme_titlebar.bind('<ButtonRelease-1>', self.drag_end)
        theme_minimize = tk.Label(self.theme_menubar, image=self.theme_minimize)
        theme_minimize.grid(row=0, column=3, padx=2)
        theme.button_bind(theme_minimize, self.oniconify, image=self.theme_minimize)
        theme_close = tk.Label(self.theme_menubar, image=self.theme_close)
        theme_close.grid(row=0, column=4, padx=2)
        theme.button_bind(theme_close, self.onexit, image=self.theme_close)
        self.theme_file_menu = tk.Label(self.theme_menubar, anchor=tk.W)
        self.theme_file_menu.grid(row=1, column=0, padx=5, sticky=tk.W)
        theme.button_bind(self.theme_file_menu, lambda e: self.file_menu.tk_popup(e.widget.winfo_rootx(), e.widget.winfo_rooty() + e.widget.winfo_height()))
        self.theme_edit_menu = tk.Label(self.theme_menubar, anchor=tk.W)
        self.theme_edit_menu.grid(row=1, column=1, sticky=tk.W)
        theme.button_bind(self.theme_edit_menu, lambda e: self.edit_menu.tk_popup(e.widget.winfo_rootx(), e.widget.winfo_rooty() + e.widget.winfo_height()))
        self.theme_help_menu = tk.Label(self.theme_menubar, anchor=tk.W)
        self.theme_help_menu.grid(row=1, column=2, sticky=tk.W)
        theme.button_bind(self.theme_help_menu, lambda e: self.help_menu.tk_popup(e.widget.winfo_rootx(), e.widget.winfo_rooty() + e.widget.winfo_height()))
        tk.Frame(self.theme_menubar, highlightthickness=1).grid(columnspan=5, padx=5, sticky=tk.EW)
        theme.register(self.theme_minimize)	# images aren't automatically registered
        theme.register(self.theme_close)
        self.blank_menubar = tk.Frame(frame)
        tk.Label(self.blank_menubar).grid()
        tk.Label(self.blank_menubar).grid()
        tk.Frame(self.blank_menubar, height=2).grid()
        theme.register_alternate((self.menubar, self.theme_menubar, self.blank_menubar), {'row':0, 'columnspan':2, 'sticky':tk.NSEW})
        self.w.resizable(tk.TRUE, tk.FALSE)

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

        theme.register(frame)
        theme.apply(self.w)

        self.postprefs()

        self.newversion_button.bind('<Button-1>', self.updateurl)

        self.w.bind('<Map>', self.onmap)			# Special handling for overrideredict
        self.w.bind('<Enter>', self.onenter)			# Special handling for transparency
        self.w.bind('<FocusIn>', self.onenter)			#   "
        self.w.bind('<Leave>', self.onleave)			#   "
        self.w.bind('<FocusOut>', self.onleave)			#   "

        self.w.bind_all('<<JournalEvent>>', self.journal_event)	# Journal monitoring callback
        self.w.bind_all('<<PluginError>>', self.plugin_error)	# Statusbar
        self.w.bind_all('<<Quit>>', self.onexit)		# Updater
        self.w.protocol("WM_DELETE_WINDOW", self.onexit)
        self.w.bind('<Control-c>', self.copy)

        self.lastmarket = None

    def postprefs(self):
        self.set_labels()
        monitor.start(root)
        self.status['text'] = 'Started'


    def set_labels(self):
        self.cmdr_label['text']    = _('Cmdr') + ':'	# Main window
        self.ship_label['text']    = (monitor.state['Captain'] and _('Role') or	# Multicrew role label in main window
                                      _('Ship')) + ':'	# Main window
        self.system_label['text']  = _('System') + ':'	# Main window
        self.station_label['text'] = _('Station') + ':'	# Main window

        # self.button['text'] = _('Update')	# Update button in main window
        # not yet self.button['state'] = tk.NORMAL

        self.menubar.entryconfigure(1, label=_('File'))	# Menu title
        self.menubar.entryconfigure(2, label=_('Edit'))	# Menu title
        self.menubar.entryconfigure(3, label=_('Help'))	# Menu title

        self.theme_file_menu['text'] = _('File')	# Menu title
        self.theme_edit_menu['text'] = _('Edit')	# Menu title
        self.theme_help_menu['text'] = _('Help')	# Menu title

        self.file_menu.entryconfigure(0, label=_('Settings'))	# Item in the File menu on Windows
        self.file_menu.entryconfigure(2, label=_('Exit'))	# Item in the File menu on Windows

        self.help_menu.entryconfigure(0, label=_('About'))	# Help menu item

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

            if entry['event'] == 'Market'  and not monitor.state['Captain']:
                lastmarket = entry

            if entry['event'] == 'Harness-NewVersion':
                self.newversion_button['text'] = '!! New version Available:' + entry['Version']
                self.newversion_button.grid()
                #self.status['text'] = 'New version'

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
            #print(f"Update details {monitor.system} {monitor.station}")
            if monitor.group:
                self.cmdr['text'] = '%s / %s' % (monitor.cmdr, monitor.group)
            else:
                self.cmdr['text'] = monitor.cmdr
            self.ship_label['text'] = _('Ship') + ':'	# Main window
            self.ship['text'] = monitor.state['ShipName']
            self.system['text'] = monitor.system
            if monitor.station is None:
                self.station['text'] = ''
            else:
                self.station['text'] = monitor.station
        else:
            self.cmdr['text'] = ''
            self.ship_label['text'] = _('Ship') + ':'	# Main window
            self.ship['text'] = ''

        self.edit_menu.entryconfigure(0, state=monitor.system and tk.NORMAL or tk.DISABLED)	# Copy


    def onexit(self, event=None):
        print("on exit!")
        if platform!='darwin' or self.w.winfo_rooty()>0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
            print(f"Windows save geo {self.w.geometry()}")
            config.set('geometry', '+{1}+{2}'.format(*self.w.geometry().split('+')))
        self.w.withdraw()	# Following items can take a few seconds, so hide the main window while they happen
        monitor.close()
        plug.notify_stop()
        config.close()
        self.w.destroy()

    def drag_start(self, event):
        self.drag_offset = (event.x_root - self.w.winfo_rootx(), event.y_root - self.w.winfo_rooty())

    def drag_continue(self, event):
        if self.drag_offset:
            self.w.geometry('+%d+%d' % (event.x_root - self.drag_offset[0], event.y_root - self.drag_offset[1]))

    def drag_end(self, event):
        self.drag_offset = None

    def oniconify(self, event=None):
        self.w.overrideredirect(0)	# Can't iconize while overrideredirect
        self.w.iconify()
        self.w.update_idletasks()	# Size and windows styles get recalculated here
        self.w.wait_visibility()	# Need main window to be re-created before returning
        theme.active = None		# So theme will be re-applied on map

    def onmap(self, event=None):
        if event.widget == self.w:
            theme.apply(self.w)

    def onenter(self, event=None):
        if config.getint('theme') > 1:
            self.w.attributes("-transparentcolor", '')
            self.blank_menubar.grid_remove()
            self.theme_menubar.grid(row=0, columnspan=2, sticky=tk.NSEW)

    def onleave(self, event=None):
        if config.getint('theme') > 1 and event.widget==self.w:
            self.w.attributes("-transparentcolor", 'grey4')
            self.theme_menubar.grid_remove()
            self.blank_menubar.grid(row=0, columnspan=2, sticky=tk.NSEW)

    def copy(self):
        if monitor.system:
            self.w.clipboard_clear()
            self.w.clipboard_append(monitor.station and '%s,%s' % (monitor.system, monitor.station) or monitor.system)

    def updateurl(self, event=None):
        openurl('https://github.com/EDDiscovery/EDD-EDMC/releases')


    def help_about(self):
        tk.messagebox.showinfo(
            f'EDD-EDMC: {appversion}',
                "This program supports EDMC plugins for EDD/EDDLite\r\n\r\n"
                "Install this program, then run it, then close the program\r\n"
                "This installs the adaptors into EDD/EDDLite\r\n\r\n"
                "Then run EDD/EDDLite and they will automatically start and stop this program\r\n\r\n"
                "Place plugins in %appdatalocal%\edd-edmc\plugins\r\n"

            )

    # Display asynchronous error from plugin
    def plugin_error(self, event=None):
        if plug.last_error.get('msg'):
            self.status['text'] = plug.last_error['msg']
            self.w.update_idletasks()

    def getandsend(self,event = None):
        # will be used if I bother to turn back on export
        print("*** get and send - not implememented yet, turn on button above**")

        if config.getint('output') & (config.OUT_MKT_CSV|config.OUT_MKT_TD):
            if not lastmarket is None:
                print("Lastmarket set")
                if config.getint('output') & config.OUT_MKT_CSV:    # would need to fix the exporters
                    commodity.export(lastmarket, COMMODITY_CSV)
                if config.getint('output') & config.OUT_MKT_TD:
                    td.export(lastmarket)



# Run Code

# Run the app
if __name__ == "__main__":
    import tempfile

    stdoutnotpresent = sys.stdout is None
    packaged = getattr(sys, 'frozen', False)
    redirectedlogoutpath = join(tempfile.gettempdir(), '%s.log' % appname)

    if stdoutnotpresent or packaged == 'windows_exe':      # if no std out, or running packaged in windows_exe (if running packaged from console its console_exe)
        sys.stdout = sys.stderr = open(redirectedlogoutpath, 'wt', 1)	# unbuffered not allowed for text in python3, so use line buffering

    print('%s %s %s' % (applongname, appversion, strftime('%Y-%m-%dT%H:%M:%S', localtime())))
    print(f"nostdout {stdoutnotpresent} packaged {packaged}")

    Translations.install(config.get('language') or None)	# Can generate errors so wait til log set up

    root = tk.Tk()

    # NEW! make sure EDDLite and EDDiscovery has the interface DLL

    import shutil

    source = join(os.getcwd(),"EDMCHarness.dll")

    if os.path.exists(source):
        dllfolder = os.path.abspath(join(config.app_dir,'..\EDDLite\DLL'))
        dllfolder2 = os.path.abspath(join(config.app_dir,'..\EDDiscovery\DLL'))

        if not isdir(dllfolder):
            os.makedirs(dllfolder)

        if not isdir(dllfolder2):
            os.makedirs(dllfolder2)

        dest = join(dllfolder,"EDMCHarness.dll")
        dest2 = join(dllfolder2,"EDMCHarness.dll")

        print(f"DLL folder {source} to {dest}")
        try:
            shutil.copyfile(source,dest)
        except:
            e = sys.exc_info()[0]
            print(f"Cannot copy DLL {e} - it may be in use")

        print(f"DLL folder {source} to {dest2}")
        try:
            shutil.copyfile(source,dest2)
        except:
            e = sys.exc_info()[0]
            print(f"Cannot copy DLL {e} - it may be in use")

        if not os.path.exists(dest):
            print(f"{dest} not installed!")
        if not os.path.exists(dest2):
            print(f"{dest2} not installed!")

    else:
        print("Harness DLL not present")

    app = Application(root)
    root.mainloop()
