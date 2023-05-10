"""Inara Sync."""

# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#
# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#
#
# This is an EDMC 'core' plugin.
#
# All EDMC plugins are *dynamically* loaded at run-time.
#
# We build for Windows using `py2exe`.
#
# `py2exe` can't possibly know about anything in the dynamically loaded
# core plugins.
#
# Thus you **MUST** check if any imports you add in this file are only
# referenced in this file (or only in any other core plugin), and if so...
#
#     YOU MUST ENSURE THAT PERTINENT ADJUSTMENTS ARE MADE IN
#     `Build-exe-and-msi.py` SO AS TO ENSURE THE FILES ARE ACTUALLY PRESENT
#     IN AN END-USER INSTALLATION ON WINDOWS.
#
# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#
# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#
import tkinter as tk
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional
from typing import cast

import requests

from config import appname, config
from EDMCLogging import get_main_logger

logger = get_main_logger()

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x


class This:
    """Holds module globals."""

    def __init__(self):

        # Main window clicks
        self.system_link: tk.Widget = None  # type: ignore
        self.system_name: Optional[str] = None  # type: ignore
        self.system_address: Optional[str] = None  # type: ignore
        self.system_population: Optional[int] = None
        self.station_link: tk.Widget = None  # type: ignore
        self.station = None


this = This()

STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7


def system_url(system_name: str) -> str:
    """Get a URL for the current system."""
    if this.system_address:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-starsystem/'
                                          f'?search={this.system_address}')

    elif system_name:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-starsystem/'
                                          f'?search={system_name}')

    return ''


def station_url(system_name: str, station_name: str) -> str:
    """
    Get a URL for the current station.

    If there is no station, the system URL is returned.

    :param system_name: The name of the current system
    :param station_name: The name of the current station, if any
    :return: A URL to inara for the given system and station
    """
    if system_name and station_name:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-station/'
                                          f'?search={system_name}%20[{station_name}]')

    # monitor state might think these are gone, but we don't yet
    if this.system_name and this.station:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-station/'
                                          f'?search={this.system_name}%20[{this.station}]')

    if system_name:
        return system_url(system_name)

    return ''


def plugin_start3(plugin_dir: str) -> str:
    """
    Start this plugin.

    Start the worker thread to handle sending to Inara API.
    """
    return 'Inara'


def plugin_app(parent: tk.Tk) -> None:
    """Plugin UI setup Hook."""
    this.parent = parent
    # system label in main window
    this.system_link = parent.nametowidget(f".{appname.lower()}.system")
    # station label in main window
    this.station_link = parent.nametowidget(f".{appname.lower()}.station")


def plugin_stop() -> None:
    """Plugin shutdown hook."""


def journal_entry(  # noqa: C901, CCR001
    cmdr: str, is_beta: bool, system: str, station: str, entry: Dict[str, Any], state: Dict[str, Any]
) -> str:
    """
    Journal entry hook.

    :return: str - empty if no error, else error string.
    """
    # But then we update all the tracking copies before any other checks,
    # because they're relevant for URL providing even if *sending* isn't
    # appropriate.
    this.system_name = state['SystemName']
    this.system_address = state['SystemAddress']

    # Only actually change URLs if we are current provider.
    if config.get_str('system_provider') == 'Inara':
        this.system_link['text'] = this.system_name
        # Do *NOT* set 'url' here, as it's set to a function that will call
        # through correctly.  We don't want a static string.
        this.system_link.update_idletasks()

    if config.get_str('station_provider') == 'Inara':
        to_set: str = cast(str, this.station)
        if not to_set:
            if this.system_population is not None and this.system_population > 0:
                to_set = STATION_UNDOCKED
            else:
                to_set = ''

        this.station_link['text'] = to_set
        # Do *NOT* set 'url' here, as it's set to a function that will call
        # through correctly.  We don't want a static string.
        this.station_link.update_idletasks()

    return ''  # No error
