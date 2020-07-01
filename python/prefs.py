# -*- coding: utf-8 -*-
import os
from os.path import dirname, expanduser, expandvars, exists, isdir, join, normpath
from sys import platform
import webbrowser

import tkinter as tk
from tkinter import ttk
from tkinter import colorchooser as tkColorChooser
from ttkHyperlinkLabel import HyperlinkLabel
import myNotebook as nb

from config import applongname, config
from l10n import Translations
from monitor import monitor
from theme import theme

import plug

if platform == 'darwin':
    import objc
    from Foundation import NSFileManager
    try:
        from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    except:
        HIServices = objc.loadBundle('HIServices', globals(), '/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework')
        objc.loadBundleFunctions(HIServices, globals(), [('AXIsProcessTrusted', 'B'),
                                                         ('AXIsProcessTrustedWithOptions', 'B@')])
        objc.loadBundleVariables(HIServices, globals(), [('kAXTrustedCheckOptionPrompt', '@^{__CFString=}')])
    was_accessible_at_launch = AXIsProcessTrusted()

elif platform=='win32':
    # sigh tkFileDialog.askdirectory doesn't support unicode on Windows
    import ctypes
    from ctypes.wintypes import *

    SHGetLocalizedName = ctypes.windll.shell32.SHGetLocalizedName
    SHGetLocalizedName.argtypes = [LPCWSTR, LPWSTR, UINT, ctypes.POINTER(ctypes.c_int)]

    LoadString = ctypes.windll.user32.LoadStringW
    LoadString.argtypes = [HINSTANCE, UINT, LPWSTR, ctypes.c_int]

    # https://msdn.microsoft.com/en-us/library/windows/desktop/bb762115
    BIF_RETURNONLYFSDIRS   = 0x00000001
    BIF_USENEWUI           = 0x00000050
    BFFM_INITIALIZED       = 1
    BFFM_SETSELECTION      = 0x00000467
    BrowseCallbackProc = ctypes.WINFUNCTYPE(ctypes.c_int, HWND, ctypes.c_uint, LPARAM, LPARAM)

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [("hwndOwner", HWND), ("pidlRoot", LPVOID), ("pszDisplayName", LPWSTR), ("lpszTitle", LPCWSTR), ("ulFlags", UINT), ("lpfn", BrowseCallbackProc), ("lParam", LPCWSTR), ("iImage", ctypes.c_int)]

    try:
        CalculatePopupWindowPosition = ctypes.windll.user32.CalculatePopupWindowPosition
        CalculatePopupWindowPosition.argtypes = [ctypes.POINTER(POINT), ctypes.POINTER(SIZE), UINT, ctypes.POINTER(RECT), ctypes.POINTER(RECT)]
        GetParent = ctypes.windll.user32.GetParent
        GetParent.argtypes = [HWND]
        GetWindowRect = ctypes.windll.user32.GetWindowRect
        GetWindowRect.argtypes = [HWND, ctypes.POINTER(RECT)]
    except:	# Not supported under Wine 4.0
        CalculatePopupWindowPosition = None

class PreferencesDialog(tk.Toplevel):

    def __init__(self, parent, callback):
        tk.Toplevel.__init__(self, parent)

        self.parent = parent
        self.callback = callback
        self.title(platform=='darwin' and _('Preferences') or
                   _('Settings'))

        if parent.winfo_viewable():
            self.transient(parent)

        # position over parent
        if platform!='darwin' or parent.winfo_rooty()>0:	# http://core.tcl.tk/tk/tktview/c84f660833546b1b84e7
            self.geometry("+%d+%d" % (parent.winfo_rootx(), parent.winfo_rooty()))

        # remove decoration
        if platform=='win32':
            self.attributes('-toolwindow', tk.TRUE)
        elif platform=='darwin':
            # http://wiki.tcl.tk/13428
            parent.call('tk::unsupported::MacWindowStyle', 'style', self, 'utility')
        self.resizable(tk.FALSE, tk.FALSE)

        self.cmdr = False	# Note if Cmdr changes in the Journal
        self.is_beta = False	# Note if Beta status changes in the Journal
        self.cmdrchanged_alarm = None

        frame = ttk.Frame(self)
        frame.grid(sticky=tk.NSEW)

        notebook = nb.Notebook(frame)
        notebook.bind('<<NotebookTabChanged>>', self.tabchanged)	# Recompute on tab change

        PADX = 10
        BUTTONX = 12	# indent Checkbuttons and Radiobuttons
        PADY = 2	# close spacing

        outframe = nb.Frame(notebook)
        outframe.columnconfigure(0, weight=1)

        output = config.getint('output') # default settings

        self.out_label = nb.Label(outframe, text=_('Please choose what data to save'))
        self.out_label.grid(columnspan=2, padx=PADX, sticky=tk.W)
#        self.out_csv = tk.IntVar(value = (output & config.OUT_MKT_CSV ) and 1)
#        self.out_csv_button = nb.Checkbutton(outframe, text=_('Market data in CSV format file'), variable=self.out_csv, command=self.outvarchanged)
#        self.out_csv_button.grid(columnspan=2, padx=BUTTONX, sticky=tk.W)
#        self.out_td  = tk.IntVar(value = (output & config.OUT_MKT_TD  ) and 1)
#        self.out_td_button = nb.Checkbutton(outframe, text=_('Market data in Trade Dangerous format file'), variable=self.out_td, command=self.outvarchanged)
#        self.out_td_button.grid(columnspan=2, padx=BUTTONX, sticky=tk.W)
        self.out_ship= tk.IntVar(value = (output & config.OUT_SHIP) and 1)
        self.out_ship_button = nb.Checkbutton(outframe, text=_('Ship loadout'), variable=self.out_ship, command=self.outvarchanged)	# Output setting
        self.out_ship_button.grid(columnspan=2, padx=BUTTONX, pady=(5,0), sticky=tk.W)

        self.outdir = tk.StringVar()
        self.outdir.set(config.get('outdir'))
        self.outdir_label = nb.Label(outframe, text=_('File location')+':')	# Section heading in settings
        self.outdir_label.grid(padx=PADX, pady=(5,0), sticky=tk.W)
        self.outdir_entry = nb.Entry(outframe, takefocus=False)
        self.outdir_entry.grid(columnspan=2, padx=PADX, pady=(0,PADY), sticky=tk.EW)
        self.outbutton = nb.Button(outframe, text=(platform=='darwin' and _('Change...') or	# Folder selection button on OSX
                                                   _('Browse...')),	# Folder selection button on Windows
                                   command = lambda:self.filebrowse(_('File location'), self.outdir))
        self.outbutton.grid(column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        nb.Frame(outframe).grid(pady=5)	# bottom spacer

        notebook.add(outframe, text=_('Output'))		# Tab heading in settings

        # build theme settings

        self.languages = Translations.available_names()
        self.lang = tk.StringVar(value = self.languages.get(config.get('language'), _('Default')))	# Appearance theme and language setting
        self.always_ontop = tk.BooleanVar(value = config.getint('always_ontop'))
        self.theme = tk.IntVar(value = config.getint('theme'))
        self.theme_colors = [config.get('dark_text'), config.get('dark_highlight')]
        self.theme_prompts = [
            _('Normal text'),		# Dark theme color setting
            _('Highlighted text'),	# Dark theme color setting
        ]

        themeframe = nb.Frame(notebook)
        themeframe.columnconfigure(2, weight=1)
        nb.Label(themeframe, text=_('Language')).grid(row=10, padx=PADX, sticky=tk.W)	# Appearance setting prompt
        self.lang_button = nb.OptionMenu(themeframe, self.lang, self.lang.get(), *self.languages.values())
        self.lang_button.grid(row=10, column=1, columnspan=2, padx=PADX, sticky=tk.W)
        ttk.Separator(themeframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY*4, sticky=tk.EW)
        nb.Label(themeframe, text=_('Theme')).grid(columnspan=3, padx=PADX, sticky=tk.W)	# Appearance setting
        nb.Radiobutton(themeframe, text=_('Default'), variable=self.theme, value=0, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme and language setting
        nb.Radiobutton(themeframe, text=_('Dark'), variable=self.theme, value=1, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme setting
        if platform == 'win32':
            nb.Radiobutton(themeframe, text=_('Transparent'), variable=self.theme, value=2, command=self.themevarchanged).grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance theme setting
        self.theme_label_0 = nb.Label(themeframe, text=self.theme_prompts[0])
        self.theme_label_0.grid(row=20, padx=PADX, sticky=tk.W)
        self.theme_button_0 = nb.ColoredButton(themeframe, text=_('Station'), background='grey4', command=lambda:self.themecolorbrowse(0))	# Main window
        self.theme_button_0.grid(row=20, column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        self.theme_label_1 = nb.Label(themeframe, text=self.theme_prompts[1])
        self.theme_label_1.grid(row=21, padx=PADX, sticky=tk.W)
        self.theme_button_1 = nb.ColoredButton(themeframe, text='  Hutton Orbital  ', background='grey4', command=lambda:self.themecolorbrowse(1))	# Do not translate
        self.theme_button_1.grid(row=21, column=1, padx=PADX, pady=PADY, sticky=tk.NSEW)
        ttk.Separator(themeframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY*4, sticky=tk.EW)
        self.ontop_button = nb.Checkbutton(themeframe, text=_('Always on top'), variable=self.always_ontop, command=self.themevarchanged)
        self.ontop_button.grid(columnspan=3, padx=BUTTONX, sticky=tk.W)	# Appearance setting
        nb.Label(themeframe).grid(sticky=tk.W)	# big spacer

        notebook.add(themeframe, text=_('Appearance'))	# Tab heading in settings

        # build plugin prefs tabs
        for plugin in plug.PLUGINS:
            #print(f'plug in pref {plugin.name}')
            plugframe = plugin.get_prefs(notebook, monitor.cmdr, monitor.is_beta)

            if plugframe:
                notebook.add(plugframe, text=plugin.name)

        # Plugin settings and info
        plugsframe = nb.Frame(notebook)
        plugsframe.columnconfigure(0, weight=1)
        plugdir = tk.StringVar()
        plugdir.set(config.plugin_dir)

        nb.Label(plugsframe, text=_('Plugins folder')+':').grid(padx=PADX, sticky=tk.W)	# Section heading in settings
        plugdirentry = nb.Entry(plugsframe, justify=tk.LEFT)
        self.displaypath(plugdir, plugdirentry)
        plugdirentry.grid(row=10, padx=PADX, sticky=tk.EW)

        nb.Button(plugsframe, text=_('Open'),	# Button that opens a folder in Explorer/Finder
                  command=lambda: webbrowser.open('file:///%s' % plugdir.get())).grid(row=10, column=1, padx=(0,PADX), sticky=tk.NSEW)

        nb.Label(plugsframe, text=_("Tip: You can disable a plugin by{CR}adding '{EXT}' to its folder name").format(EXT='.disabled')).grid(	# Help text in settings
            columnspan=2, padx=PADX, pady=10, sticky=tk.NSEW)

        enabled_plugins = [x for x in plug.PLUGINS if x.folder and x.module]
        if len(enabled_plugins):
            ttk.Separator(plugsframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY * 8, sticky=tk.EW)
            nb.Label(plugsframe, text=_('Enabled Plugins')+':').grid(padx=PADX, sticky=tk.W)	# List of plugins in settings
            for plugin in enabled_plugins:
                if plugin.name == plugin.folder:
                    label = nb.Label(plugsframe, text=plugin.name)
                else:
                    label = nb.Label(plugsframe, text='%s (%s)' % (plugin.folder, plugin.name))
                label.grid(columnspan=2, padx=PADX*2, sticky=tk.W)

        disabled_plugins = [x for x in plug.PLUGINS if x.folder and not x.module]
        if len(disabled_plugins):
            ttk.Separator(plugsframe, orient=tk.HORIZONTAL).grid(columnspan=3, padx=PADX, pady=PADY * 8, sticky=tk.EW)
            nb.Label(plugsframe, text=_('Disabled Plugins')+':').grid(padx=PADX, sticky=tk.W)	# List of plugins in settings
            for plugin in disabled_plugins:
                nb.Label(plugsframe, text=plugin.name).grid(columnspan=2, padx=PADX*2, sticky=tk.W)

        notebook.add(plugsframe, text=_('Plugins'))		# Tab heading in settings

        if platform=='darwin':
            self.protocol("WM_DELETE_WINDOW", self.apply)	# close button applies changes
        else:
            buttonframe = ttk.Frame(frame)
            buttonframe.grid(padx=PADX, pady=PADX, sticky=tk.NSEW)
            buttonframe.columnconfigure(0, weight=1)
            ttk.Label(buttonframe).grid(row=0, column=0)	# spacer
            button = ttk.Button(buttonframe, text=_('OK'), command=self.apply)
            button.grid(row=0, column=1, sticky=tk.E)
            button.bind("<Return>", lambda event:self.apply())
            self.protocol("WM_DELETE_WINDOW", self._destroy)

        # Selectively disable buttons depending on output settings
        self.cmdrchanged()

        # wait for window to appear on screen before calling grab_set
        self.parent.update_idletasks()
        self.parent.wm_attributes('-topmost', 0)	# needed for dialog to appear ontop of parent on OSX & Linux
        self.wait_visibility()
        self.grab_set()

        # Ensure fully on-screen
        if platform == 'win32' and CalculatePopupWindowPosition:
            position = RECT()
            GetWindowRect(GetParent(self.winfo_id()), position)
            if CalculatePopupWindowPosition(POINT(parent.winfo_rootx(), parent.winfo_rooty()),
                                            SIZE(position.right - position.left, position.bottom - position.top),
                                            0x10000, None, position):
                self.geometry("+%d+%d" % (position.left, position.top))

    def cmdrchanged(self, event=None):
        if self.cmdr != monitor.cmdr or self.is_beta != monitor.is_beta:
            # Cmdr has changed - update settings
            if self.cmdr is not False:		# Don't notify on first run
                plug.notify_prefs_cmdr_changed(monitor.cmdr, monitor.is_beta)
            self.cmdr = monitor.cmdr
            self.is_beta = monitor.is_beta

        # Poll
        self.cmdrchanged_alarm = self.after(1000, self.cmdrchanged)

    def tabchanged(self, event):
        self.outvarchanged()
        if platform == 'darwin':
            # Hack to recompute size so that buttons show up under Mojave
            notebook = event.widget
            frame = self.nametowidget(notebook.winfo_parent())
            temp = nb.Label(frame)
            temp.grid()
            temp.update_idletasks()
            temp.destroy()

    def outvarchanged(self, event=None):
        self.displaypath(self.outdir, self.outdir_entry)

        self.out_label['state'] = tk.NORMAL or tk.DISABLED
        #self.out_csv_button['state'] = self.out_td_button['state'] = tk.NORMAL or tk.DISABLED
        self.out_ship_button['state'] = tk.NORMAL or tk.DISABLED
        #local = self.out_td.get() or self.out_csv.get() or self.out_ship.get()
        local = self.out_ship.get()
        self.outdir_label['state']      = local and tk.NORMAL  or tk.DISABLED
        self.outbutton['state']         = local and tk.NORMAL  or tk.DISABLED
        self.outdir_entry['state']      = local and 'readonly' or tk.DISABLED

    def filebrowse(self, title, pathvar):
        if platform != 'win32':
            import tkinter.filedialog
            d = tkinter.filedialog.askdirectory(parent=self, initialdir=expanduser(pathvar.get()), title=title, mustexist=tk.TRUE)
        else:
            def browsecallback(hwnd, uMsg, lParam, lpData):
                # set initial folder
                if uMsg==BFFM_INITIALIZED and lpData:
                    ctypes.windll.user32.SendMessageW(hwnd, BFFM_SETSELECTION, 1, lpData);
                return 0

            browseInfo = BROWSEINFO()
            browseInfo.lpszTitle = title
            browseInfo.ulFlags = BIF_RETURNONLYFSDIRS|BIF_USENEWUI
            browseInfo.lpfn = BrowseCallbackProc(browsecallback)
            browseInfo.lParam = pathvar.get().startswith('~') and join(config.home, pathvar.get()[2:]) or pathvar.get()
            ctypes.windll.ole32.CoInitialize(None)
            pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(browseInfo))
            if pidl:
                path = ctypes.create_unicode_buffer(MAX_PATH)
                ctypes.windll.shell32.SHGetPathFromIDListW(pidl, path)
                ctypes.windll.ole32.CoTaskMemFree(pidl)
                d = path.value
            else:
                d = None

        if d:
            pathvar.set(d)
            self.outvarchanged()

    def displaypath(self, pathvar, entryfield):
        entryfield['state'] = tk.NORMAL	# must be writable to update
        entryfield.delete(0, tk.END)
        if platform=='win32':
            start = pathvar.get().lower().startswith(config.home.lower()) and len(config.home.split('\\')) or 0
            display = []
            components = normpath(pathvar.get()).split('\\')
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            pidsRes = ctypes.c_int()
            for i in range(start, len(components)):
                try:
                    if (not SHGetLocalizedName('\\'.join(components[:i+1]), buf, MAX_PATH, ctypes.byref(pidsRes)) and
                        LoadString(ctypes.WinDLL(expandvars(buf.value))._handle, pidsRes.value, buf, MAX_PATH)):
                        display.append(buf.value)
                    else:
                        display.append(components[i])
                except:
                    display.append(components[i])
            entryfield.insert(0, '\\'.join(display))
        elif platform=='darwin' and NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get()):	# None if path doesn't exist
            if pathvar.get().startswith(config.home):
                display = ['~'] + NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get())[len(NSFileManager.defaultManager().componentsToDisplayForPath_(config.home)):]
            else:
                display = NSFileManager.defaultManager().componentsToDisplayForPath_(pathvar.get())
            entryfield.insert(0, '/'.join(display))
        else:
            if pathvar.get().startswith(config.home):
                entryfield.insert(0, '~' + pathvar.get()[len(config.home):])
            else:
                entryfield.insert(0, pathvar.get())
        entryfield['state'] = 'readonly'

    def logdir_reset(self):
        if config.default_journal_dir:
            self.logdir.set(config.default_journal_dir)
        self.outvarchanged()

    def themecolorbrowse(self, index):
        (rgb, color) = tkColorChooser.askcolor(self.theme_colors[index], title=self.theme_prompts[index], parent=self.parent)
        if color:
            self.theme_colors[index] = color
            self.themevarchanged()

    def themevarchanged(self):
        self.theme_button_0['foreground'], self.theme_button_1['foreground'] = self.theme_colors

        state = self.theme.get() and tk.NORMAL or tk.DISABLED
        self.theme_label_0['state'] = state
        self.theme_label_1['state'] = state
        self.theme_button_0['state'] = state
        self.theme_button_1['state'] = state


    def apply(self):
        config.set('output',
#                   (self.out_td.get()   and config.OUT_MKT_TD) +
#                   (self.out_csv.get()  and config.OUT_MKT_CSV) +
                   (0) +
                   (self.out_ship.get() and config.OUT_SHIP) +
                   (config.getint('output') & (config.OUT_MKT_EDDN | config.OUT_SYS_EDDN | config.OUT_SYS_DELAY)))

        #print(f"output {config.getint('output')} {self.out_ship.get()}")

        config.set('outdir', self.outdir.get().startswith('~') and join(config.home, self.outdir.get()[2:]) or self.outdir.get())

        lang_codes = { v: k for k, v in self.languages.items() }	# Codes by name
        config.set('language', lang_codes.get(self.lang.get()) or '')
        Translations.install(config.get('language') or None)

        config.set('always_ontop', self.always_ontop.get())
        config.set('theme', self.theme.get())
        config.set('dark_text', self.theme_colors[0])
        config.set('dark_highlight', self.theme_colors[1])
        theme.apply(self.parent)

        # Notify
        if self.callback:
            self.callback()
        plug.notify_prefs_changed(monitor.cmdr, monitor.is_beta)

        self._destroy()

    def _destroy(self):
        if self.cmdrchanged_alarm is not None:
            self.after_cancel(self.cmdrchanged_alarm)
            self.cmdrchanged_alarm = None
        self.parent.wm_attributes('-topmost', config.getint('always_ontop') and 1 or 0)
        self.destroy()

    if platform == 'darwin':
        def enableshortcuts(self):
            self.apply()
            # popup System Preferences dialog
            try:
                # http://stackoverflow.com/questions/6652598/cocoa-button-opens-a-system-preference-page/6658201
                from ScriptingBridge import SBApplication
                sysprefs = 'com.apple.systempreferences'
                prefs = SBApplication.applicationWithBundleIdentifier_(sysprefs)
                pane = [x for x in prefs.panes() if x.id() == 'com.apple.preference.security'][0]
                prefs.setCurrentPane_(pane)
                anchor = [x for x in pane.anchors() if x.name() == 'Privacy_Accessibility'][0]
                anchor.reveal()
                prefs.activate()
            except:
                AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
            self.parent.event_generate('<<Quit>>', when="tail")
