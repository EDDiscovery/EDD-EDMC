"""Inara Sync."""

import json
import threading
import time
import tkinter as tk
from collections import OrderedDict, defaultdict, deque
from operator import itemgetter
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, List, Mapping, NamedTuple, Optional
from typing import OrderedDict as OrderedDictT
from typing import Sequence, Union, cast

import requests

import killswitch
import myNotebook as nb  # noqa: N813
import plug
import timeout_session
from config import applongname, appversion, config
from EDMCLogging import get_main_logger
from ttkHyperlinkLabel import HyperlinkLabel

logger = get_main_logger()

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x


_TIMEOUT = 20
FAKE = ('CQC', 'Training', 'Destination')  # Fake systems that shouldn't be sent to Inara
CREDIT_RATIO = 1.05		# Update credits if they change by 5% over the course of a session


# These need to be defined above This
class Credentials(NamedTuple):
    """Credentials holds the set of credentials required to identify an inara API payload to inara."""

    cmdr: Optional[str]
    fid: Optional[str]
    api_key: str


EVENT_DATA = Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]


class Event(NamedTuple):
    """Event represents an event for the Inara API."""

    name: str
    timestamp: str
    data: EVENT_DATA


class This:
    """Holds module globals."""

    def __init__(self):
        self.session = timeout_session.new_session()
        self.thread: Thread
        self.lastlocation = None  # eventData from the last Commander's Flight Log event
        self.lastship = None  # eventData from the last addCommanderShip or setCommanderShip event

        # Cached Cmdr state
        self.cmdr: Optional[str] = None
        self.FID: Optional[str] = None  # Frontier ID
        self.multicrew: bool = False  # don't send captain's ship info to Inara while on a crew
        self.newuser: bool = False  # just entered API Key - send state immediately
        self.newsession: bool = True  # starting a new session - wait for Cargo event
        self.undocked: bool = False  # just undocked
        self.suppress_docked = False  # Skip initial Docked event if started docked
        self.cargo: Optional[List[OrderedDictT[str, Any]]] = None
        self.materials: Optional[List[OrderedDictT[str, Any]]] = None
        self.lastcredits: int = 0  # Send credit update soon after Startup / new game
        self.storedmodules: Optional[List[OrderedDictT[str, Any]]] = None
        self.loadout: Optional[OrderedDictT[str, Any]] = None
        self.fleet: Optional[List[OrderedDictT[str, Any]]] = None
        self.shipswap: bool = False  # just swapped ship
        self.on_foot = False

        self.timer_run = True

        # Main window clicks
        self.system_link: tk.Widget = None  # type: ignore
        self.system: Optional[str] = None  # type: ignore
        self.system_address: Optional[str] = None  # type: ignore
        self.system_population: Optional[int] = None
        self.station_link: tk.Widget = None  # type: ignore
        self.station = None
        self.station_marketid = None

        # Prefs UI
        self.log: 'tk.IntVar'
        self.log_button: nb.Checkbutton
        self.label: HyperlinkLabel
        self.apikey: nb.Entry
        self.apikey_label: HyperlinkLabel

        self.events: Dict[Credentials, Deque[Event]] = defaultdict(deque)
        self.event_lock: Lock = threading.Lock()  # protects events, for use when rewriting events

    def filter_events(self, key: Credentials, predicate: Callable[[Event], bool]) -> None:
        """
        filter_events is the equivalent of running filter() on any event list in the events dict.

        it will automatically handle locking, and replacing the event list with the filtered version.

        :param key: the key to filter
        :param predicate: the predicate to use while filtering
        """
        with self.event_lock:
            tmp = self.events[key].copy()
            self.events[key].clear()
            self.events[key].extend(filter(predicate, tmp))


this = This()
# last time we updated, if unset in config this is 0, which means an instant update
LAST_UPDATE_CONF_KEY = 'inara_last_update'
EVENT_COLLECT_TIME = 31  # Minimum time to take collecting events before requesting a send
WORKER_WAIT_TIME = 35  # Minimum time for worker to wait between sends

STATION_UNDOCKED: str = '×'  # "Station" name to display when not docked = U+00D7


TARGET_URL = 'https://inara.cz/inapi/v1/'


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
    if (ks := killswitch.get_disabled('plugins.inara.journal')).disabled:
        logger.warning(f'Inara support has been disabled via killswitch: {ks.reason}')
        plug.show_error(_('Inara disabled. See Log.'))
        return ''

    elif (ks := killswitch.get_disabled(f'plugins.inara.journal.event.{entry["event"]}')).disabled:
        logger.warning(f'event {entry["event"]} processing has been disabled via killswitch: {ks.reason}')

    this.on_foot = state['OnFoot']
    event_name: str = entry['event']
    this.cmdr = cmdr
    this.FID = state['FID']
    this.multicrew = bool(state['Role'])

    if event_name == 'LoadGame' or this.newuser:
        # clear cached state
        if event_name == 'LoadGame':
            # User setup Inara API while at the loading screen - proceed as for new session
            this.newuser = False
            this.newsession = True

        else:
            this.newuser = True
            this.newsession = False

        this.undocked = False
        this.suppress_docked = False
        this.cargo = None
        this.materials = None
        this.lastcredits = 0
        this.storedmodules = None
        this.loadout = None
        this.fleet = None
        this.shipswap = False
        this.system = None
        this.system_address = None
        this.station = None
        this.station_marketid = None

    elif event_name in ('Resurrect', 'ShipyardBuy', 'ShipyardSell', 'SellShipOnRebuy'):
        # Events that mean a significant change in credits so we should send credits after next "Update"
        this.lastcredits = 0

    elif event_name in ('ShipyardNew', 'ShipyardSwap') or (event_name == 'Location' and entry['Docked']):
        this.suppress_docked = True

    # Always update our system address even if we're not currently the provider for system or station, but dont update
    # on events that contain "future" data, such as FSDTarget
    if entry['event'] in ('Location', 'Docked', 'CarrierJump', 'FSDJump'):
        this.system_address = entry.get('SystemAddress') or this.system_address
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

    this.station_marketid = entry.get('MarketID', this.station_marketid) or this.station_marketid
    # We might pick up StationName in DockingRequested, make sure we clear it if leaving
    if event_name in ('Undocked', 'FSDJump', 'SupercruiseEntry'):
        this.station = None
        this.station_marketid = None

    if entry['event'] == 'Embark' and not entry.get('OnStation'):
        # If we're embarking OnStation to a Taxi/Dropship we'll also get an
        # Undocked event.
        this.station = None
        this.station_marketid = None

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


def update_location(event=None) -> None:
    """
    Update other plugins with our response to system and station changes.

    :param event: Unused and ignored, defaults to None
    """
    if this.lastlocation:
        for plugin in plug.provides('inara_notify_location'):
            plug.invoke(plugin, None, 'inara_notify_location', this.lastlocation)


def inara_notify_location(event_data) -> None:
    """Unused."""
    pass


def update_ship(event=None) -> None:
    """
    Update other plugins with our response to changing.

    :param event: Unused and ignored, defaults to None
    """
    if this.lastship:
        for plugin in plug.provides('inara_notify_ship'):
            plug.invoke(plugin, None, 'inara_notify_ship', this.lastship)
