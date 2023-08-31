"""Station display and eddb.io lookup."""
# Tests:
#
# As there's a lot of state tracking in here, need to ensure (at least)
# the URL text and link follow along correctly with:
#
#  1) Game not running, EDMC started.
#  2) Then hit 'Update' for CAPI data pull
#  3) Login fully to game, and whether #2 happened or not:
#      a) If docked then update Station
#      b) Either way update System
#  4) Undock, SupercruiseEntry, FSDJump should change Station text to 'x'
#    and link to system one.
#  5) RequestDocking should populate Station, no matter if the request
#    succeeded or not.
#  6) FSDJump should update System text+link.
#  7) Switching to a different provider and then back... combined with
#    any of the above in the interim.
#


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
import tkinter
from typing import TYPE_CHECKING, Any, Mapping

import requests

import EDMCLogging
import plug
from config import appname, config

if TYPE_CHECKING:
    from tkinter import Tk

    def _(x: str) -> str:
        return x

logger = EDMCLogging.get_main_logger()


class This:
    """Holds module globals."""

    STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7

    def __init__(self) -> None:
        # Main window clicks
        self.system_link: tkinter.Widget
        self.system_name: str | None = None
        self.system_address: str | None = None
        self.system_population: int | None = None
        self.station_link: tkinter.Widget
        self.station_name: str | None = None
        self.station_marketid: int | None = None
        self.on_foot = False


this = This()


def system_url(system_name: str) -> str:
    """
    Construct an appropriate EDDB.IO URL for the provided system.

    :param system_name: Will be overridden with `this.system_address` if that
      is set.
    :return: The URL, empty if no data was available to construct it.
    """
    if this.system_address:
        return requests.utils.requote_uri(f'https://eddb.io/system/ed-address/{this.system_address}')

    if system_name:
        return requests.utils.requote_uri(f'https://eddb.io/system/name/{system_name}')

    return ''


def station_url(system_name: str, station_name: str) -> str:
    """
    Construct an appropriate EDDB.IO URL for a station.

    Ignores `station_name` in favour of `this.station_marketid`.

    :param system_name: Name of the system the station is in.
    :param station_name: **NOT USED**
    :return: The URL, empty if no data was available to construct it.
    """
    if this.station_marketid:
        return requests.utils.requote_uri(f'https://eddb.io/station/market-id/{this.station_marketid}')

    return system_url(system_name)


def plugin_start3(plugin_dir: str) -> str:
    """
    Start the plugin.

    :param plugin_dir: NAme of directory this was loaded from.
    :return: Identifier string for this plugin.
    """
    return 'eddb'


def plugin_app(parent: 'Tk'):
    """
    Construct this plugin's main UI, if any.

    :param parent: The tk parent to place our widgets into.
    :return: See PLUGINS.md#display
    """
    # system label in main window
    this.system_link = parent.nametowidget(f".{appname.lower()}.system")
    this.system_name = None
    this.system_address = None
    this.station_name = None
    this.station_marketid = None  # Frontier MarketID
    # station label in main window
    this.station_link = parent.nametowidget(f".{appname.lower()}.station")
    this.station_link['popup_copy'] = lambda x: x != this.STATION_UNDOCKED


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    """
    Update any saved configuration after Settings is closed.

    :param cmdr: Name of Commander.
    :param is_beta: If game beta was detected.
    """
    # Do *NOT* set 'url' here, as it's set to a function that will call
    # through correctly.  We don't want a static string.
    pass


def journal_entry(
    cmdr: str, is_beta: bool, system: str, station: str,
    entry: dict[str, Any],
    state: Mapping[str, Any]
):
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
    should_return: bool

    this.on_foot = state['OnFoot']
    this.system_address = state['SystemAddress']
    this.system_name = state['SystemName']
    this.system_population = state['SystemPopulation']
    this.station_name = state['StationName']
    this.station_marketid = state['MarketID']

    # Only change URL text if we are current provider.
    if config.get_str('station_provider') == 'eddb':
        this.system_link['text'] = this.system_name
        # Do *NOT* set 'url' here, as it's set to a function that will call
        # through correctly.  We don't want a static string.
        this.system_link.update_idletasks()

        if this.station_name:
            this.station_link['text'] = this.station_name

        else:
            if this.system_population is not None and this.system_population > 0:
                this.station_link['text'] = this.STATION_UNDOCKED

            else:
                this.station_link['text'] = ''

        # Do *NOT* set 'url' here, as it's set to a function that will call
        # through correctly.  We don't want a static string.
        this.station_link.update_idletasks()
