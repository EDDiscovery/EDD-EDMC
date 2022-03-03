"""System display and EDSM lookup."""

import sys
import tkinter as tk
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping, Optional

import requests

from config import config
from EDMCLogging import get_main_logger

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x

logger = get_main_logger()

this: Any = sys.modules[__name__]  # For holding module globals

# Game state
this.system_link: tk.Tk = None
this.system: tk.Tk = None
this.system_address: Optional[int] = None  # Frontier SystemAddress
this.system_population: Optional[int] = None
this.station_link: tk.Tk = None
this.station: Optional[str] = None
this.on_foot = False
STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7
__cleanup = str.maketrans({' ': None, '\n': None})


# Main window clicks
def system_url(system_name: str) -> str:
    """Get a URL for the current system."""
    if this.system_address:
        return requests.utils.requote_uri(f'https://www.edsm.net/en/system?systemID64={this.system_address}')

    if system_name:
        return requests.utils.requote_uri(f'https://www.edsm.net/en/system?systemName={system_name}')

    return ''


def station_url(system_name: str, station_name: str) -> str:
    """Get a URL for the current station."""
    if system_name and station_name:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={system_name}&stationName={station_name}'
        )

    # monitor state might think these are gone, but we don't yet
    if this.system and this.station:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={this.system}&stationName={this.station}'
        )

    if system_name:
        return requests.utils.requote_uri(
            f'https://www.edsm.net/en/system?systemName={system_name}&stationName=ALL'
        )

    return ''


def plugin_start3(plugin_dir: str) -> str:
    return 'EDSM'


def plugin_app(parent: tk.Tk) -> None:
    """Plugin UI setup."""
    this.system_link = parent.children['system']  # system label in main window
    this.station_link = parent.children['station']  # station label in main window


def journal_entry(
    cmdr: str, is_beta: bool, system: str, station: str, entry: MutableMapping[str, Any], state: Mapping[str, Any]
) -> None:
    # Always update our system address even if we're not currently the provider for system or station, but dont update
    # on events that contain "future" data, such as FSDTarget
    if entry['event'] in ('Location', 'Docked', 'CarrierJump', 'FSDJump'):
        this.system_address = entry.get('SystemAddress', this.system_address)
        this.system = entry.get('StarSystem', this.system)

    # We need pop == 0 to set the value so as to clear 'x' in systems with
    # no stations.
    pop = entry.get('Population')
    if pop is not None:
        this.system_population = pop

    this.station = entry.get('StationName', this.station)
    # on_foot station detection
    if entry['event'] == 'Location' and entry['BodyType'] == 'Station':
        this.station = entry['Body']

    # We might pick up StationName in DockingRequested, make sure we clear it if leaving
    if entry['event'] in ('Undocked', 'FSDJump', 'SupercruiseEntry'):
        this.station = None

    if entry['event'] == 'Embark' and not entry.get('OnStation'):
        # If we're embarking OnStation to a Taxi/Dropship we'll also get an
        # Undocked event.
        this.station = None

    if config.get_str('station_provider') == 'EDSM':
        to_set = this.station
        if not this.station:
            if this.system_population and this.system_population > 0:
                to_set = STATION_UNDOCKED

            else:
                to_set = ''

        this.station_link['text'] = to_set
        this.station_link['url'] = station_url(this.system, str(this.station))
        this.station_link.update_idletasks()

    # Update display of 'EDSM Status' image
    if this.system_link['text'] != system:
        this.system_link['text'] = system if system else ''
        this.system_link['image'] = ''
        this.system_link.update_idletasks()
