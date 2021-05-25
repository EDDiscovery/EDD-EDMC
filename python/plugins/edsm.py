"""System display and EDSM lookup."""

# TODO:
#  1) Re-factor EDSM API calls out of journal_entry() into own function.
#  2) Fix how StartJump already changes things, but only partially.
#  3) Possibly this and other two 'provider' plugins could do with being
#    based on a single class that they extend.  There's a lot of duplicated
#    logic.
#  4) Ensure the EDSM API call(back) for setting the image at end of system
#    text is always fired.  i.e. CAPI cmdr_data() processing.

import json
import sys
import tkinter as tk
from queue import Queue
from threading import Thread
from typing import TYPE_CHECKING, Any, List, Mapping, MutableMapping, Optional, Tuple, cast

import requests

import killswitch
import myNotebook as nb  # noqa: N813
import plug
from config import applongname, appversion, config
from EDMCLogging import get_main_logger
from ttkHyperlinkLabel import HyperlinkLabel

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x

logger = get_main_logger()

EDSM_POLL = 0.1
_TIMEOUT = 20


this: Any = sys.modules[__name__]  # For holding module globals
this.discardedEvents: List[str] = []  # List discarded events from EDSM
this.lastlookup: bool = False		# whether the last lookup succeeded

# Game state
this.multicrew: bool = False  # don't send captain's ship info to EDSM while on a crew
this.coordinates: Optional[Tuple[int, int, int]] = None
this.newgame: bool = False  # starting up - batch initial burst of events
this.newgame_docked: bool = False  # starting up while docked
this.navbeaconscan: int = 0		# batch up burst of Scan events after NavBeaconScan
this.system_link: tk.Tk = None
this.system: tk.Tk = None
this.system_address: Optional[int] = None  # Frontier SystemAddress
this.system_population: Optional[int] = None
this.station_link: tk.Tk = None
this.station: Optional[str] = None
this.station_marketid: Optional[int] = None  # Frontier MarketID
this.on_foot = False
STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7
__cleanup = str.maketrans({' ': None, '\n': None})
IMG_KNOWN_B64 = """
R0lGODlhEAAQAMIEAFWjVVWkVWS/ZGfFZ////////////////yH5BAEKAAQALAAAAAAQABAAAAMvSLrc/lAFIUIkYOgNXt5g14Dk0AQlaC1CuglM6w7wgs7r
MpvNV4q932VSuRiPjQQAOw==
""".translate(__cleanup)

IMG_UNKNOWN_B64 = """
R0lGODlhEAAQAKEDAGVLJ+ddWO5fW////yH5BAEKAAMALAAAAAAQABAAAAItnI+pywYRQBtA2CtVvTwjDgrJFlreEJRXgKSqwB5keQ6vOKq1E+7IE5kIh4kC
ADs=
""".translate(__cleanup)

IMG_NEW_B64 = """
R0lGODlhEAAQAMZwANKVHtWcIteiHuiqLPCuHOS1MN22ZeW7ROG6Zuu9MOy+K/i8Kf/DAuvCVf/FAP3BNf/JCf/KAPHHSv7ESObHdv/MBv/GRv/LGP/QBPXO
PvjPQfjQSvbRSP/UGPLSae7Sfv/YNvLXgPbZhP7dU//iI//mAP/jH//kFv7fU//fV//ebv/iTf/iUv/kTf/iZ/vgiP/hc/vgjv/jbfriiPriiv7ka//if//j
d//sJP/oT//tHv/mZv/sLf/rRP/oYv/rUv/paP/mhv/sS//oc//lkf/mif/sUf/uPv/qcv/uTv/uUv/vUP/qhP/xP//pm//ua//sf//ubf/wXv/thv/tif/s
lv/tjf/smf/yYP/ulf/2R//2Sv/xkP/2av/0gP/ylf/2df/0i//0j//0lP/5cP/7a//1p//5gf/7ev/3o//2sf/5mP/6kv/2vP/3y//+jP//////////////
/////////////////////////////////////////////////yH5BAEKAH8ALAAAAAAQABAAAAePgH+Cg4SFhoJKPIeHYT+LhVppUTiPg2hrUkKPXWdlb2xH
Jk9jXoNJQDk9TVtkYCUkOy4wNjdGfy1UXGJYOksnPiwgFwwYg0NubWpmX1ArHREOFYUyWVNIVkxXQSoQhyMoNVUpRU5EixkcMzQaGy8xhwsKHiEfBQkSIg+G
BAcUCIIBBDSYYGiAAUMALFR6FAgAOw==
""".translate(__cleanup)

IMG_ERR_B64 = """
R0lGODlhEAAQAKEBAAAAAP///////////yH5BAEKAAIALAAAAAAQABAAAAIwlBWpeR0AIwwNPRmZuVNJinyWuClhBlZjpm5fqnIAHJPtOd3Hou9mL6NVgj2L
plEAADs=
""".translate(__cleanup)


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
    """Plugin setup hook."""
    # Can't be earlier since can only call PhotoImage after window is created
    this._IMG_KNOWN = tk.PhotoImage(data=IMG_KNOWN_B64)  # green circle
    this._IMG_UNKNOWN = tk.PhotoImage(data=IMG_UNKNOWN_B64)  # red circle
    this._IMG_NEW = tk.PhotoImage(data=IMG_NEW_B64)
    this._IMG_ERROR = tk.PhotoImage(data=IMG_ERR_B64)  # BBC Mode 5 '?'

    # Migrate old settings
    if not config.get_list('edsm_cmdrs'):
        if isinstance(config.get_list('cmdrs'), list) and config.get_list('edsm_usernames') and config.get_list('edsm_apikeys'):
            # Migrate <= 2.34 settings
            config.set('edsm_cmdrs', config.get_list('cmdrs'))

        elif config.get_list('edsm_cmdrname'):
            # Migrate <= 2.25 settings. edsm_cmdrs is unknown at this time
            config.set('edsm_usernames', [config.get_str('edsm_cmdrname', default='')])
            config.set('edsm_apikeys',   [config.get_str('edsm_apikey', default='')])

        config.delete('edsm_cmdrname', suppress=True)
        config.delete('edsm_apikey', suppress=True)

    if config.get_int('output') & 256:
        # Migrate <= 2.34 setting
        config.set('edsm_out', 1)

    config.delete('edsm_autoopen', suppress=True)
    config.delete('edsm_historical', suppress=True)

    return 'EDSM'


def plugin_app(parent: tk.Tk) -> None:
    """Plugin UI setup."""
    this.system_link = parent.children['system']  # system label in main window
    this.station_link = parent.children['station']  # station label in main window


def journal_entry(
    cmdr: str, is_beta: bool, system: str, station: str, entry: MutableMapping[str, Any], state: Mapping[str, Any]
) -> None:
    """Journal Entry hook."""
    if (ks := killswitch.get_disabled('plugins.edsm.journal')).disabled:
        logger.warning(f'EDSM Journal handler disabled via killswitch: {ks.reason}')
        plug.show_error(_('EDSM Handler disabled. See Log.'))
        return

    elif (ks := killswitch.get_disabled(f'plugins.edsm.journal.event.{entry["event"]}')).disabled:
        logger.warning(f'Handling of event {entry["event"]} has been disabled via killswitch: {ks.reason}')
        return

    this.on_foot = state['OnFoot']
    # if entry['event'] in ('CarrierJump', 'FSDJump', 'Location', 'Docked'):
    #     logger.trace(f'''{entry["event"]}
# Commander: {cmdr}
# System: {system}
# Station: {station}
# state: {state!r}
# entry: {entry!r}'''
#                      )
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

    this.station_marketid = entry.get('MarketID', this.station_marketid)
    # We might pick up StationName in DockingRequested, make sure we clear it if leaving
    if entry['event'] in ('Undocked', 'FSDJump', 'SupercruiseEntry'):
        this.station = None
        this.station_marketid = None

    if entry['event'] == 'Embark' and not entry.get('OnStation'):
        # If we're embarking OnStation to a Taxi/Dropship we'll also get an
        # Undocked event.
        this.station = None
        this.station_marketid = None

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

    this.multicrew = bool(state['Role'])
    if 'StarPos' in entry:
        this.coordinates = entry['StarPos']

    elif entry['event'] == 'LoadGame':
        this.coordinates = None

    if entry['event'] in ('LoadGame', 'Commander', 'NewCommander'):
        this.newgame = True
        this.newgame_docked = False
        this.navbeaconscan = 0

    elif entry['event'] == 'StartUp':
        this.newgame = False
        this.newgame_docked = False
        this.navbeaconscan = 0

    elif entry['event'] == 'Location':
        this.newgame = True
        this.newgame_docked = entry.get('Docked', False)
        this.navbeaconscan = 0

    elif entry['event'] == 'NavBeaconScan':
        this.navbeaconscan = entry['NumBodies']

    elif entry['event'] == 'BackPack':
        # Use the stored file contents, not the empty journal event
        if state['BackpackJSON']:
            entry = state['BackpackJSON']
