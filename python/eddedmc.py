#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the main GUI application."""

import os
import html
import locale
import pathlib
import re
import sys
from builtins import object, str
from os import chdir, environ
from os.path import dirname, join, isdir
from sys import platform
from time import localtime, strftime, time
from typing import TYPE_CHECKING, Optional, Tuple

# Have this as early as possible for people running EDMarketConnector.exe
# from cmd.exe or a bat file or similar.  Else they might not be in the correct
# place for things like config.py reading .gitversion
if getattr(sys, 'frozen', False):
    # Under py2exe sys.path[0] is the executable name
    if platform == 'win32':
        chdir(dirname(sys.path[0]))
        # Allow executable to be invoked from any cwd
        environ['TCL_LIBRARY'] = join(dirname(sys.path[0]), 'lib', 'tcl')
        environ['TK_LIBRARY'] = join(dirname(sys.path[0]), 'lib', 'tk')

else:
    # We still want to *try* to have CWD be where the main script is, even if
    # not frozen.
    chdir(pathlib.Path(__file__).parent)

from constants import applongname, appname, protocolhandler_redirect

# config will now cause an appname logger to be set up, so we need the
# console redirect before this
if __name__ == '__main__':
    # Keep this as the very first code run to be as sure as possible of no
    # output until after this redirect is done, if needed.
    if getattr(sys, 'frozen', False):
        # By default py2exe tries to write log to dirname(sys.executable) which fails when installed
        import tempfile

        # unbuffered not allowed for text in python3, so use `1 for line buffering
        sys.stdout = sys.stderr = open(join(tempfile.gettempdir(), f'{appname}.log'), mode='wt', buffering=1)
    # TODO: Test: Make *sure* this redirect is working, else py2exe is going to cause an exit popup

# These need to be after the stdout/err redirect because they will cause
# logging to be set up.
# isort: off
import killswitch
from config import appversion, appversion_nobuild, config, copyright
# isort: on

from EDMCLogging import edmclogger, logger, logging
from journal_lock import JournalLock, JournalLockResult


if __name__ == '__main__':  # noqa: C901
    def handle_edmc_callback_or_foregrounding() -> None:  # noqa: CCR001
        """Handle any edmc:// auth callback, else foreground existing window."""
        logger.trace('Begin...')
    
        if platform == 'win32':
    
            # If *this* instance hasn't locked, then another already has and we
            # now need to do the edmc:// checks for auth callback
            if locked != JournalLockResult.LOCKED:
                import ctypes
                from ctypes.wintypes import BOOL, HWND, INT, LPARAM, LPCWSTR, LPWSTR
    
                EnumWindows = ctypes.windll.user32.EnumWindows  # noqa: N806
                GetClassName = ctypes.windll.user32.GetClassNameW  # noqa: N806
                GetClassName.argtypes = [HWND, LPWSTR, ctypes.c_int]
                GetWindowText = ctypes.windll.user32.GetWindowTextW  # noqa: N806
                GetWindowText.argtypes = [HWND, LPWSTR, ctypes.c_int]
                GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW  # noqa: N806
                GetProcessHandleFromHwnd = ctypes.windll.oleacc.GetProcessHandleFromHwnd  # noqa: N806
    
                SW_RESTORE = 9  # noqa: N806
                SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow  # noqa: N806
                ShowWindow = ctypes.windll.user32.ShowWindow  # noqa: N806
                ShowWindowAsync = ctypes.windll.user32.ShowWindowAsync  # noqa: N806
    
                COINIT_MULTITHREADED = 0  # noqa: N806,F841
                COINIT_APARTMENTTHREADED = 0x2  # noqa: N806
                COINIT_DISABLE_OLE1DDE = 0x4  # noqa: N806
                CoInitializeEx = ctypes.windll.ole32.CoInitializeEx  # noqa: N806
    
                ShellExecute = ctypes.windll.shell32.ShellExecuteW  # noqa: N806
                ShellExecute.argtypes = [HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT]
    
                def window_title(h: int) -> Optional[str]:
                    if h:
                        text_length = GetWindowTextLength(h) + 1
                        buf = ctypes.create_unicode_buffer(text_length)
                        if GetWindowText(h, buf, text_length):
                            return buf.value
    
                    return None
    
                @ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
                def enumwindowsproc(window_handle, l_param):  # noqa: CCR001
                    """
                    Determine if any window for the Application exists.
    
                    Called for each found window by EnumWindows().
    
                    When a match is found we check if we're being invoked as the
                    edmc://auth handler.  If so we send the message to the existing
                    process/window.  If not we'll raise that existing window to the
                    foreground.
                    :param window_handle: Window to check.
                    :param l_param: The second parameter to the EnumWindows() call.
                    :return: False if we found a match, else True to continue iteration
                    """
                    # class name limited to 256 - https://msdn.microsoft.com/en-us/library/windows/desktop/ms633576
                    cls = ctypes.create_unicode_buffer(257)
                    # This conditional is exploded to make debugging slightly easier
                    if GetClassName(window_handle, cls, 257):
                        if cls.value == 'TkTopLevel':
                            if window_title(window_handle) == applongname:
                                if GetProcessHandleFromHwnd(window_handle):
                                    # If GetProcessHandleFromHwnd succeeds then the app is already running as this user
                                    if len(sys.argv) > 1 and sys.argv[1].startswith(protocolhandler_redirect):
                                        CoInitializeEx(0, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)
                                        # Wait for it to be responsive to avoid ShellExecute recursing
                                        ShowWindow(window_handle, SW_RESTORE)
                                        ShellExecute(0, None, sys.argv[1], None, None, SW_RESTORE)
    
                                    else:
                                        ShowWindowAsync(window_handle, SW_RESTORE)
                                        SetForegroundWindow(window_handle)
    
                            return False  # Indicate window found, so stop iterating
    
                    # Indicate that EnumWindows() needs to continue iterating
                    return True  # Do not remove, else this function as a callback breaks
    
                # This performs the edmc://auth check and forward
                # EnumWindows() will iterate through all open windows, calling
                # enumwindwsproc() on each.  When an invocation returns False it
                # stops iterating.
                # Ref: <https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows>
                EnumWindows(enumwindowsproc, 0)

        return

    def already_running_popup():
        """Create the "already running" popup."""
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk(className=appname.lower())

        frame = tk.Frame(root)
        frame.grid(row=1, column=0, sticky=tk.NSEW)

        label = tk.Label(frame)
        label['text'] = 'An EDMarketConnector.exe process was already running, exiting.'
        label.grid(row=1, column=0, sticky=tk.NSEW)

        button = ttk.Button(frame, text='OK', command=lambda: sys.exit(0))
        button.grid(row=2, column=0, sticky=tk.S)

        root.mainloop()

    journal_lock = JournalLock()
    locked = journal_lock.obtain_lock()

    handle_edmc_callback_or_foregrounding()

    if locked == JournalLockResult.ALREADY_LOCKED:
        # There's a copy already running.

        logger.info("An EDMarketConnector.exe process was already running, exiting.")

        # To be sure the user knows, we need a popup
        already_running_popup()
        # If the user closes the popup with the 'X', not the 'OK' button we'll
        # reach here.
        sys.exit(0)

    if getattr(sys, 'frozen', False):
        # Now that we're sure we're the only instance running we can truncate the logfile
        logger.trace('Truncating plain logfile')
        sys.stdout.seek(0)
        sys.stdout.truncate()


# See EDMCLogging.py docs.
# isort: off
if TYPE_CHECKING:
    from logging import trace, TRACE  # type: ignore # noqa: F401
    import update
    # from infi.systray import SysTrayIcon
# isort: on

    def _(x: str) -> str:
        """Fake the l10n translation functions for typing."""
        return x

import tkinter as tk
import tkinter.filedialog
import tkinter.font
import tkinter.messagebox
from tkinter import ttk

import commodity
import plug
import prefs
import td
from commodity import COMMODITY_CSV
from dashboard import dashboard
from edmc_data import ship_name_map
from hotkey import hotkeymgr
from l10n import Translations
from monitor import monitor
from theme import theme
from ttkHyperlinkLabel import HyperlinkLabel, openurl

SERVER_RETRY = 5  # retry pause for Companion servers [s]

SHIPYARD_HTML_TEMPLATE = """
<!DOCTYPE HTML>
<html>
    <head>
        <meta http-equiv="refresh" content="0; url={link}">
        <title>Redirecting you to your {ship_name} at {provider_name}...</title>
    </head>
    <body>
        <a href="{link}">
            You should be redirected to your {ship_name} at {provider_name} shortly...
        </a>
    </body>
</html>
"""


class Application(object):
    """Define the main application window."""

    # Tkinter Event types
    EVENT_KEYPRESS = 2
    EVENT_BUTTON = 4
    EVENT_VIRTUAL = 35

    PADX = 5

    def __init__(self, master: tk.Tk):  # noqa: C901, CCR001 # TODO - can possibly factor something out

        self.w = master
        self.w.title(appname)
        self.w.rowconfigure(0, weight=1)
        self.w.columnconfigure(0, weight=1)

        self.prefsdialog = None

        # if platform == 'win32':
        #     from infi.systray import SysTrayIcon

        #     def open_window(systray: 'SysTrayIcon') -> None:
        #         self.w.deiconify()

        #     menu_options = (("Open", None, open_window),)
        #     # Method associated with on_quit is called whenever the systray is closing
        #     self.systray = SysTrayIcon("EDMarketConnector.ico", applongname, menu_options, on_quit=self.exit_tray)
        #     self.systray.start()

        plug.load_plugins(master)

        if platform == 'win32':
            self.w.wm_iconbitmap(default='EDDEDMC.ico')

        # TODO: Export to files and merge from them in future ?
        self.theme_icon = tk.PhotoImage(
            data='R0lGODlhFAAQAMZQAAoKCQoKCgsKCQwKCQsLCgwLCg4LCQ4LCg0MCg8MCRAMCRANChINCREOChIOChQPChgQChgRCxwTCyYVCSoXCS0YCTkdCTseCT0fCTsjDU0jB0EnDU8lB1ElB1MnCFIoCFMoCEkrDlkqCFwrCGEuCWIuCGQvCFs0D1w1D2wyCG0yCF82D182EHE0CHM0CHQ1CGQ5EHU2CHc3CHs4CH45CIA6CIE7CJdECIdLEolMEohQE5BQE41SFJBTE5lUE5pVE5RXFKNaFKVbFLVjFbZkFrxnFr9oFsNqFsVrF8RsFshtF89xF9NzGNh1GNl2GP+KG////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////yH5BAEKAH8ALAAAAAAUABAAAAeegAGCgiGDhoeIRDiIjIZGKzmNiAQBQxkRTU6am0tPCJSGShuSAUcLoIIbRYMFra4FAUgQAQCGJz6CDQ67vAFJJBi0hjBBD0w9PMnJOkAiJhaIKEI7HRoc19ceNAolwbWDLD8uAQnl5ga1I9CHEjEBAvDxAoMtFIYCBy+kFDKHAgM3ZtgYSLAGgwkp3pEyBOJCC2ELB31QATGioAoVAwEAOw==')  # noqa: E501
        self.theme_minimize = tk.BitmapImage(
            data='#define im_width 16\n#define im_height 16\nstatic unsigned char im_bits[] = {\n   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,\n   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfc, 0x3f,\n   0xfc, 0x3f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };\n')  # noqa: E501
        self.theme_close = tk.BitmapImage(
            data='#define im_width 16\n#define im_height 16\nstatic unsigned char im_bits[] = {\n   0x00, 0x00, 0x00, 0x00, 0x0c, 0x30, 0x1c, 0x38, 0x38, 0x1c, 0x70, 0x0e,\n   0xe0, 0x07, 0xc0, 0x03, 0xc0, 0x03, 0xe0, 0x07, 0x70, 0x0e, 0x38, 0x1c,\n   0x1c, 0x38, 0x0c, 0x30, 0x00, 0x00, 0x00, 0x00 };\n')  # noqa: E501

        frame = tk.Frame(self.w, name=appname.lower())
        frame.grid(sticky=tk.NSEW)
        frame.columnconfigure(1, weight=1)

        self.cmdr_label = tk.Label(frame)
        self.cmdr = tk.Label(frame, compound=tk.RIGHT, anchor=tk.W, name='cmdr')
        self.ship_label = tk.Label(frame)
        self.ship = HyperlinkLabel(frame, compound=tk.RIGHT, url=self.shipyard_url, name='ship')
        self.suit_label = tk.Label(frame)
        self.suit = tk.Label(frame, compound=tk.RIGHT, anchor=tk.W, name='suit')
        self.system_label = tk.Label(frame)
        self.system = HyperlinkLabel(frame, compound=tk.RIGHT, url=self.system_url, popup_copy=True, name='system')
        self.station_label = tk.Label(frame)
        self.station = HyperlinkLabel(frame, compound=tk.RIGHT, url=self.station_url, name='station')
        # system and station text is set/updated by the 'provider' plugins
        # eddb, edsm and inara.  Look for:
        #
        # parent.children['system'] / parent.children['station']

        ui_row = 1

        self.cmdr_label.grid(row=ui_row, column=0, sticky=tk.W)
        self.cmdr.grid(row=ui_row, column=1, sticky=tk.EW)
        ui_row += 1

        self.ship_label.grid(row=ui_row, column=0, sticky=tk.W)
        self.ship.grid(row=ui_row, column=1, sticky=tk.EW)
        ui_row += 1

        self.suit_grid_row = ui_row
        self.suit_shown = False
        ui_row += 1

        self.system_label.grid(row=ui_row, column=0, sticky=tk.W)
        self.system.grid(row=ui_row, column=1, sticky=tk.EW)
        ui_row += 1

        self.station_label.grid(row=ui_row, column=0, sticky=tk.W)
        self.station.grid(row=ui_row, column=1, sticky=tk.EW)
        ui_row += 1

        for plugin in plug.PLUGINS:
            appitem = plugin.get_app(frame)
            if appitem:
                tk.Frame(frame, highlightthickness=1).grid(columnspan=2, sticky=tk.EW)  # separator
                if isinstance(appitem, tuple) and len(appitem) == 2:
                    ui_row = frame.grid_size()[1]
                    appitem[0].grid(row=ui_row, column=0, sticky=tk.W)
                    appitem[1].grid(row=ui_row, column=1, sticky=tk.EW)

                else:
                    appitem.grid(columnspan=2, sticky=tk.EW)

        # Update button in main window
        # self.button = ttk.Button(frame, text=_('Update'), width=28, default=tk.ACTIVE, state=tk.DISABLED)
        # self.theme_button = tk.Label(frame, width=32 if platform == 'darwin' else 28, state=tk.DISABLED)
        self.status = tk.Label(frame, name='status', anchor=tk.W)

        # ui_row = frame.grid_size()[1]
        # self.button.grid(row=ui_row, columnspan=2, sticky=tk.NSEW)
        # self.theme_button.grid(row=ui_row, columnspan=2, sticky=tk.NSEW)
        # theme.register_alternate((self.button, self.theme_button, self.theme_button),
        #                          {'row': ui_row, 'columnspan': 2, 'sticky': tk.NSEW})
        self.status.grid(columnspan=2, sticky=tk.EW)
        # self.button.bind('<Button-1>', self.getandsend)
        # theme.button_bind(self.theme_button, self.getandsend)

        for child in frame.winfo_children():
            child.grid_configure(padx=self.PADX, pady=(platform != 'win32' or isinstance(child, tk.Frame)) and 2 or 0)

        self.newversion_button = tk.Button(frame, text='NewVersion', width=28, default=tk.ACTIVE)	# Update button in main window
        row = frame.grid_size()[1]
        self.newversion_button.grid(row=row, columnspan=2, sticky=tk.NSEW)
        self.newversion_button.grid_remove()

        self.menubar = tk.Menu()
        if platform == 'darwin':
            # Can't handle (de)iconify if topmost is set, so suppress iconify button
            # http://wiki.tcl.tk/13428 and p15 of
            # https://developer.apple.com/legacy/library/documentation/Carbon/Conceptual/HandlingWindowsControls/windowscontrols.pdf
            root.call('tk::unsupported::MacWindowStyle', 'style', root, 'document', 'closeBox resizable')

            # https://www.tcl.tk/man/tcl/TkCmd/menu.htm
            self.system_menu = tk.Menu(self.menubar, name='apple')
            self.system_menu.add_command(command=lambda: self.w.call('tk::mac::standardAboutPanel'))
            self.system_menu.add_command(command=lambda: self.updater.checkForUpdates())
            self.menubar.add_cascade(menu=self.system_menu)
            self.file_menu = tk.Menu(self.menubar, name='file')
            self.file_menu.add_command(command=self.save_raw)
            self.menubar.add_cascade(menu=self.file_menu)
            self.edit_menu = tk.Menu(self.menubar, name='edit')
            self.edit_menu.add_command(accelerator='Command-c', state=tk.DISABLED, command=self.copy)
            self.menubar.add_cascade(menu=self.edit_menu)
            self.w.bind('<Command-c>', self.copy)
            # self.view_menu = tk.Menu(self.menubar, name='view')
            # self.view_menu.add_command(command=lambda: stats.StatsDialog(self.w, self.status))
            # self.menubar.add_cascade(menu=self.view_menu)
            window_menu = tk.Menu(self.menubar, name='window')
            self.menubar.add_cascade(menu=window_menu)
            self.help_menu = tk.Menu(self.menubar, name='help')
            self.help_menu.add_command(command=self.help_about)
            self.menubar.add_cascade(menu=self.help_menu)
            self.w['menu'] = self.menubar
            # https://www.tcl.tk/man/tcl/TkCmd/tk_mac.htm
            self.w.call('set', 'tk::mac::useCompatibilityMetrics', '0')
            self.w.createcommand('tkAboutDialog', lambda: self.w.call('tk::mac::standardAboutPanel'))
            self.w.createcommand("::tk::mac::Quit", self.onexit)
            self.w.createcommand("::tk::mac::ShowPreferences", lambda: prefs.PreferencesDialog(self.w, self.postprefs))
            self.w.createcommand("::tk::mac::ReopenApplication", self.w.deiconify)  # click on app in dock = restore
            self.w.protocol("WM_DELETE_WINDOW", self.w.withdraw)  # close button shouldn't quit app
            self.w.resizable(tk.FALSE, tk.FALSE)  # Can't be only resizable on one axis
        else:
            self.file_menu = self.view_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)  # type: ignore
            # self.file_menu.add_command(command=lambda: stats.StatsDialog(self.w, self.status))
            # self.file_menu.add_command(command=self.save_raw)
            self.file_menu.add_command(command=lambda: prefs.PreferencesDialog(self.w, self.postprefs))
            self.file_menu.add_separator()
            self.file_menu.add_command(command=self.onexit)
            self.menubar.add_cascade(menu=self.file_menu)
            self.edit_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)  # type: ignore
            self.edit_menu.add_command(accelerator='Ctrl+C', state=tk.DISABLED, command=self.copy)
            self.menubar.add_cascade(menu=self.edit_menu)
            self.help_menu = tk.Menu(self.menubar, tearoff=tk.FALSE)  # type: ignore
            self.help_menu.add_command(command=self.help_about)

            self.menubar.add_cascade(menu=self.help_menu)
            if platform == 'win32':
                # Must be added after at least one "real" menu entry
                self.always_ontop = tk.BooleanVar(value=bool(config.get_int('always_ontop')))
                self.system_menu = tk.Menu(self.menubar, name='system', tearoff=tk.FALSE)
                self.system_menu.add_separator()
                self.system_menu.add_checkbutton(label=_('Always on top'),
                                                 variable=self.always_ontop,
                                                 command=self.ontop_changed)  # Appearance setting
                self.menubar.add_cascade(menu=self.system_menu)
            self.w.bind('<Control-c>', self.copy)
            self.w.protocol("WM_DELETE_WINDOW", self.onexit)
            theme.register(self.menubar)  # menus and children aren't automatically registered
            theme.register(self.file_menu)
            theme.register(self.edit_menu)
            theme.register(self.help_menu)

            # Alternate title bar and menu for dark theme
            self.theme_menubar = tk.Frame(frame)
            self.theme_menubar.columnconfigure(2, weight=1)
            theme_titlebar = tk.Label(self.theme_menubar, text=applongname,
                                      image=self.theme_icon, cursor='fleur',
                                      anchor=tk.W, compound=tk.LEFT)
            theme_titlebar.grid(columnspan=3, padx=2, sticky=tk.NSEW)
            self.drag_offset: Tuple[Optional[int], Optional[int]] = (None, None)
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
            self.theme_file_menu.grid(row=1, column=0, padx=self.PADX, sticky=tk.W)
            theme.button_bind(self.theme_file_menu,
                              lambda e: self.file_menu.tk_popup(e.widget.winfo_rootx(),
                                                                e.widget.winfo_rooty()
                                                                + e.widget.winfo_height()))
            self.theme_edit_menu = tk.Label(self.theme_menubar, anchor=tk.W)
            self.theme_edit_menu.grid(row=1, column=1, sticky=tk.W)
            theme.button_bind(self.theme_edit_menu,
                              lambda e: self.edit_menu.tk_popup(e.widget.winfo_rootx(),
                                                                e.widget.winfo_rooty()
                                                                + e.widget.winfo_height()))
            self.theme_help_menu = tk.Label(self.theme_menubar, anchor=tk.W)
            self.theme_help_menu.grid(row=1, column=2, sticky=tk.W)
            theme.button_bind(self.theme_help_menu,
                              lambda e: self.help_menu.tk_popup(e.widget.winfo_rootx(),
                                                                e.widget.winfo_rooty()
                                                                + e.widget.winfo_height()))
            tk.Frame(self.theme_menubar, highlightthickness=1).grid(columnspan=5, padx=self.PADX, sticky=tk.EW)
            theme.register(self.theme_minimize)  # images aren't automatically registered
            theme.register(self.theme_close)
            self.blank_menubar = tk.Frame(frame)
            tk.Label(self.blank_menubar).grid()
            tk.Label(self.blank_menubar).grid()
            tk.Frame(self.blank_menubar, height=2).grid()
            theme.register_alternate((self.menubar, self.theme_menubar, self.blank_menubar),
                                     {'row': 0, 'columnspan': 2, 'sticky': tk.NSEW})
            self.w.resizable(tk.TRUE, tk.FALSE)

        # update geometry
        if config.get_str('geometry'):
            match = re.match(r'\+([\-\d]+)\+([\-\d]+)', config.get_str('geometry'))
            if match:
                if platform == 'darwin':
                    # http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
                    if int(match.group(2)) >= 0:
                        self.w.geometry(config.get_str('geometry'))
                elif platform == 'win32':
                    # Check that the titlebar will be at least partly on screen
                    import ctypes
                    from ctypes.wintypes import POINT

                    # https://msdn.microsoft.com/en-us/library/dd145064
                    MONITOR_DEFAULTTONULL = 0  # noqa: N806
                    if ctypes.windll.user32.MonitorFromPoint(POINT(int(match.group(1)) + 16, int(match.group(2)) + 16),
                                                             MONITOR_DEFAULTTONULL):
                        self.w.geometry(config.get_str('geometry'))
                else:
                    self.w.geometry(config.get_str('geometry'))

        self.w.attributes('-topmost', config.get_int('always_ontop') and 1 or 0)

        theme.register(frame)
        theme.apply(self.w)

        self.newversion_button.bind('<Button-1>', self.updateurl)

        self.w.bind('<Map>', self.onmap)  # Special handling for overrideredict
        self.w.bind('<Enter>', self.onenter)  # Special handling for transparency
        self.w.bind('<FocusIn>', self.onenter)  # Special handling for transparency
        self.w.bind('<Leave>', self.onleave)  # Special handling for transparency
        self.w.bind('<FocusOut>', self.onleave)  # Special handling for transparency
        self.w.bind_all('<<JournalEvent>>', self.journal_event)  # Journal monitoring
        self.w.bind_all('<<DashboardEvent>>', self.dashboard_event)  # Dashboard monitoring
        self.w.bind_all('<<PluginError>>', self.plugin_error)  # Statusbar
        self.w.bind_all('<<Quit>>', self.onexit)  # Updater
        self.w.protocol("WM_DELETE_WINDOW", self.onexit)
        self.w.bind('<Control-c>', self.copy)

        self.postprefs()
        self.toggle_suit_row(visible=False)

    def update_suit_text(self) -> None:
        """Update the suit text for current type and loadout."""
        if not monitor.state['Odyssey']:
            # Odyssey not detected, no text should be set so it will hide
            self.suit['text'] = ''
            return

        if (suit := monitor.state.get('SuitCurrent')) is None:
            self.suit['text'] = f'<{_("Unknown")}>'
            return

        suitname = suit['locName']

        if (suitloadout := monitor.state.get('SuitLoadoutCurrent')) is None:
            self.suit['text'] = ''
            return

        loadout_name = suitloadout['name']
        self.suit['text'] = f'{suitname} ({loadout_name})'

    def suit_show_if_set(self) -> None:
        """Show UI Suit row if we have data, else hide."""
        if self.suit['text'] != '':
            self.toggle_suit_row(visible=True)

        else:
            self.toggle_suit_row(visible=False)

    def toggle_suit_row(self, visible: Optional[bool] = None) -> None:
        """
        Toggle the visibility of the 'Suit' row.

        :param visible: Force visibility to this.
        """
        if visible is True:
            self.suit_shown = False

        elif visible is False:
            self.suit_shown = True

        if not self.suit_shown:
            if platform != 'win32':
                pady = 2

            else:

                pady = 0

            self.suit_label.grid(row=self.suit_grid_row, column=0, sticky=tk.W, padx=self.PADX, pady=pady)
            self.suit.grid(row=self.suit_grid_row, column=1, sticky=tk.EW, padx=self.PADX, pady=pady)
            self.suit_shown = True

        else:
            # Hide the Suit row
            self.suit_label.grid_forget()
            self.suit.grid_forget()
            self.suit_shown = False

    def postprefs(self):
        """Perform necessary actions after the Preferences dialog is applied."""
        self.prefsdialog = None
        self.set_labels()  # in case language has changed

        # Reset links in case plugins changed them
        self.ship.configure(url=self.shipyard_url)
        self.system.configure(url=self.system_url)
        self.station.configure(url=self.station_url)

        # (Re-)install hotkey monitoring
        hotkeymgr.register(self.w, config.get_int('hotkey_code'), config.get_int('hotkey_mods'))

        # Update Journal lock if needs be.
        journal_lock.update_lock(self.w)

        # (Re-)install log monitoring
        if not monitor.start(self.w):
            self.status['text'] = f'Error: Check {_("E:D journal file location")}'
        self.status['text'] = 'Started'

    def set_labels(self):
        """Set main window labels, e.g. after language change."""
        self.cmdr_label['text'] = _('Cmdr') + ':'  # Main window
        # Multicrew role label in main window
        self.ship_label['text'] = (monitor.state['Captain'] and _('Role') or _('Ship')) + ':'  # Main window
        self.suit_label['text'] = _('Suit') + ':'  # Main window
        self.system_label['text'] = _('System') + ':'  # Main window
        self.station_label['text'] = _('Station') + ':'  # Main window

        # self.button['text'] = _('Update')	# Update button in main window
        # not yet self.button['state'] = tk.NORMAL

        self.menubar.entryconfigure(1, label=_('File'))  # Menu title
        self.menubar.entryconfigure(2, label=_('Edit'))  # Menu title
        self.menubar.entryconfigure(3, label=_('Help'))  # Menu title
        self.theme_file_menu['text'] = _('File')  # Menu title
        self.theme_edit_menu['text'] = _('Edit')  # Menu title
        self.theme_help_menu['text'] = _('Help')  # Menu title

        self.file_menu.entryconfigure(0, label=_('Settings'))	# Item in the File menu on Windows
        self.file_menu.entryconfigure(2, label=_('Exit'))	# Item in the File menu on Windows

        self.help_menu.entryconfigure(0, label=_('About'))	# Help menu item

    # def getandsend(self, event=None):
    #     # will be used if I bother to turn back on export
    #     print("*** get and send - not implememented yet, turn on button above**")
    # 
    #     if config.getint('output') & (config.OUT_MKT_CSV|config.OUT_MKT_TD):
    #         if not lastmarket is None:
    #             print("Lastmarket set")
    #             if config.getint('output') & config.OUT_MKT_CSV:    # would need to fix the exporters
    #                 commodity.export(lastmarket, COMMODITY_CSV)
    #             if config.getint('output') & config.OUT_MKT_TD:
    #                 td.export(lastmarket)

    def journal_event(self, event):  # noqa: C901, CCR001 # Currently not easily broken up.
        """
        Handle a Journal event passed through event queue from monitor.py.

        :param event: string JSON data of the event
        :return:
        """

        # if monitor.thread is None:
        #     logger.debug('monitor.thread is None, assuming shutdown and returning')
        #     return

        while True:
            entry = monitor.get_entry()
            if not entry:
                # This is expected due to some monitor.py code that appends `None`
                # logger.trace('No entry from monitor.get_entry()')
                return

            if entry['event'] == 'ExitProgram':
                self.onexit()
                return

            # Update main window
            self.updatedetails(entry)

            self.w.update_idletasks()
    
            if not entry['event'] or not monitor.mode:
                # logger.trace('Startup or in CQC, returning')
                return  # Startup or in CQC
    
            if entry['event'] in ['StartUp', 'LoadGame'] and monitor.started:
                logger.info('Startup or LoadGame event')
    
                # Can't start dashboard monitoring
                if not dashboard.start(self.w, monitor.started):
                    logger.info("Can't start Status monitoring")

            # Export loadout
            if entry['event'] == 'Loadout' and not monitor.state['Captain'] and config.getint(
                    'output') & config.OUT_SHIP:
                monitor.export_ship()

            if entry['event'] == 'Market' and not monitor.state['Captain']:
                lastmarket = entry

            if entry['event'] == 'Harness-NewVersion':
                self.newversion_button['text'] = '!! New version Available:' + entry['Version']
                self.newversion_button.grid()
                # self.status['text'] = 'New version'

            # Plugins
            err = plug.notify_journal_entry(monitor.cmdr,
                                            monitor.is_beta,
                                            monitor.system,
                                            monitor.station,
                                            entry,
                                            monitor.state)
            if err:
                self.status['text'] = err
                if not config.get_int('hotkey_mute'):
                    hotkeymgr.play_bad()

    def updatedetails(self, entry):

        def crewroletext(role: str) -> str:
            """
            Return translated crew role.

            Needs to be dynamic to allow for changing language.
            """
            return {
                None:         '',
                'Idle':       '',
                'FighterCon': _('Fighter'),  # Multicrew role
                'FireCon':    _('Gunner'),  # Multicrew role
                'FlightCon':  _('Helm'),  # Multicrew role
            }.get(role, role)

        if monitor.cmdr and monitor.state['Captain']:
            self.cmdr['text'] = f'{monitor.cmdr} / {monitor.state["Captain"]}'
            self.ship_label['text'] = _('Role') + ':'  # Multicrew role label in main window
            self.ship.configure(state=tk.NORMAL, text=crewroletext(monitor.state['Role']), url=None)

        elif monitor.cmdr:
            if monitor.group:
                self.cmdr['text'] = f'{monitor.cmdr} / {monitor.group}'

            else:
                self.cmdr['text'] = monitor.cmdr

            self.ship_label['text'] = _('Ship') + ':'  # Main window

            # TODO: Show something else when on_foot
            if monitor.state['ShipName']:
                ship_text = monitor.state['ShipName']

            else:
                ship_text = ship_name_map.get(monitor.state['ShipType'], monitor.state['ShipType'])

            if not ship_text:
                ship_text = ''

            # Ensure the ship type/name text is clickable, if it should be.
            if monitor.state['Modules']:
                ship_state = True

            else:
                ship_state = tk.DISABLED

            self.ship.configure(text=ship_text, url=self.shipyard_url, state=ship_state)

        else:
            self.cmdr['text'] = ''
            self.ship_label['text'] = _('Ship') + ':'  # Main window
            self.ship['text'] = ''

        if monitor.cmdr and monitor.is_beta:
            self.cmdr['text'] += ' (beta)'

        self.update_suit_text()
        self.suit_show_if_set()

        self.edit_menu.entryconfigure(0, state=monitor.system and tk.NORMAL or tk.DISABLED)  # Copy

        if entry['event'] in (
                'Undocked',
                'StartJump',
                'SetUserShipName',
                'ShipyardBuy',
                'ShipyardSell',
                'ShipyardSwap',
                'ModuleBuy',
                'ModuleSell',
                'MaterialCollected',
                'MaterialDiscarded',
                'ScientificResearch',
                'EngineerCraft',
                'Synthesis',
                'JoinACrew'):
            self.status['text'] = ''  # Periodically clear any old error

    def dashboard_event(self, event) -> None:
        """
        Handle DashBoardEvent tk event.

        Event is sent by code in dashboard.py.
        """
        if not dashboard.status:
            return

        entry = dashboard.status
        # Currently we don't do anything with these events
        err = plug.notify_dashboard_entry(monitor.cmdr, monitor.is_beta, entry)
        if err:
            self.status['text'] = err
            if not config.get_int('hotkey_mute'):
                hotkeymgr.play_bad()

    def plugin_error(self, event=None) -> None:
        """Display asynchronous error from plugin."""
        if plug.last_error.get('msg'):
            self.status['text'] = plug.last_error['msg']
            self.w.update_idletasks()
            if not config.get_int('hotkey_mute'):
                hotkeymgr.play_bad()

    def shipyard_url(self, shipname: str) -> str:
        """Despatch a ship URL to the configured handler."""
        if not (loadout := monitor.ship()):
            logger.warning('No ship loadout, aborting.')
            return ''

        if not bool(config.get_int("use_alt_shipyard_open")):
            return plug.invoke(config.get_str('shipyard_provider'),
                               'EDSY',
                               'shipyard_url',
                               loadout,
                               monitor.is_beta)

        # Avoid file length limits if possible
        provider = config.get_str('shipyard_provider', default='EDSY')
        target = plug.invoke(provider, 'EDSY', 'shipyard_url', loadout, monitor.is_beta)
        file_name = join(config.app_dir_path, "last_shipyard.html")

        with open(file_name, 'w') as f:
            print(SHIPYARD_HTML_TEMPLATE.format(
                link=html.escape(str(target)),
                provider_name=html.escape(str(provider)),
                ship_name=html.escape(str(shipname))
            ), file=f)

        return f'file://localhost/{file_name}'

    def system_url(self, system: str) -> str:
        """Despatch a system URL to the configured handler."""
        return plug.invoke(config.get_str('system_provider'), 'EDSM', 'system_url', monitor.system)

    def station_url(self, station: str) -> str:
        """Despatch a station URL to the configured handler."""
        return plug.invoke(config.get_str('station_provider'), 'eddb', 'station_url', monitor.system, monitor.station)

    def ontop_changed(self, event=None) -> None:
        """Set main window 'on top' state as appropriate."""
        config.set('always_ontop', self.always_ontop.get())
        self.w.wm_attributes('-topmost', self.always_ontop.get())

    def copy(self, event=None) -> None:
        """Copy system, and possible station, name to clipboard."""
        if monitor.system:
            self.w.clipboard_clear()
            self.w.clipboard_append(monitor.station and f'{monitor.system},{monitor.station}' or monitor.system)

    def help_about(self):
        tk.messagebox.showinfo(
            f'EDD-EDMC: {appversion()}',
                "This program supports EDMC plugins for EDD/EDDLite\r\n\r\n"
                "Install this program, then run it, then close the program\r\n"
                "This installs the adaptors into EDD/EDDLite\r\n\r\n"
                "Then run EDD/EDDLite and they will automatically start and stop this program\r\n\r\n"
                "Place plugins in %appdatalocal%\edd-edmc\plugins\r\n"

            )

    def onexit(self, event=None) -> None:
        """Application shutdown procedure."""
        # if platform == 'win32':
        #     shutdown_thread = threading.Thread(target=self.systray.shutdown)
        #     shutdown_thread.setDaemon(True)
        #     shutdown_thread.start()

        config.set_shutdown()  # Signal we're in shutdown now.

        # http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
        if platform != 'darwin' or self.w.winfo_rooty() > 0:
            x, y = self.w.geometry().split('+')[1:3]  # e.g. '212x170+2881+1267'
            config.set('geometry', f'+{x}+{y}')

        # Let the user know we're shutting down.
        self.status['text'] = _('Shutting down...')
        self.w.update_idletasks()
        logger.info('Starting shutdown procedures...')

        # Earlier than anything else so plugin code can't interfere *and* it
        # won't still be running in a manner that might rely on something
        # we'd otherwise have already stopped.
        logger.info('Notifying plugins to stop...')
        plug.notify_stop()

        # Handling of application hotkeys now so the user can't possible cause
        # an issue via triggering one.
        logger.info('Unregistering hotkey manager...')
        hotkeymgr.unregister()

        # Now the main programmatic input methods
        logger.info('Closing dashboard...')
        dashboard.close()

        logger.info('Closing journal monitor...')
        monitor.close()

        # Now anything else.
        logger.info('Closing config...')
        config.close()

        logger.info('Destroying app window...')
        self.w.destroy()

        logger.info('Done.')

    def drag_start(self, event) -> None:
        """Initiate dragging the window."""
        self.drag_offset = (event.x_root - self.w.winfo_rootx(), event.y_root - self.w.winfo_rooty())

    def drag_continue(self, event) -> None:
        """Continued handling of window drag."""
        if self.drag_offset[0]:
            offset_x = event.x_root - self.drag_offset[0]
            offset_y = event.y_root - self.drag_offset[1]
            self.w.geometry(f'+{offset_x:d}+{offset_y:d}')

    def drag_end(self, event) -> None:
        """Handle end of window dragging."""
        self.drag_offset = (None, None)

    def oniconify(self, event=None) -> None:
        """Handle minimization of the application."""
        self.w.overrideredirect(0)  # Can't iconize while overrideredirect
        self.w.iconify()
        self.w.update_idletasks()  # Size and windows styles get recalculated here
        self.w.wait_visibility()  # Need main window to be re-created before returning
        theme.active = None  # So theme will be re-applied on map

    # TODO: Confirm this is unused and remove.
    def onmap(self, event=None) -> None:
        """Perform a now unused function."""
        if event.widget == self.w:
            theme.apply(self.w)

    def onenter(self, event=None) -> None:
        """Handle when our window gains focus."""
        # TODO: This assumes that 1) transparent is at least 2, 2) there are
        #       no new themes added after that.
        if config.get_int('theme') > 1:
            self.w.attributes("-transparentcolor", '')
            self.blank_menubar.grid_remove()
            self.theme_menubar.grid(row=0, columnspan=2, sticky=tk.NSEW)

    def onleave(self, event=None) -> None:
        """Handle when our window loses focus."""
        # TODO: This assumes that 1) transparent is at least 2, 2) there are
        #       no new themes added after that.
        if config.get_int('theme') > 1 and event.widget == self.w:
            self.w.attributes("-transparentcolor", 'grey4')
            self.theme_menubar.grid_remove()
            self.blank_menubar.grid(row=0, columnspan=2, sticky=tk.NSEW)

    def updateurl(self, event=None):
        openurl('https://github.com/EDDiscovery/EDD-EDMC/releases')


def test_logging() -> None:
    """Simple test of top level logging."""
    logger.debug('Test from EDMarketConnector.py top-level test_logging()')


def log_locale(prefix: str) -> None:
    """Log all of the current local settings."""
    logger.debug(f'''Locale: {prefix}
Locale LC_COLLATE: {locale.getlocale(locale.LC_COLLATE)}
Locale LC_CTYPE: {locale.getlocale(locale.LC_CTYPE)}
Locale LC_MONETARY: {locale.getlocale(locale.LC_MONETARY)}
Locale LC_NUMERIC: {locale.getlocale(locale.LC_NUMERIC)}
Locale LC_TIME: {locale.getlocale(locale.LC_TIME)}'''
                 )


# Run the app
if __name__ == "__main__":  # noqa: C901
    logger.info(f'Startup v{appversion()} : Running on Python v{sys.version}')
    logger.debug(f'''Platform: {sys.platform} {sys.platform == "win32" and sys.getwindowsversion()}
argv[0]: {sys.argv[0]}
exec_prefix: {sys.exec_prefix}
executable: {sys.executable}
sys.path: {sys.path}'''
                 )

    # We prefer a UTF-8 encoding gets set, but older Windows versions have
    # issues with this.  From Windows 10 1903 onwards we can rely on the
    # manifest ActiveCodePage to set this, but that is silently ignored on
    # all previous Windows versions.
    # Trying to set a UTF-8 encoding on those older versions will fail with
    #   locale.Error: unsupported locale setting
    # but we do need to make the attempt for when we're running from source.
    #
    # Note that this locale magic is partially done in l10n.py as well. So
    # removing or modifying this may or may not have the desired effect.
    log_locale('Initial Locale')

    try:
        locale.setlocale(locale.LC_ALL, '')

    except locale.Error as e:
        logger.error("Could not set LC_ALL to ''", exc_info=e)

    else:
        log_locale('After LC_ALL defaults set')

        locale_startup = locale.getlocale(locale.LC_CTYPE)
        logger.debug(f'Locale LC_CTYPE: {locale_startup}')

        # Older Windows Versions and builds have issues with UTF-8, so only
        # even attempt this where we think it will be safe.

        if sys.platform == 'win32':
            windows_ver = sys.getwindowsversion()

        # <https://en.wikipedia.org/wiki/Windows_10_version_history#Version_1903_(May_2019_Update)>
        # Windows 19, 1903 was build 18362
        if (
                sys.platform != 'win32'
                or (
                    windows_ver.major == 10
                    and windows_ver.build >= 18362
                )
                or windows_ver.major > 10  # Paranoid future check
        ):
            # Set that same language, but utf8 encoding (it was probably cp1252
            # or equivalent for other languages).
            # UTF-8, not utf8: <https://en.wikipedia.org/wiki/UTF-8#Naming>
            try:
                # locale_startup[0] is the 'language' portion
                locale.setlocale(locale.LC_ALL, (locale_startup[0], 'UTF-8'))

            except locale.Error:
                logger.exception(f"Could not set LC_ALL to ('{locale_startup[0]}', 'UTF_8')")

            except Exception:
                logger.exception(
                    f"Exception other than locale.Error on setting LC_ALL=('{locale_startup[0]}', 'UTF_8')"
                )

            else:
                log_locale('After switching to UTF-8 encoding (same language)')

    # TODO: unittests in place of these
    # logger.debug('Test from __main__')
    # test_logging()

    class A(object):
        """Simple top-level class."""

        class B(object):
            """Simple second-level class."""

            def __init__(self):
                logger.debug('A call from A.B.__init__')
                self.__test()
                _ = self.test_prop

            def __test(self):
                logger.debug("A call from A.B.__test")

            @property
            def test_prop(self):
                """Test property."""
                logger.debug("test log from property")
                return "Test property is testy"

    # abinit = A.B()

    # Plain, not via `logger`
    print(f'{applongname} {appversion()}')

    Translations.install(config.get_str('language'))  # Can generate errors so wait til log set up

    root = tk.Tk(className=appname.lower())
    if sys.platform != 'win32' and ((f := config.get_str('font')) is not None or f != ''):
        size = config.get_int('font_size', default=-1)
        if size == -1:
            size = 10

        logger.info(f'Overriding tkinter default font to {f!r} at size {size}')
        tk.font.nametofont('TkDefaultFont').configure(family=f, size=size)

    # UI Scaling
    """
    We scale the UI relative to what we find tk-scaling is on startup.
    """
    ui_scale = config.get_int('ui_scale')
    # NB: This *also* catches a literal 0 value to re-set to the default 100
    if not ui_scale:
        ui_scale = 100
        config.set('ui_scale', ui_scale)
    theme.default_ui_scale = root.tk.call('tk', 'scaling')
    logger.trace(f'Default tk scaling = {theme.default_ui_scale}')
    theme.startup_ui_scale = ui_scale
    root.tk.call('tk', 'scaling', theme.default_ui_scale * float(ui_scale) / 100.0)
    app = Application(root)

    def messagebox_not_py3():
        """Display message about plugins not updated for Python 3.x."""
        plugins_not_py3_last = config.get_int('plugins_not_py3_last', default=0)
        if (plugins_not_py3_last + 86400) < int(time()) and len(plug.PLUGINS_not_py3):
            # Yes, this is horribly hacky so as to be sure we match the key
            # that we told Translators to use.
            popup_text = "One or more of your enabled plugins do not yet have support for Python 3.x. Please see the " \
                         "list on the '{PLUGINS}' tab of '{FILE}' > '{SETTINGS}'. You should check if there is an " \
                         "updated version available, else alert the developer that they need to update the code for " \
                         "Python 3.x.\r\n\r\nYou can disable a plugin by renaming its folder to have '{DISABLED}' on " \
                         "the end of the name."
            popup_text = popup_text.replace('\n', '\\n')
            popup_text = popup_text.replace('\r', '\\r')
            # Now the string should match, so try translation
            popup_text = _(popup_text)
            # And substitute in the other words.
            popup_text = popup_text.format(PLUGINS=_('Plugins'), FILE=_('File'), SETTINGS=_('Settings'),
                                           DISABLED='.disabled')
            # And now we do need these to be actual \r\n
            popup_text = popup_text.replace('\\n', '\n')
            popup_text = popup_text.replace('\\r', '\r')

            tk.messagebox.showinfo(
                _('EDMC: Plugins Without Python 3.x Support'),
                popup_text
            )
            config.set('plugins_not_py3_last', int(time()))

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

    # UI Transparency
    ui_transparency = config.get_int('ui_transparency')
    if ui_transparency == 0:
        ui_transparency = 100

    root.wm_attributes('-alpha', ui_transparency / 100)

    root.after(0, messagebox_not_py3)
    root.mainloop()

    logger.info('Exiting')
