"""Show EDSM data in display and handle lookups."""

# TODO:
#  1) Re-factor EDSM API calls out of journal_entry() into own function.
#  2) Fix how StartJump already changes things, but only partially.
#  3) Possibly this and other two 'provider' plugins could do with being
#    based on a single class that they extend.  There's a lot of duplicated
#    logic.
#  4) Ensure the EDSM API call(back) for setting the image at end of system
#    text is always fired.  i.e. CAPI cmdr_data() processing.

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
#     `Build-exe-and-msi.py` SO AS TO ENSURE THE FILES ARE ACTUALLY PRESENT IN
#     AN END-USER INSTALLATION ON WINDOWS.
#
#
# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#
# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $# ! $#

import tkinter as tk
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Mapping, MutableMapping, Optional, Set, Tuple, Union, cast

import requests

import plug
from config import appname, config
from EDMCLogging import get_main_logger

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x

logger = get_main_logger()

class This:
    """Holds module globals."""

    def __init__(self):

        # Game state
        self.system_link: tk.Widget | None = None
        self.system_name: tk.Tk | None = None
        self.system_address: int | None = None  # Frontier SystemAddress
        self.system_population: int | None = None
        self.station_link: tk.Widget | None = None
        self.station_name: str | None = None
        self.on_foot = False


this = This()

STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7
__cleanup = str.maketrans({' ': None, '\n': None})


# Main window clicks
def system_url(system_name: str) -> str:
    """
    Construct an appropriate EDSM URL for the provided system.

    :param system_name: Will be overridden with `this.system_address` if that
      is set.
    :return: The URL, empty if no data was available to construct it.
    """
    if this.system_address:
        return requests.utils.requote_uri(f'https://www.edsm.net/en/system?systemID64={this.system_address}')

    if system_name:
        return requests.utils.requote_uri(f'https://www.edsm.net/en/system?systemName={system_name}')

    return ''


def station_url(system_name: str, station_name: str) -> str:
    """
    Construct an appropriate EDSM URL for a station.

    :param system_name: Name of the system the station is in.
    :param station_name: Name of the station.
    :return: The URL, empty if no data was available to construct it.
    """
    if system_name and station_name:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={system_name}&stationName={station_name}'
        )

    # monitor state might think these are gone, but we don't yet
    if this.system_name and this.station_name:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={this.system_name}&stationName={this.station_name}'
        )

    if system_name:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={system_name}&stationName=ALL'
        )

    return ''


def plugin_start3(plugin_dir: str) -> str:
    """
    Start the plugin.

    :param plugin_dir: NAme of directory this was loaded from.
    :return: Identifier string for this plugin.
    """
    return 'EDSM'


def plugin_app(parent: tk.Tk) -> None:
    """
    Construct this plugin's main UI, if any.

    :param parent: The tk parent to place our widgets into.
    :return: See PLUGINS.md#display
    """
    # system label in main window
    this.system_link = parent.nametowidget(f".{appname.lower()}.system")
    if this.system_link is None:
        logger.error("Couldn't look up system widget!!!")
        return

    this.system_link.bind_all('<<EDSMStatus>>', update_status)
    # station label in main window
    this.station_link = parent.nametowidget(f".{appname.lower()}.station")


def journal_entry(  # noqa: C901, CCR001
    cmdr: str, is_beta: bool, system: str, station: str, entry: MutableMapping[str, Any], state: Mapping[str, Any]
) -> str:
    """
    Handle a new Journal event.

    :param cmdr: Name of Commander.
    :param is_beta: Whether game beta was detected.
    :param system: Name of current tracked system.
    :param station: Name of current tracked station location.
    :param entry: The journal event.
    :param state: `monitor.state`
    :return: None if no error, else an error string.
    """

    this.game_version = state['GameVersion']
    this.game_build = state['GameBuild']
    this.system_address = state['SystemAddress']
    this.system_name = state['SystemName']
    this.system_population = state['SystemPopulation']
    this.station_name = state['StationName']
    this.station_marketid = state['MarketID']

    this.on_foot = state['OnFoot']
    if entry['event'] in ('CarrierJump', 'FSDJump', 'Location', 'Docked'):
        logger.trace_if(
            'journal.locations', f'''{entry["event"]}
Commander: {cmdr}
System: {system}
Station: {station}
state: {state!r}
entry: {entry!r}'''
        )

    if config.get_str('station_provider') == 'EDSM':
        to_set = this.station_name
        if not this.station_name:
            if this.system_population and this.system_population > 0:
                to_set = STATION_UNDOCKED

            else:
                to_set = ''

        if this.station_link:
            this.station_link['text'] = to_set
            this.station_link['url'] = station_url(str(this.system_name), str(this.station_name))
            this.station_link.update_idletasks()

    # Update display of 'EDSM Status' image
    if this.system_link and this.system_link['text'] != system:
        this.system_link['text'] = system if system else ''
        this.system_link['image'] = ''
        this.system_link.update_idletasks()


def update_status(event=None) -> None:
    """Update listening plugins with our response to StartUp, Location, FSDJump, or CarrierJump."""
    for plugin in plug.provides('edsm_notify_system'):
        plug.invoke(plugin, None, 'edsm_notify_system', this.lastlookup)