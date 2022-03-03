"""Inara Sync."""
import tkinter as tk
from typing import TYPE_CHECKING, Any, Dict, Optional
from typing import cast

import requests

from config import config
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
        self.system: Optional[str] = None  # type: ignore
        self.system_population: Optional[int] = None
        self.station_link: tk.Widget = None  # type: ignore
        self.station = None


this = This()

STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7


def system_url(system_name: str) -> str:
    """Get a URL for the current system."""
    if this.system_address:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-starsystem/?search={this.system_address}')

    elif system_name:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-starsystem/?search={system_name}')

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
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-station/?search={system_name}%20[{station_name}]')

    # monitor state might think these are gone, but we don't yet
    if this.system and this.station:
        return requests.utils.requote_uri(f'https://inara.cz/galaxy-station/?search={this.system}%20[{this.station}]')

    if system_name:
        return system_url(system_name)

    return ''


def plugin_start3(plugin_dir: str) -> str:
    """
    Start this plugin.
    """

    return 'Inara'


def plugin_app(parent: tk.Tk) -> None:
    """Plugin UI setup Hook."""
    this.system_link = parent.children['system']  # system label in main window
    this.station_link = parent.children['station']  # station label in main window


def plugin_stop() -> None:
    """Plugin shutdown hook."""


def journal_entry(  # noqa: C901, CCR001
    cmdr: str, is_beta: bool, system: str, station: str, entry: Dict[str, Any], state: Dict[str, Any]
) -> str:
    """
    Journal entry hook.

    :return: str - empty if no error, else error string.
    """
    event_name: str = entry['event']

    if event_name == 'LoadGame':
        # clear cached state
        this.system = None
        this.station = None

    # Always update our system address even if we're not currently the provider for system or station, but dont update
    # on events that contain "future" data, such as FSDTarget
    if entry['event'] in ('Location', 'Docked', 'CarrierJump', 'FSDJump'):
        this.system = entry.get('StarSystem') or this.system

    # We need pop == 0 to set the value so as to clear 'x' in systems with
    # no stations.
    pop: Optional[int] = entry.get('Population')
    if pop is not None:
        this.system_population = pop

    this.station = entry.get('StationName', this.station)
    # on_foot station detection
    if entry['event'] == 'Location' and entry['BodyType'] == 'Station':
        this.station = entry['Body']

    # We might pick up StationName in DockingRequested, make sure we clear it if leaving
    if event_name in ('Undocked', 'FSDJump', 'SupercruiseEntry'):
        this.station = None

    if entry['event'] == 'Embark' and not entry.get('OnStation'):
        # If we're embarking OnStation to a Taxi/Dropship we'll also get an
        # Undocked event.
        this.station = None

    # Only actually change URLs if we are current provider.
    if config.get_str('system_provider') == 'Inara':
        this.system_link['text'] = this.system
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
