"""Monitor for new Journal files and contents of latest."""

import os
import json
import re
import threading
from calendar import timegm
from collections import OrderedDict, defaultdict
from os import SEEK_END, SEEK_SET, listdir
from os.path import basename, expanduser, isdir, join
from sys import platform
from time import gmtime, localtime, sleep, strftime, strptime, time
from typing import TYPE_CHECKING, Any, Dict, List, MutableMapping, Optional
from typing import OrderedDict as OrderedDictT
from typing import Tuple

if TYPE_CHECKING:
    import tkinter

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

import util_ships
from config import config
from edmc_data import edmc_suit_shortnames, edmc_suit_symbol_localised
from EDMCLogging import get_main_logger

logger = get_main_logger()

if TYPE_CHECKING:
    def _(x: str) -> str:
        return x

if platform == 'darwin':
    from fcntl import fcntl

    from AppKit import NSWorkspace
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    F_GLOBAL_NOCACHE = 55

elif platform == 'win32':
    import ctypes
    from ctypes.wintypes import BOOL, HWND, LPARAM, LPWSTR

    from watchdog.events import FileCreatedEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)

    CloseHandle = ctypes.windll.kernel32.CloseHandle

    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowText.argtypes = [HWND, LPWSTR, ctypes.c_int]
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW

    GetProcessHandleFromHwnd = ctypes.windll.oleacc.GetProcessHandleFromHwnd

else:
    # Linux's inotify doesn't work over CIFS or NFS, so poll
    FileSystemEventHandler = object  # dummy


# Journal handler
class EDLogs:  # type: ignore # See below
    """Monitoring of Journal files."""

    # Magic with FileSystemEventHandler can confuse type checkers when they do not have access to every import

    _POLL = 1		# Polling is cheap, so do it often
    _RE_CANONICALISE = re.compile(r'\$(.+)_name;')
    _RE_CATEGORY = re.compile(r'\$MICRORESOURCE_CATEGORY_(.+);')
    _RE_LOGFILE = re.compile(r'^Journal(Alpha|Beta)?\.[0-9]{12}\.[0-9]{2}\.log$')
    _RE_SHIP_ONFOOT = re.compile(r'^(FlightSuit|UtilitySuit_Class.|TacticalSuit_Class.|ExplorationSuit_Class.)$')

    def __init__(self) -> None:
        # TODO(A_D): A bunch of these should be switched to default values (eg '' for strings) and no longer be Optional
        self.root: 'tkinter.Tk' = None  # type: ignore # Don't use Optional[] - mypy thinks no methods
        self.currentdir: Optional[str] = None  # The actual logdir that we're monitoring
        self.logfile: Optional[str] = None
        self.observer: Optional['Observer'] = None
        self.observed = None  # a watchdog ObservedWatch, or None if polling
        self.thread: Optional[threading.Thread] = None
        # For communicating journal entries back to main thread
        self.event_queue = []		# For communicating journal entries back to main thread

        # On startup we might be:
        # 1) Looking at an old journal file because the game isn't running or the user has exited to the main menu.
        # 2) Looking at an empty journal (only 'Fileheader') because the user is at the main menu.
        # 3) In the middle of a 'live' game.
        # If 1 or 2 a LoadGame event will happen when the game goes live.
        # If 3 we need to inject a special 'StartUp' event since consumers won't see the LoadGame event.
        self.live = False

        self.game_was_running = False  # For generation of the "ShutDown" event

        # Context for journal handling
        self.version: Optional[str] = None
        self.is_beta = False
        self.mode: Optional[str] = None
        self.group: Optional[str] = None
        self.cmdr: Optional[str] = None
        self.planet: Optional[str] = None
        self.system: Optional[str] = None
        self.station: Optional[str] = None
        self.station_marketid: Optional[int] = None
        self.stationtype: Optional[str] = None
        self.coordinates: Optional[Tuple[float, float, float]] = None
        self.systemaddress: Optional[int] = None
        self.systempopulation: Optional[int] = None
        self.started: Optional[int] = None  # Timestamp of the LoadGame event

        self.logposstored = 0
        self.logposcurrent = 0

        self.__init_state()

    def __init_state(self) -> None:
        # Cmdr state shared with EDSM and plugins
        # If you change anything here update PLUGINS.md documentation!
        self.state: Dict = {
            'GameLanguage':       None,  # From `Fileheader
            'GameVersion':        None,  # From `Fileheader
            'GameBuild':          None,  # From `Fileheader
            'Captain':            None,  # On a crew
            'Cargo':              defaultdict(int),
            'Credits':            None,
            'FID':                None,  # Frontier Cmdr ID
            'Horizons':           None,  # Does this user have Horizons?
            'Odyssey':            False,  # Have we detected we're running under Odyssey?
            'Loan':               None,
            'Raw':                defaultdict(int),
            'Manufactured':       defaultdict(int),
            'Encoded':            defaultdict(int),
            'Engineers':          {},
            'Rank':               {},
            'Reputation':         {},
            'Statistics':         {},
            'Role':               None,  # Crew role - None, Idle, FireCon, FighterCon
            'Friends':            set(),  # Online friends
            'ShipID':             None,
            'ShipIdent':          None,
            'ShipName':           None,
            'ShipType':           None,
            'HullValue':          None,
            'ModulesValue':       None,
            'Rebuy':              None,
            'Modules':            None,
            'CargoJSON':          None,  # The raw data from the last time cargo.json was read
            'Route':              None,  # Last plotted route from Route.json file
            'OnFoot':             False,  # Whether we think you're on-foot
            'Component':          defaultdict(int),      # Odyssey Components in Ship Locker
            'Item':               defaultdict(int),      # Odyssey Items in Ship Locker
            'Consumable':         defaultdict(int),      # Odyssey Consumables in Ship Locker
            'Data':               defaultdict(int),      # Odyssey Data in Ship Locker
            'BackPack':     {                      # Odyssey BackPack contents
                'Component':      defaultdict(int),    # BackPack Components
                'Consumable':     defaultdict(int),    # BackPack Consumables
                'Item':           defaultdict(int),    # BackPack Items
                'Data':           defaultdict(int),  # Backpack Data
            },
            'BackpackJSON':       None,  # Raw JSON from `Backpack.json` file, if available
            'SuitCurrent':        None,
            'Suits':              {},
            'SuitLoadoutCurrent': None,
            'SuitLoadouts':       {},
        }

        self.my_observer = None

        self.lastloc = None

    def start(self, root):
        self.root = root
        patterns = ["*.edd"]
        ignore_patterns = ""
        ignore_directories = False
        case_sensitive = True
        my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)
        my_event_handler.on_created = self.on_created
        my_event_handler.on_modified = self.on_modified
        go_recursively = False

        path = config.app_dir

        # edmc may be slow starting, stored/current may already  be there, process

        stored = join(path, "stored.edd")
        if os.path.exists(stored):
            logger.info("Stored exists, processing")
            self.readfile(stored)

        current = join(path, "current.edd")
        if os.path.exists(current):
            logger.info("Current exists, processing")
            self.readfile(current)

        my_observer = Observer()
        my_observer.schedule(my_event_handler, path, recursive=go_recursively)
        my_observer.start()

        #print(f"Monitor started on {path}")

    def stop(self):
        logger.info("Monitor stopping")
        if self.my_observer:
            self.my_observer.stop()
        if self.my_observer:
            self.my_observer.join()
            self.my_observer = None
        logger.info("Monitor stopped")

    def close(self):
        self.stop()

    def on_created(self,event):
        logger.info(f"{event.src_path} has been created!")

    def on_modified(self, event):
        #print(f"{event.src_path} has been modified")
        self.readfile(event.src_path)

    def readfile(self,path):
        loghandle = open(path, 'rb', 0)	# unbuffered

        if 'current' in path:
            loghandle.seek(self.logposcurrent, SEEK_SET)	# reset EOF flag

            for line in loghandle:
                logger.info(f'Current Line {line}')
                self.event_queue.append(line)
                self.root.event_generate('<<JournalEvent>>', when="tail")

            self.logposcurrent = loghandle.tell()

        elif 'stored' in path:
            loghandle.seek(self.logposstored, SEEK_SET)	# reset EOF flag

            for line in loghandle:
                logger.info(f'Stored Line {line}')
                entry = self.parse_entry(line)             # stored ones are parsed now for state update

                if entry['event'] == 'Harness-NewVersion':      # send this thru to the foreground for processing
                    self.event_queue.append(line)
                    self.root.event_generate('<<JournalEvent>>', when="tail")

                elif entry['event'] == 'Location' or entry['event'] == 'FSDJump':     # for now, not going to do anything with this, but may feed it thru if required later
                    self.lastloc = entry

                elif entry['event'] == 'RefreshOver':       # its stored, and we have a refresh over, its the end of the refresh cycle.
                    if not (self.lastloc is None):
                        logger.info("Send a Startup as we have a location")
                        entry = OrderedDict([
                            ('timestamp', strftime('%Y-%m-%dT%H:%M:%SZ', gmtime())),
                            ('event', 'StartUp'),
                            ('StarSystem', self.system),
                            ('StarPos', self.coordinates),
                            ('SystemAddress', self.systemaddress),
                            ('Population', self.systempopulation),
                        ])
                        if self.planet:
                            entry['Body'] = self.planet
                        entry['Docked'] = bool(self.station)
                        if self.station:
                            entry['StationName'] = self.station
                            entry['StationType'] = self.stationtype
                            entry['MarketID'] = self.station_marketid

                        self.event_queue.append(json.dumps(entry, separators=(', ', ':')))
                    else:
                        logger.info("No location, send a None")
                        self.event_queue.append(None)	# Generate null event to update the display (with possibly out-of-date info)

                    self.root.event_generate('<<JournalEvent>>', when="tail")   # generate an event for the foreground

            self.logposstored = loghandle.tell();

    def get_entry(self):
        if not self.event_queue:
            return None
        else:
            entry = self.parse_entry(self.event_queue.pop(0))
            return entry

# Direct from EDMC, synced 28 May 2021 with <commit>

    def parse_entry(self, line: bytes) -> MutableMapping[str, Any]:  # noqa: C901, CCR001
        """
        Parse a Journal JSON line.

        This augments some events, sets internal state in reaction to many and
        loads some extra files, e.g. Cargo.json, as necessary.

        :param line: bytes - The entry being parsed.  Yes, this is bytes, not str.
                             We rely on json.loads() dealing with this properly.
        :return: Dict of the processed event.
        """
        # TODO(A_D): a bunch of these can be simplified to use if itertools.product and filters
        if line is None:
            return {'event': None}  # Fake startup event

        try:
            # Preserve property order because why not?
            entry: MutableMapping[str, Any] = json.loads(line, object_pairs_hook=OrderedDict)
            entry['timestamp']  # we expect this to exist # TODO: replace with assert? or an if key in check

            event_type = entry['event']
            if event_type == 'Fileheader':
                self.live = False
                self.version = entry['gameversion']
                self.is_beta = any(v in entry['gameversion'].lower() for v in ('alpha', 'beta'))

                self.cmdr = None
                self.mode = None
                self.group = None
                self.planet = None
                self.system = None
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None
                self.started = None
                self.__init_state()
                # In self.state as well, as that's what plugins get
                self.state['GameLanguage'] = entry['language']
                self.state['GameVersion'] = entry['gameversion']
                self.state['GameBuild'] = entry['build']

            elif event_type == 'Commander':
                self.live = True  # First event in 3.0

            elif event_type == 'LoadGame':
                self.cmdr = entry['Commander']
                # 'Open', 'Solo', 'Group', or None for CQC (and Training - but no LoadGame event)
                self.mode = entry.get('GameMode')
                self.group = entry.get('Group')
                self.planet = None
                self.system = None
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None
                self.started = timegm(strptime(entry['timestamp'], '%Y-%m-%dT%H:%M:%SZ'))
                # Don't set Ship, ShipID etc since this will reflect Fighter or SRV if starting in those
                self.state.update({
                    'Captain':    None,
                    'Credits':    entry['Credits'],
                    'FID':        entry.get('FID'),   # From 3.3
                    'Horizons':   entry['Horizons'],  # From 3.0
                    'Odyssey':    entry.get('Odyssey', False),  # From 4.0 Odyssey
                    'Loan':       entry['Loan'],
                    'Engineers':  {},
                    'Rank':       {},
                    'Reputation': {},
                    'Statistics': {},
                    'Role':       None,
                })
                if entry.get('Ship') is not None and self._RE_SHIP_ONFOOT.search(entry['Ship']):
                    self.state['OnFoot'] = True

            elif event_type == 'NewCommander':
                self.cmdr = entry['Name']
                self.group = None

            elif event_type == 'SetUserShipName':
                self.state['ShipID'] = entry['ShipID']
                if 'UserShipId' in entry:  # Only present when changing the ship's ident
                    self.state['ShipIdent'] = entry['UserShipId']

                self.state['ShipName'] = entry.get('UserShipName')
                self.state['ShipType'] = self.canonicalise(entry['Ship'])

            elif event_type == 'ShipyardBuy':
                self.state['ShipID'] = None
                self.state['ShipIdent'] = None
                self.state['ShipName'] = None
                self.state['ShipType'] = self.canonicalise(entry['ShipType'])
                self.state['HullValue'] = None
                self.state['ModulesValue'] = None
                self.state['Rebuy'] = None
                self.state['Modules'] = None

                self.state['Credits'] -= entry.get('ShipPrice', 0)

            elif event_type == 'ShipyardSwap':
                self.state['ShipID'] = entry['ShipID']
                self.state['ShipIdent'] = None
                self.state['ShipName'] = None
                self.state['ShipType'] = self.canonicalise(entry['ShipType'])
                self.state['HullValue'] = None
                self.state['ModulesValue'] = None
                self.state['Rebuy'] = None
                self.state['Modules'] = None

            elif (event_type == 'Loadout' and
                  'fighter' not in self.canonicalise(entry['Ship']) and
                  'buggy' not in self.canonicalise(entry['Ship'])):
                self.state['ShipID'] = entry['ShipID']
                self.state['ShipIdent'] = entry['ShipIdent']

                # Newly purchased ships can show a ShipName of "" initially,
                # and " " after a game restart/relog.
                # Players *can* also purposefully set " " as the name, but anyone
                # doing that gets to live with EDMC showing ShipType instead.
                if entry['ShipName'] and entry['ShipName'] not in ('', ' '):
                    self.state['ShipName'] = entry['ShipName']

                self.state['ShipType'] = self.canonicalise(entry['Ship'])
                self.state['HullValue'] = entry.get('HullValue')  # not present on exiting Outfitting
                self.state['ModulesValue'] = entry.get('ModulesValue')  # not present on exiting Outfitting
                self.state['Rebuy'] = entry.get('Rebuy')
                # Remove spurious differences between initial Loadout event and subsequent
                self.state['Modules'] = {}
                for module in entry['Modules']:
                    module = dict(module)
                    module['Item'] = self.canonicalise(module['Item'])
                    if ('Hardpoint' in module['Slot'] and
                        not module['Slot'].startswith('TinyHardpoint') and
                            module.get('AmmoInClip') == module.get('AmmoInHopper') == 1):  # lasers
                        module.pop('AmmoInClip')
                        module.pop('AmmoInHopper')

                    self.state['Modules'][module['Slot']] = module

            elif event_type == 'ModuleBuy':
                self.state['Modules'][entry['Slot']] = {
                    'Slot':     entry['Slot'],
                    'Item':     self.canonicalise(entry['BuyItem']),
                    'On':       True,
                    'Priority': 1,
                    'Health':   1.0,
                    'Value':    entry['BuyPrice'],
                }

                self.state['Credits'] -= entry.get('BuyPrice', 0)

            elif event_type == 'ModuleRetrieve':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'ModuleSell':
                self.state['Modules'].pop(entry['Slot'], None)
                self.state['Credits'] += entry.get('SellPrice', 0)

            elif event_type == 'ModuleSellRemote':
                self.state['Credits'] += entry.get('SellPrice', 0)

            elif event_type == 'ModuleStore':
                self.state['Modules'].pop(entry['Slot'], None)
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'ModuleSwap':
                to_item = self.state['Modules'].get(entry['ToSlot'])
                to_slot = entry['ToSlot']
                from_slot = entry['FromSlot']
                modules = self.state['Modules']
                modules[to_slot] = modules[from_slot]
                if to_item:
                    modules[from_slot] = to_item

                else:
                    modules.pop(from_slot, None)

            elif event_type == 'Undocked':
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None

            elif event_type == 'Embark':
                # This event is logged when a player (on foot) gets into a ship or SRV
                # Parameters:
                #     • SRV: true if getting into SRV, false if getting into a ship
                #     • Taxi: true when boarding a taxi transposrt ship
                #     • Multicrew: true when boarding another player’s vessel
                #     • ID: player’s ship ID (if players own vessel)
                #     • StarSystem
                #     • SystemAddress
                #     • Body
                #     • BodyID
                #     • OnStation: bool
                #     • OnPlanet: bool
                #     • StationName (if at a station)
                #     • StationType
                #     • MarketID
                self.station = None
                if entry.get('OnStation'):
                    self.station = entry.get('StationName', '')

                self.state['OnFoot'] = False

            elif event_type == 'Disembark':
                # This event is logged when the player steps out of a ship or SRV
                #
                # Parameters:
                #     • SRV: true if getting out of SRV, false if getting out of a ship
                #     • Taxi: true when getting out of a taxi transposrt ship
                #     • Multicrew: true when getting out of another player’s vessel
                #     • ID: player’s ship ID (if players own vessel)
                #     • StarSystem
                #     • SystemAddress
                #     • Body
                #     • BodyID
                #     • OnStation: bool
                #     • OnPlanet: bool
                #     • StationName (if at a station)
                #     • StationType
                #     • MarketID

                if entry.get('OnStation', False):
                    self.station = entry.get('StationName', '')

                else:
                    self.station = None

                self.state['OnFoot'] = True

            elif event_type == 'DropshipDeploy':
                # We're definitely on-foot now
                self.state['OnFoot'] = True

            elif event_type == 'Docked':
                self.station = entry.get('StationName')  # May be None
                self.station_marketid = entry.get('MarketID')  # May be None
                self.stationtype = entry.get('StationType')  # May be None
                self.stationservices = entry.get('StationServices')  # None under E:D < 2.4

            elif event_type in ('Location', 'FSDJump', 'CarrierJump'):
                # alpha4 - any changes ?
                # Location:
                # New in Odyssey:
                #     • Taxi: bool
                #     • Multicrew: bool
                #     • InSRV: bool
                #     • OnFoot: bool
                if event_type in ('Location', 'CarrierJump'):
                    self.planet = entry.get('Body') if entry.get('BodyType') == 'Planet' else None

                    # if event_type == 'Location':
                    #     logger.trace('"Location" event')

                elif event_type == 'FSDJump':
                    self.planet = None

                if 'StarPos' in entry:
                    self.coordinates = tuple(entry['StarPos'])  # type: ignore

                self.systemaddress = entry.get('SystemAddress')

                self.systempopulation = entry.get('Population')

                self.system = 'CQC' if entry['StarSystem'] == 'ProvingGround' else entry['StarSystem']

                self.station = entry.get('StationName')  # May be None
                # If on foot in-station 'Docked' is false, but we have a
                # 'BodyType' of 'Station', and the 'Body' is the station name
                # NB: No MarketID
                if entry.get('BodyType') and entry['BodyType'] == 'Station':
                    self.station = entry.get('Body')

                self.station_marketid = entry.get('MarketID')  # May be None
                self.stationtype = entry.get('StationType')  # May be None
                self.stationservices = entry.get('StationServices')  # None in Odyssey for on-foot 'Location'

            elif event_type == 'ApproachBody':
                self.planet = entry['Body']

            elif event_type in ('LeaveBody', 'SupercruiseEntry'):
                self.planet = None

            elif event_type in ('Rank', 'Promotion'):
                payload = dict(entry)
                payload.pop('event')
                payload.pop('timestamp')

                self.state['Rank'].update({k: (v, 0) for k, v in payload.items()})

            elif event_type == 'Progress':
                rank = self.state['Rank']
                for k, v in entry.items():
                    if k in rank:
                        # perhaps not taken promotion mission yet
                        rank[k] = (rank[k][0], min(v, 100))

            elif event_type in ('Reputation', 'Statistics'):
                payload = OrderedDict(entry)
                payload.pop('event')
                payload.pop('timestamp')
                self.state[event_type] = payload

            elif event_type == 'EngineerProgress':
                # Sanity check - at least once the 'Engineer' (name) was missing from this in early
                # Odyssey 4.0.0.100.  Might only have been a server issue causing incomplete data.

                if self.event_valid_engineerprogress(entry):
                    engineers = self.state['Engineers']
                    if 'Engineers' in entry:  # Startup summary
                        self.state['Engineers'] = {
                            e['Engineer']: ((e['Rank'], e.get('RankProgress', 0)) if 'Rank' in e else e['Progress'])
                            for e in entry['Engineers']
                        }

                    else:  # Promotion
                        engineer = entry['Engineer']
                        if 'Rank' in entry:
                            engineers[engineer] = (entry['Rank'], entry.get('RankProgress', 0))

                        else:
                            engineers[engineer] = entry['Progress']

            elif event_type == 'Cargo' and entry.get('Vessel') == 'Ship':
                self.state['Cargo'] = defaultdict(int)
                self.state['CargoJSON'] = self.state['Cargo']

                clean = self.coalesce_cargo(entry['Inventory'])

                self.state['Cargo'].update({self.canonicalise(x['Name']): x['Count'] for x in clean})

            elif event_type == 'CargoTransfer':
                for c in entry['Transfers']:
                    name = self.canonicalise(c['Type'])
                    if c['Direction'] == 'toship':
                        self.state['Cargo'][name] += c['Count']

                    else:
                        # So it's *from* the ship
                        self.state['Cargo'][name] -= c['Count']

            elif event_type == 'ShipLockerMaterials':
                # This event has the current totals, so drop any current data
                self.state['Component'] = defaultdict(int)
                self.state['Consumable'] = defaultdict(int)
                self.state['Item'] = defaultdict(int)
                self.state['Data'] = defaultdict(int)
                # TODO: Really we need a full BackPackMaterials event at the same time.
                #       In lieu of that, empty the backpack.  This will explicitly
                #       be wrong if Cmdr relogs at a Settlement with anything in
                #       backpack.
                #       Still no BackPackMaterials at the same time in 4.0.0.31
                self.state['BackPack']['Component'] = defaultdict(int)
                self.state['BackPack']['Consumable'] = defaultdict(int)
                self.state['BackPack']['Item'] = defaultdict(int)
                self.state['BackPack']['Data'] = defaultdict(int)

                clean_components = self.coalesce_cargo(entry['Components'])
                self.state['Component'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_components}
                )

                clean_consumables = self.coalesce_cargo(entry['Consumables'])
                self.state['Consumable'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_consumables}
                )

                clean_items = self.coalesce_cargo(entry['Items'])
                self.state['Item'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_items}
                )

                clean_data = self.coalesce_cargo(entry['Data'])
                self.state['Data'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_data}
                )

            # Journal v31 implies this was removed before Odyssey launch
            elif event_type == 'BackPackMaterials':
                # alpha4 -
                # Lists the contents of the backpack, eg when disembarking from ship

                # Assume this reflects the current state when written
                self.state['BackPack']['Component'] = defaultdict(int)
                self.state['BackPack']['Consumable'] = defaultdict(int)
                self.state['BackPack']['Item'] = defaultdict(int)
                self.state['BackPack']['Data'] = defaultdict(int)

                clean_components = self.coalesce_cargo(entry['Components'])
                self.state['BackPack']['Component'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_components}
                )

                clean_consumables = self.coalesce_cargo(entry['Consumables'])
                self.state['BackPack']['Consumable'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_consumables}
                )

                clean_items = self.coalesce_cargo(entry['Items'])
                self.state['BackPack']['Item'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_items}
                )

                clean_data = self.coalesce_cargo(entry['Data'])
                self.state['BackPack']['Data'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_data}
                )

            elif event_type in ('BackPack', 'Backpack'):  # WORKAROUND 4.0.0.200: BackPack becomes Backpack
                # TODO: v31 doc says this is`backpack.json` ... but Howard Chalkley
                #       said it's `Backpack.json`
                self.state['BackpackJSON'] = self.state['BackPack']

                # Assume this reflects the current state when written
                self.state['BackPack']['Component'] = defaultdict(int)
                self.state['BackPack']['Consumable'] = defaultdict(int)
                self.state['BackPack']['Item'] = defaultdict(int)
                self.state['BackPack']['Data'] = defaultdict(int)

                clean_components = self.coalesce_cargo(entry['Components'])
                self.state['BackPack']['Component'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_components}
                )

                clean_consumables = self.coalesce_cargo(entry['Consumables'])
                self.state['BackPack']['Consumable'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_consumables}
                )

                clean_items = self.coalesce_cargo(entry['Items'])
                self.state['BackPack']['Item'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_items}
                )

                clean_data = self.coalesce_cargo(entry['Data'])
                self.state['BackPack']['Data'].update(
                    {self.canonicalise(x['Name']): x['Count'] for x in clean_data}
                )

            elif event_type == 'BackpackChange':
                # Changes to Odyssey Backpack contents *other* than from a Transfer
                # See TransferMicroResources event for that.

                if entry.get('Added') is not None:
                    changes = 'Added'

                elif entry.get('Removed') is not None:
                    changes = 'Removed'

                else:
                    logger.warning(f'BackpackChange with neither Added nor Removed: {entry=}')
                    changes = ''

                if changes != '':
                    for c in entry[changes]:
                        category = self.category(c['Type'])
                        name = self.canonicalise(c['Name'])

                        if changes == 'Removed':
                            self.state['BackPack'][category][name] -= c['Count']

                        elif changes == 'Added':
                            self.state['BackPack'][category][name] += c['Count']

                # Paranoia check to see if anything has gone negative.
                # As of Odyssey Alpha Phase 1 Hotfix 2 keeping track of BackPack
                # materials is impossible when used/picked up anyway.
                for c in self.state['BackPack']:
                    for m in self.state['BackPack'][c]:
                        if self.state['BackPack'][c][m] < 0:
                            self.state['BackPack'][c][m] = 0

            elif event_type == 'BuyMicroResources':
                # Buying from a Pioneer Supplies, goes directly to ShipLocker.
                # One event per Item, not an array.
                category = self.category(entry['Category'])
                name = self.canonicalise(entry['Name'])
                self.state[category][name] += entry['Count']

                self.state['Credits'] -= entry.get('Price', 0)

            elif event_type == 'SellMicroResources':
                # Selling to a Bar Tender on-foot.
                self.state['Credits'] += entry.get('Price', 0)
                # One event per whole sale, so it's an array.
                for mr in entry['MicroResources']:
                    category = self.category(mr['Category'])
                    name = self.canonicalise(mr['Name'])
                    self.state[category][name] -= mr['Count']

            elif event_type == 'TradeMicroResources':
                # Trading some MicroResources for another at a Bar Tender
                # 'Offered' is what we traded away
                for offer in entry['Offered']:
                    category = self.category(offer['Category'])
                    name = self.canonicalise(offer['Name'])
                    self.state[category][name] -= offer['Count']

                # For a single item name received
                category = self.category(entry['Category'])
                name = self.canonicalise(entry['Received'])
                self.state[category][name] += entry['Count']

            elif event_type == 'TransferMicroResources':
                # Moving Odyssey MicroResources between ShipLocker and BackPack
                # Backpack dropped as its done in BackpackChange
                #
                #  from: 4.0.0.200 -- Locker(Old|New)Count is now a thing.
                for mr in entry['Transfers']:
                    category = self.category(mr['Category'])
                    name = self.canonicalise(mr['Name'])

                    self.state[category][name] = mr['LockerNewCount']
                    if mr['Direction'] not in ('ToShipLocker', 'ToBackpack'):
                        logger.warning(f'TransferMicroResources with unexpected Direction {mr["Direction"]=}: {mr=}')

                # Paranoia check to see if anything has gone negative.
                # As of Odyssey Alpha Phase 1 Hotfix 2 keeping track of BackPack
                # materials is impossible when used/picked up anyway.
                for c in self.state['BackPack']:
                    for m in self.state['BackPack'][c]:
                        if self.state['BackPack'][c][m] < 0:
                            self.state['BackPack'][c][m] = 0

            elif event_type == 'CollectItems':
                # alpha4
                # When picking up items from the ground
                # Parameters:
                #     • Name
                #     • Type
                #     • OwnerID

                # Handled by BackpackChange
                # for i in self.state['BackPack'][entry['Type']]:
                #     if i == entry['Name']:
                #         self.state['BackPack'][entry['Type']][i] += entry['Count']
                pass

            elif event_type == 'DropItems':
                # alpha4
                # Parameters:
                #     • Name
                #     • Type
                #     • OwnerID
                #     • MissionID
                #     • Count

                # This is handled by BackpackChange.
                # for i in self.state['BackPack'][entry['Type']]:
                #     if i == entry['Name']:
                #         self.state['BackPack'][entry['Type']][i] -= entry['Count']
                #         # Paranoia in case we lost track
                #         if self.state['BackPack'][entry['Type']][i] < 0:
                #             self.state['BackPack'][entry['Type']][i] = 0
                pass

            elif event_type == 'UseConsumable':
                # TODO: XXX: From v31 doc
                #   12.2 BackpackChange
                # This is written when there is any change to the contents of the
                # suit backpack – note this can be written at the same time as other
                # events like UseConsumable

                # In 4.0.0.100 it is observed that:
                #
                #  1. Throw of any grenade type *only* causes a BackpackChange event, no
                #     accompanying 'UseConsumable'.
                #  2. Using an Energy Cell causes both UseConsumable and BackpackChange,
                #     in that order.
                #  3. Medkit acts the same as Energy Cell.
                #
                #  Thus we'll just ignore 'UseConsumable' for now.
                #  for c in self.state['BackPack']['Consumable']:
                #      if c == entry['Name']:
                #          self.state['BackPack']['Consumable'][c] -= 1
                #          # Paranoia in case we lost track
                #          if self.state['BackPack']['Consumable'][c] < 0:
                #              self.state['BackPack']['Consumable'][c] = 0
                pass

            # TODO:
            # <https://forums.frontier.co.uk/threads/575010/>
            # also there's one additional journal event that was missed out from
            # this version of the docs: "SuitLoadout": # when starting on foot, or
            # when disembarking from a ship, with the same info as found in "CreateSuitLoadout"
            elif event_type == 'SuitLoadout':
                suit_slotid, suitloadout_slotid = self.suitloadout_store_from_event(entry)
                if not self.suit_and_loadout_setcurrent(suit_slotid, suitloadout_slotid):
                    logger.error(f"Event was: {entry}")

            elif event_type == 'SwitchSuitLoadout':
                # 4.0.0.101
                #
                # { "timestamp":"2021-05-21T10:39:43Z", "event":"SwitchSuitLoadout",
                #   "SuitID":1700217809818876, "SuitName":"utilitysuit_class1",
                #   "SuitName_Localised":"Maverick Suit", "LoadoutID":4293000002,
                #   "LoadoutName":"K/P", "Modules":[ { "SlotName":"PrimaryWeapon1",
                #   "SuitModuleID":1700217863661544,
                #   "ModuleName":"wpn_m_assaultrifle_kinetic_fauto",
                #   "ModuleName_Localised":"Karma AR-50" },
                #   { "SlotName":"SecondaryWeapon", "SuitModuleID":1700216180036986,
                #   "ModuleName":"wpn_s_pistol_plasma_charged",
                #   "ModuleName_Localised":"Manticore Tormentor" } ] }
                #
                suitid, suitloadout_slotid = self.suitloadout_store_from_event(entry)
                if not self.suit_and_loadout_setcurrent(suitid, suitloadout_slotid):
                    logger.error(f"Event was: {entry}")

            elif event_type == 'CreateSuitLoadout':
                # 4.0.0.101
                #
                # { "timestamp":"2021-05-21T11:13:15Z", "event":"CreateSuitLoadout", "SuitID":1700216165682989,
                # "SuitName":"tacticalsuit_class1", "SuitName_Localised":"Dominator Suit", "LoadoutID":4293000004,
                # "LoadoutName":"P/P/K", "Modules":[ { "SlotName":"PrimaryWeapon1", "SuitModuleID":1700216182854765,
                # "ModuleName":"wpn_m_assaultrifle_plasma_fauto", "ModuleName_Localised":"Manticore Oppressor" },
                # { "SlotName":"PrimaryWeapon2", "SuitModuleID":1700216190363340,
                # "ModuleName":"wpn_m_shotgun_plasma_doublebarrel", "ModuleName_Localised":"Manticore Intimidator" },
                # { "SlotName":"SecondaryWeapon", "SuitModuleID":1700217869872834,
                # "ModuleName":"wpn_s_pistol_kinetic_sauto", "ModuleName_Localised":"Karma P-15" } ] }
                #
                suitid, suitloadout_slotid = self.suitloadout_store_from_event(entry)
                # Creation doesn't mean equipping it
                #  if not self.suit_and_loadout_setcurrent(suitid, suitloadout_slotid):
                #      logger.error(f"Event was: {entry}")

            elif event_type == 'DeleteSuitLoadout':
                # alpha4:
                # { "timestamp":"2021-04-29T10:32:27Z", "event":"DeleteSuitLoadout", "SuitID":1698365752966423,
                # "SuitName":"explorationsuit_class1", "SuitName_Localised":"Artemis Suit", "LoadoutID":4293000003,
                # "LoadoutName":"Loadout 1" }

                if self.state['SuitLoadouts']:
                    loadout_id = self.suit_loadout_id_from_loadoutid(entry['LoadoutID'])
                    try:
                        self.state['SuitLoadouts'].pop(f'{loadout_id}')

                    except KeyError:
                        # This should no longer happen, as we're now handling CreateSuitLoadout properly
                        logger.debug(f"loadout slot id {loadout_id} doesn't exist, not in last CAPI pull ?")

            elif event_type == 'RenameSuitLoadout':
                # alpha4
                # Parameters:
                #     • SuitID
                #     • SuitName
                #     • LoadoutID
                #     • Loadoutname
                # alpha4:
                # { "timestamp":"2021-04-29T10:35:55Z", "event":"RenameSuitLoadout", "SuitID":1698365752966423,
                # "SuitName":"explorationsuit_class1", "SuitName_Localised":"Artemis Suit", "LoadoutID":4293000003,
                # "LoadoutName":"Art L/K" }
                if self.state['SuitLoadouts']:
                    loadout_id = self.suit_loadout_id_from_loadoutid(entry['LoadoutID'])
                    try:
                        self.state['SuitLoadouts'][loadout_id]['name'] = entry['LoadoutName']

                    except KeyError:
                        logger.debug(f"loadout slot id {loadout_id} doesn't exist, not in last CAPI pull ?")

            elif event_type == 'BuySuit':
                # alpha4 :
                # { "timestamp":"2021-04-29T09:03:37Z", "event":"BuySuit", "Name":"UtilitySuit_Class1",
                # "Name_Localised":"Maverick Suit", "Price":150000, "SuitID":1698364934364699 }
                loc_name = entry.get('Name_Localised', entry['Name'])
                self.state['Suits'][entry['SuitID']] = {
                    'name':      entry['Name'],
                    'locName':   loc_name,
                    'edmcName':  self.suit_sane_name(loc_name),
                    'id':        None,  # Is this an FDev ID for suit type ?
                    'suitId':    entry['SuitID'],
                    'slots':     [],
                }

                # update credits
                if price := entry.get('Price') is None:
                    logger.error(f"BuySuit didn't contain Price: {entry}")

                else:
                    self.state['Credits'] -= price

            elif event_type == 'SellSuit':
                # Remove from known suits
                # As of Odyssey Alpha Phase 2, Hotfix 5 (4.0.0.13) this isn't possible as this event
                # doesn't contain the specific suit ID as per CAPI `suits` dict.
                # alpha4
                # This event is logged when a player sells a flight suit
                #
                # Parameters:
                #     • Name
                #     • Price
                #     • SuitID
                # alpha4:
                # { "timestamp":"2021-04-29T09:15:51Z", "event":"SellSuit", "SuitID":1698364937435505,
                # "Name":"explorationsuit_class1", "Name_Localised":"Artemis Suit", "Price":90000 }
                if self.state['Suits']:
                    try:
                        self.state['Suits'].pop(entry['SuitID'])

                    except KeyError:
                        logger.debug(f"SellSuit for a suit we didn't know about? {entry['SuitID']}")

                    # update credits total
                    if price := entry.get('Price') is None:
                        logger.error(f"SellSuit didn't contain Price: {entry}")

                    else:
                        self.state['Credits'] += price

            elif event_type == 'UpgradeSuit':
                # alpha4
                # This event is logged when the player upgrades their flight suit
                #
                # Parameters:
                #     • Name
                #     • SuitID
                #     • Class
                #     • Cost
                # TODO: Update self.state['Suits'] when we have an example to work from
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'LoadoutEquipModule':
                # alpha4:
                # { "timestamp":"2021-04-29T11:11:13Z", "event":"LoadoutEquipModule", "LoadoutName":"Dom L/K/K",
                # "SuitID":1698364940285172, "SuitName":"tacticalsuit_class1", "SuitName_Localised":"Dominator Suit",
                # "LoadoutID":4293000001, "SlotName":"PrimaryWeapon2", "ModuleName":"wpn_m_assaultrifle_laser_fauto",
                # "ModuleName_Localised":"TK Aphelion", "SuitModuleID":1698372938719590 }
                if self.state['SuitLoadouts']:
                    loadout_id = self.suit_loadout_id_from_loadoutid(entry['LoadoutID'])
                    try:
                        self.state['SuitLoadouts'][loadout_id]['slots'][entry['SlotName']] = {
                            'name':           entry['ModuleName'],
                            'locName':        entry.get('ModuleName_Localised', entry['ModuleName']),
                            'id':             None,
                            'weaponrackId':   entry['SuitModuleID'],
                            'locDescription': '',
                        }

                    except KeyError:
                        logger.error(f"LoadoutEquipModule: {entry}")

            elif event_type == 'LoadoutRemoveModule':
                # alpha4 - triggers if selecting an already-equipped weapon into a different slot
                # { "timestamp":"2021-04-29T11:11:13Z", "event":"LoadoutRemoveModule", "LoadoutName":"Dom L/K/K",
                # "SuitID":1698364940285172, "SuitName":"tacticalsuit_class1", "SuitName_Localised":"Dominator Suit",
                # "LoadoutID":4293000001, "SlotName":"PrimaryWeapon1", "ModuleName":"wpn_m_assaultrifle_laser_fauto",
                # "ModuleName_Localised":"TK Aphelion", "SuitModuleID":1698372938719590 }
                if self.state['SuitLoadouts']:
                    loadout_id = self.suit_loadout_id_from_loadoutid(entry['LoadoutID'])
                    try:
                        self.state['SuitLoadouts'][loadout_id]['slots'].pop(entry['SlotName'])

                    except KeyError:
                        logger.error(f"LoadoutRemoveModule: {entry}")

            elif event_type == 'BuyWeapon':
                # alpha4
                # { "timestamp":"2021-04-29T11:10:51Z", "event":"BuyWeapon", "Name":"Wpn_M_AssaultRifle_Laser_FAuto",
                # "Name_Localised":"TK Aphelion", "Price":125000, "SuitModuleID":1698372938719590 }
                # update credits
                if price := entry.get('Price') is None:
                    logger.error(f"BuyWeapon didn't contain Price: {entry}")

                else:
                    self.state['Credits'] -= price

            elif event_type == 'SellWeapon':
                # We're not actually keeping track of all owned weapons, only those in
                # Suit Loadouts.
                # alpha4:
                # { "timestamp":"2021-04-29T10:50:34Z", "event":"SellWeapon", "Name":"wpn_m_assaultrifle_laser_fauto",
                # "Name_Localised":"TK Aphelion", "Price":75000, "SuitModuleID":1698364962722310 }

                # We need to look over all Suit Loadouts for ones that used this specific weapon
                # and update them to entirely empty that slot.
                for sl in self.state['SuitLoadouts']:
                    for w in self.state['SuitLoadouts'][sl]['slots']:
                        if self.state['SuitLoadouts'][sl]['slots'][w]['weaponrackId'] == entry['SuitModuleID']:
                            self.state['SuitLoadouts'][sl]['slots'].pop(w)
                            # We've changed the dict, so iteration breaks, but also the weapon
                            # could only possibly have been here once.
                            break

                # Update credits total
                if price := entry.get('Price') is None:
                    logger.error(f"SellWeapon didn't contain Price: {entry}")

                else:
                    self.state['Credits'] += price

            elif event_type == 'UpgradeWeapon':
                # We're not actually keeping track of all owned weapons, only those in
                # Suit Loadouts.
                # alpha4 - credits?  Shouldn't cost any!
                pass

            elif event_type == 'ScanOrganic':
                # Nothing of interest to our state.
                pass

            elif event_type == 'SellOrganicData':
                for bd in entry['BioData']:
                    self.state['Credits'] += bd.get('Value', 0) + bd.get('Bonus', 0)

            elif event_type == 'BookDropship':
                self.state['Credits'] -= entry.get('Cost', 0)
                # Technically we *might* now not be OnFoot.
                # The problem is that this event is recorded both for signing up for
                # an on-foot CZ, and when you use the Dropship to return after the
                # CZ completes.
                #
                # In the first case we're still in-station and thus still on-foot.
                #
                # In the second case we should instantly be in the Dropship and thus
                # not still on-foot, BUT it doesn't really matter as the next significant
                # event is going to be Disembark to on-foot anyway.

            elif event_type == 'BookTaxi':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'CancelDropship':
                self.state['Credits'] += entry.get('Refund', 0)

            elif event_type == 'CancelTaxi':
                self.state['Credits'] += entry.get('Refund', 0)

            elif event_type in ('CollectCargo', 'MarketBuy', 'BuyDrones', 'MiningRefined'):
                commodity = self.canonicalise(entry['Type'])
                self.state['Cargo'][commodity] += entry.get('Count', 1)

                if event_type == 'BuyDrones':
                    self.state['Credits'] -= entry.get('TotalCost', 0)

                elif event_type == 'MarketBuy':
                    self.state['Credits'] -= entry.get('TotalCost', 0)

            elif event_type in ('EjectCargo', 'MarketSell', 'SellDrones'):
                commodity = self.canonicalise(entry['Type'])
                cargo = self.state['Cargo']
                cargo[commodity] -= entry.get('Count', 1)
                if cargo[commodity] <= 0:
                    cargo.pop(commodity)

                if event_type == 'MarketSell':
                    self.state['Credits'] += entry.get('TotalSale', 0)

                elif event_type == 'SellDrones':
                    self.state['Credits'] += entry.get('TotalSale', 0)

            elif event_type == 'SearchAndRescue':
                for item in entry.get('Items', []):
                    commodity = self.canonicalise(item['Name'])
                    cargo = self.state['Cargo']
                    cargo[commodity] -= item.get('Count', 1)
                    if cargo[commodity] <= 0:
                        cargo.pop(commodity)

            elif event_type == 'Materials':
                for category in ('Raw', 'Manufactured', 'Encoded'):
                    self.state[category] = defaultdict(int)
                    self.state[category].update({
                        self.canonicalise(x['Name']): x['Count'] for x in entry.get(category, [])
                    })

            elif event_type == 'MaterialCollected':
                material = self.canonicalise(entry['Name'])
                self.state[entry['Category']][material] += entry['Count']

            elif event_type in ('MaterialDiscarded', 'ScientificResearch'):
                material = self.canonicalise(entry['Name'])
                state_category = self.state[entry['Category']]
                state_category[material] -= entry['Count']
                if state_category[material] <= 0:
                    state_category.pop(material)

            elif event_type == 'Synthesis':
                for category in ('Raw', 'Manufactured', 'Encoded'):
                    for x in entry['Materials']:
                        material = self.canonicalise(x['Name'])
                        if material in self.state[category]:
                            self.state[category][material] -= x['Count']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)

            elif event_type == 'MaterialTrade':
                category = self.category(entry['Paid']['Category'])
                state_category = self.state[category]
                paid = entry['Paid']
                received = entry['Received']

                state_category[paid['Material']] -= paid['Quantity']
                if state_category[paid['Material']] <= 0:
                    state_category.pop(paid['Material'])

                category = self.category(received['Category'])
                state_category[received['Material']] += received['Quantity']

            elif event_type == 'EngineerCraft' or (
                event_type == 'EngineerLegacyConvert' and not entry.get('IsPreview')
            ):

                for category in ('Raw', 'Manufactured', 'Encoded'):
                    for x in entry.get('Ingredients', []):
                        material = self.canonicalise(x['Name'])
                        if material in self.state[category]:
                            self.state[category][material] -= x['Count']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)

                module = self.state['Modules'][entry['Slot']]
                assert(module['Item'] == self.canonicalise(entry['Module']))
                module['Engineering'] = {
                    'Engineer':      entry['Engineer'],
                    'EngineerID':    entry['EngineerID'],
                    'BlueprintName': entry['BlueprintName'],
                    'BlueprintID':   entry['BlueprintID'],
                    'Level':         entry['Level'],
                    'Quality':       entry['Quality'],
                    'Modifiers':     entry['Modifiers'],
                }

                if 'ExperimentalEffect' in entry:
                    module['Engineering']['ExperimentalEffect'] = entry['ExperimentalEffect']
                    module['Engineering']['ExperimentalEffect_Localised'] = entry['ExperimentalEffect_Localised']

                else:
                    module['Engineering'].pop('ExperimentalEffect', None)
                    module['Engineering'].pop('ExperimentalEffect_Localised', None)

            elif event_type == 'MissionCompleted':
                self.state['Credits'] += entry.get('Reward', 0)

                for reward in entry.get('CommodityReward', []):
                    commodity = self.canonicalise(reward['Name'])
                    self.state['Cargo'][commodity] += reward.get('Count', 1)

                for reward in entry.get('MaterialsReward', []):
                    if 'Category' in reward:  # Category not present in E:D 3.0
                        category = self.category(reward['Category'])
                        material = self.canonicalise(reward['Name'])
                        self.state[category][material] += reward.get('Count', 1)

            elif event_type == 'EngineerContribution':
                commodity = self.canonicalise(entry.get('Commodity'))
                if commodity:
                    self.state['Cargo'][commodity] -= entry['Quantity']
                    if self.state['Cargo'][commodity] <= 0:
                        self.state['Cargo'].pop(commodity)

                material = self.canonicalise(entry.get('Material'))
                if material:
                    for category in ('Raw', 'Manufactured', 'Encoded'):
                        if material in self.state[category]:
                            self.state[category][material] -= entry['Quantity']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)

            elif event_type == 'TechnologyBroker':
                for thing in entry.get('Ingredients', []):  # 3.01
                    for category in ('Cargo', 'Raw', 'Manufactured', 'Encoded'):
                        item = self.canonicalise(thing['Name'])
                        if item in self.state[category]:
                            self.state[category][item] -= thing['Count']
                            if self.state[category][item] <= 0:
                                self.state[category].pop(item)

                for thing in entry.get('Commodities', []):  # 3.02
                    commodity = self.canonicalise(thing['Name'])
                    self.state['Cargo'][commodity] -= thing['Count']
                    if self.state['Cargo'][commodity] <= 0:
                        self.state['Cargo'].pop(commodity)

                for thing in entry.get('Materials', []):  # 3.02
                    material = self.canonicalise(thing['Name'])
                    category = thing['Category']
                    self.state[category][material] -= thing['Count']
                    if self.state[category][material] <= 0:
                        self.state[category].pop(material)

            elif event_type == 'JoinACrew':
                self.state['Captain'] = entry['Captain']
                self.state['Role'] = 'Idle'
                self.planet = None
                self.system = None
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None
                self.state['OnFoot'] = False

            elif event_type == 'ChangeCrewRole':
                self.state['Role'] = entry['Role']

            elif event_type == 'QuitACrew':
                self.state['Captain'] = None
                self.state['Role'] = None
                self.planet = None
                self.system = None
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None
                # TODO: on_foot: Will we get an event after this to know ?

            elif event_type == 'Friends':
                if entry['Status'] in ('Online', 'Added'):
                    self.state['Friends'].add(entry['Name'])

                else:
                    self.state['Friends'].discard(entry['Name'])

            # Try to keep Credits total updated
            elif event_type in ('MultiSellExplorationData', 'SellExplorationData'):
                self.state['Credits'] += entry.get('TotalEarnings', 0)

            elif event_type == 'BuyExplorationData':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'BuyTradeData':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'BuyAmmo':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'CommunityGoalReward':
                self.state['Credits'] += entry.get('Reward', 0)

            elif event_type == 'CrewHire':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'FetchRemoteModule':
                self.state['Credits'] -= entry.get('TransferCost', 0)

            elif event_type == 'MissionAbandoned':
                # Is this paid at this point, or just a fine to pay later ?
                # self.state['Credits'] -= entry.get('Fine', 0)
                pass

            elif event_type in ('PayBounties', 'PayFines', 'PayLegacyFines'):
                self.state['Credits'] -= entry.get('Amount', 0)

            elif event_type == 'RedeemVoucher':
                self.state['Credits'] += entry.get('Amount', 0)

            elif event_type in ('RefuelAll', 'RefuelPartial', 'Repair', 'RepairAll', 'RestockVehicle'):
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'SellShipOnRebuy':
                self.state['Credits'] += entry.get('ShipPrice', 0)

            elif event_type == 'ShipyardSell':
                self.state['Credits'] += entry.get('ShipPrice', 0)

            elif event_type == 'ShipyardTransfer':
                self.state['Credits'] -= entry.get('TransferPrice', 0)

            elif event_type == 'PowerplayFastTrack':
                self.state['Credits'] -= entry.get('Cost', 0)

            elif event_type == 'PowerplaySalary':
                self.state['Credits'] += entry.get('Amount', 0)

            elif event_type == 'SquadronCreated':
                # v30 docs don't actually say anything about credits cost
                pass

            elif event_type == 'CarrierBuy':
                self.state['Credits'] -= entry.get('Price', 0)

            elif event_type == 'CarrierBankTransfer':
                if (newbal := entry.get('PlayerBalance')):
                    self.state['Credits'] = newbal

            elif event_type == 'CarrierDecommission':
                # v30 doc says nothing about citing the refund amount
                pass

            elif event_type == 'NpcCrewPaidWage':
                self.state['Credits'] -= entry.get('Amount', 0)

            elif event_type == 'Resurrect':
                self.state['Credits'] -= entry.get('Cost', 0)

            return entry

        except Exception as ex:
            logger.debug(f'Invalid journal entry:\n{line!r}\n', exc_info=ex)
            return {'event': None}

    def suit_sane_name(self, name: str) -> str:
        """
        Given an input suit name return the best 'sane' name we can.

        AS of 4.0.0.102 the Journal events are fine for a Grade 1 suit, but
        anything above that has broken SuitName_Localised strings, e.g.
        $TacticalSuit_Class1_Name;

        Also, if there isn't a SuitName_Localised value at all we'll use the
        plain SuitName which can be, e.g. tacticalsuit_class3

        If the names were correct we would get 'Dominator Suit' in this instance,
        however what we want to return is, e.g. 'Dominator'.  As that's both
        sufficient for disambiguation and more succinct.

        :param name: Name that could be in any of the forms.
        :return: Our sane version of this suit's name.
        """
        # WORKAROUND 4.0.0.200 | 2021-05-27: Suit names above Grade 1 aren't localised
        #    properly by Frontier, so we do it ourselves.
        # Stage 1: Is it in `$<type>_Class<X>_Name;` form ?
        if m := re.fullmatch(r'(?i)^\$([^_]+)_Class([0-9]+)_Name;$', name):
            n, c = m.group(1, 2)
            name = n

        # Stage 2: Is it in `<type>_class<x>` form ?
        elif m := re.fullmatch(r'(?i)^([^_]+)_class([0-9]+)$', name):
            n, c = m.group(1, 2)
            name = n

        # Now turn either of those into a '<type> Suit' (modulo language) form
        if loc_lookup := edmc_suit_symbol_localised.get(self.state['GameLanguage']):
            name = loc_lookup.get(name.lower(), name)
        # WORKAROUND END

        # Finally, map that to a form without the verbose ' Suit' on the end
        name = edmc_suit_shortnames.get(name, name)

        return name

    def suitloadout_store_from_event(self, entry) -> Tuple[int, int]:
        """
        Store Suit and SuitLoadout data from a journal event.

        Also use set currently in-use instances of them as being as per this
        event.

        :param entry: Journal entry - 'SwitchSuitLoadout' or 'SuitLoadout'
        :return Tuple[suit_slotid, suitloadout_slotid]: The IDs we set data for.
        """
        # This is the full ID from Frontier, it's not a sparse array slot id
        suitid = entry['SuitID']

        # Check if this looks like a suit we already have stored, so as
        # to avoid 'bad' Journal localised names.
        suit = self.state['Suits'].get(f"{suitid}", None)
        if suit is None:
            # Initial suit containing just the data that is then embedded in
            # the loadout

            # TODO: Attempt to map SuitName_Localised to something sane, if it
            #       isn't already.
            suitname = entry.get('SuitName_Localised', entry['SuitName'])
            edmc_suitname = self.suit_sane_name(suitname)
            suit = {
                'edmcName': edmc_suitname,
                'locName':  suitname,
                'suitId':   entry['SuitID'],
                'name':     entry['SuitName'],
            }

        suitloadout_slotid = self.suit_loadout_id_from_loadoutid(entry['LoadoutID'])
        # Make the new loadout, in the CAPI format
        new_loadout = {
            'loadoutSlotId': suitloadout_slotid,
            'suit':          suit,
            'name':          entry['LoadoutName'],
            'slots':         self.suit_loadout_slots_array_to_dict(entry['Modules']),
        }
        # Assign this loadout into our state
        self.state['SuitLoadouts'][f"{suitloadout_slotid}"] = new_loadout

        # Now add in the extra fields for new_suit to be a 'full' Suit structure
        suit['id'] = suit.get('id')  # Not available in 4.0.0.100 journal event
        suit['slots'] = new_loadout['slots']  # 'slots', not 'Modules', to match CAPI
        # Ensure the suit is in self.state['Suits']
        self.state['Suits'][f"{suitid}"] = suit

        return suitid, suitloadout_slotid

    def suit_and_loadout_setcurrent(self, suitid: int, suitloadout_slotid: int) -> bool:
        """
        Set self.state for SuitCurrent and SuitLoadoutCurrent as requested.

        If the specified slots are unknown we abort and return False, else
        return True.

        :param suitid: Numeric ID of the suit.
        :param suitloadout_slotid: Numeric ID of the slot for the suit loadout.
        :return: True if we could do this, False if not.
        """
        str_suitid = f"{suitid}"
        str_suitloadoutid = f"{suitloadout_slotid}"

        if (self.state['Suits'].get(str_suitid, False)
                and self.state['SuitLoadouts'].get(str_suitloadoutid, False)):
            self.state['SuitCurrent'] = self.state['Suits'][str_suitid]
            self.state['SuitLoadoutCurrent'] = self.state['SuitLoadouts'][str_suitloadoutid]
            return True

        logger.error(f"Tried to set a suit and suitloadout where we didn't know about both: {suitid=}, "
                     f"{str_suitloadoutid=}")
        return False

    # TODO: *This* will need refactoring and a proper validation infrastructure
    #       designed for this in the future.  This is a bandaid for a known issue.
    def event_valid_engineerprogress(self, entry) -> bool:  # noqa: CCR001 C901
        """
        Check an `EngineerProgress` Journal event for validity.

        :param entry: Journal event dict
        :return: True if passes validation, else False.
        """
        # The event should have at least one of these
        if 'Engineers' not in entry and 'Progress' not in entry:
            logger.warning(f"EngineerProgress has neither 'Engineers' nor 'Progress': {entry=}")
            return False

        # But not both of them
        if 'Engineers' in entry and 'Progress' in entry:
            logger.warning(f"EngineerProgress has BOTH 'Engineers' and 'Progress': {entry=}")
            return False

        if 'Engineers' in entry:
            # 'Engineers' version should have a list as value
            if not isinstance(entry['Engineers'], list):
                logger.warning(f"EngineerProgress 'Engineers' is not a list: {entry=}")
                return False

            # It should have at least one entry?  This might still be valid ?
            if len(entry['Engineers']) < 1:
                logger.warning(f"EngineerProgress 'Engineers' list is empty ?: {entry=}")
                # TODO: As this might be valid, we might want to only log
                return False

            # And that list should have all of these keys
            for e in entry['Engineers']:
                for f in ('Engineer', 'EngineerID', 'Rank', 'Progress', 'RankProgress'):
                    if f not in e:
                        # For some Progress there's no Rank/RankProgress yet
                        if f in ('Rank', 'RankProgress'):
                            if (progress := e.get('Progress', None)) is not None:
                                if progress in ('Invited', 'Known'):
                                    continue

                        logger.warning(f"Engineer entry without '{f}' key: {e=} in {entry=}")
                        return False

        if 'Progress' in entry:
            # Progress is only a single Engineer, so it's not an array
            # { "timestamp":"2021-05-24T17:57:52Z",
            #   "event":"EngineerProgress",
            #   "Engineer":"Felicity Farseer",
            #   "EngineerID":300100,
            #   "Progress":"Invited" }
            for f in ('Engineer', 'EngineerID', 'Rank', 'Progress', 'RankProgress'):
                if f not in entry:
                    # For some Progress there's no Rank/RankProgress yet
                    if f in ('Rank', 'RankProgress'):
                        if (progress := entry.get('Progress', None)) is not None:
                            if progress in ('Invited', 'Known'):
                                continue

                    logger.warning(f"Progress event without '{f}' key: {entry=}")
                    return False

        return True

    def suit_loadout_id_from_loadoutid(self, journal_loadoutid: int) -> int:
        """
        Determine the CAPI-oriented numeric slot id for a Suit Loadout.

        :param journal_loadoutid: Journal `LoadoutID` integer value.
        :return:
        """
        # Observed LoadoutID in SwitchSuitLoadout events are, e.g.
        # 4293000005 for CAPI slot 5.
        # This *might* actually be "lower 6 bits", but maybe it's not.
        slotid = journal_loadoutid - 4293000000
        return slotid

    def canonicalise(self, item: Optional[str]) -> str:
        """
        Produce canonical name for a ship module.

        Commodities, Modules and Ships can appear in different forms e.g. "$HNShockMount_Name;", "HNShockMount",
        and "hnshockmount", "$int_cargorack_size6_class1_name;" and "Int_CargoRack_Size6_Class1",
        "python" and "Python", etc.
        This returns a simple lowercased name e.g. 'hnshockmount', 'int_cargorack_size6_class1', 'python', etc

        :param item: str - 'Found' name of the item.
        :return: str - The canonical name.
        """
        if not item:
            return ''

        item = item.lower()
        match = self._RE_CANONICALISE.match(item)

        if match:
            return match.group(1)

        return item

    def category(self, item: str) -> str:
        """
        Determine the category of an item.

        :param item: str - The item in question.
        :return: str - The category for this item.
        """
        match = self._RE_CATEGORY.match(item)

        if match:
            return match.group(1).capitalize()

        return item.capitalize()

    def game_running(self) -> bool:  # noqa: CCR001
        """
        Determine if the game is currently running.

        TODO: Implement on Linux

        :return: bool - True if the game is running.
        """
        if platform == 'darwin':
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.bundleIdentifier() == 'uk.co.frontier.EliteDangerous':
                    return True

        elif platform == 'win32':
            def WindowTitle(h):  # noqa: N802 # type: ignore
                if h:
                    length = GetWindowTextLength(h) + 1
                    buf = ctypes.create_unicode_buffer(length)
                    if GetWindowText(h, buf, length):
                        return buf.value
                return None

            def callback(hWnd, lParam):  # noqa: N803
                name = WindowTitle(hWnd)
                if name and name.startswith('Elite - Dangerous'):
                    handle = GetProcessHandleFromHwnd(hWnd)
                    if handle:  # If GetProcessHandleFromHwnd succeeds then the app is already running as this user
                        CloseHandle(handle)
                        return False  # stop enumeration

                return True

            return not EnumWindows(EnumWindowsProc(callback), 0)

        return False

    def ship(self, timestamped=True) -> Optional[MutableMapping[str, Any]]:
        """
        Produce a subset of data for the current ship.

        Return a subset of the received data describing the current ship as a Loadout event.

        :param timestamped: bool - Whether to add a 'timestamp' member.
        :return: dict
        """
        if not self.state['Modules']:
            return None

        standard_order = (
            'ShipCockpit', 'CargoHatch', 'Armour', 'PowerPlant', 'MainEngines', 'FrameShiftDrive', 'LifeSupport',
            'PowerDistributor', 'Radar', 'FuelTank'
        )

        d: MutableMapping[str, Any] = OrderedDict()
        if timestamped:
            d['timestamp'] = strftime('%Y-%m-%dT%H:%M:%SZ', gmtime())

        d['event'] = 'Loadout'
        d['Ship'] = self.state['ShipType']
        d['ShipID'] = self.state['ShipID']

        if self.state['ShipName']:
            d['ShipName'] = self.state['ShipName']

        if self.state['ShipIdent']:
            d['ShipIdent'] = self.state['ShipIdent']

        # sort modules by slot - hardpoints, standard, internal
        d['Modules'] = []

        for slot in sorted(
            self.state['Modules'],
            key=lambda x: (
                'Hardpoint' not in x,
                len(standard_order) if x not in standard_order else standard_order.index(x),
                'Slot' not in x,
                x
            )
        ):

            module = dict(self.state['Modules'][slot])
            module.pop('Health', None)
            module.pop('Value', None)
            d['Modules'].append(module)

        return d

    def export_ship(self, filename=None) -> None:  # noqa: C901, CCR001
        """
        Export ship loadout as a Loadout event.

        Writes either to the specified filename or to a formatted filename based on
        the ship name and a date+timestamp.

        :param filename: Name of file to write to, if not default.
        """
        # TODO(A_D): Some type checking has been disabled in here due to config.get getting weird outputs
        string = json.dumps(self.ship(False), ensure_ascii=False, indent=2, separators=(',', ': '))  # pretty print
        if filename:
            try:
                with open(filename, 'wt', encoding='utf-8') as h:
                    h.write(string)

            except UnicodeError:
                logger.exception("UnicodeError writing ship loadout to specified filename with utf-8 encoding"
                                 ", trying without..."
                                 )

                try:
                    with open(filename, 'wt') as h:
                        h.write(string)

                except OSError:
                    logger.exception("OSError writing ship loadout to specified filename with default encoding"
                                     ", aborting."
                                     )

            except OSError:
                logger.exception("OSError writing ship loadout to specified filename with utf-8 encoding, aborting.")

            return

        ship = util_ships.ship_file_name(self.state['ShipName'], self.state['ShipType'])
        regexp = re.compile(re.escape(ship) + r'\.\d{4}\-\d\d\-\d\dT\d\d\.\d\d\.\d\d\.txt')
        oldfiles = sorted((x for x in listdir(config.get_str('outdir')) if regexp.match(x)))  # type: ignore
        if oldfiles:
            try:
                with open(join(config.get_str('outdir'), oldfiles[-1]), 'r', encoding='utf-8') as h:  # type: ignore
                    if h.read() == string:
                        return  # same as last time - don't write

            except UnicodeError:
                logger.exception("UnicodeError reading old ship loadout with utf-8 encoding, trying without...")
                try:
                    with open(join(config.get_str('outdir'), oldfiles[-1]), 'r') as h:  # type: ignore
                        if h.read() == string:
                            return  # same as last time - don't write

                except OSError:
                    logger.exception("OSError reading old ship loadout default encoding.")

                except ValueError:
                    # User was on $OtherEncoding, updated windows to be sane and use utf8 everywhere, thus
                    # the above open() fails, likely with a UnicodeDecodeError, which subclasses UnicodeError which
                    # subclasses ValueError, this catches ValueError _instead_ of UnicodeDecodeError just to be sure
                    # that if some other encoding error crops up we grab it too.
                    logger.exception('ValueError when reading old ship loadout default encoding')

            except OSError:
                logger.exception("OSError reading old ship loadout with default encoding")

        # Write
        ts = strftime('%Y-%m-%dT%H.%M.%S', localtime(time()))
        filename = join(  # type: ignore
            config.get_str('outdir'), f'{ship}.{ts}.txt'
        )

        try:
            with open(filename, 'wt', encoding='utf-8') as h:
                h.write(string)

        except UnicodeError:
            logger.exception("UnicodeError writing ship loadout to new filename with utf-8 encoding, trying without...")
            try:
                with open(filename, 'wt') as h:
                    h.write(string)

            except OSError:
                logger.exception("OSError writing ship loadout to new filename with default encoding, aborting.")

        except OSError:
            logger.exception("OSError writing ship loadout to new filename with utf-8 encoding, aborting.")

    def coalesce_cargo(self, raw_cargo: List[MutableMapping[str, Any]]) -> List[MutableMapping[str, Any]]:
        """
        Coalesce multiple entries of the same cargo into one.

        This exists due to the fact that a user can accept multiple missions that all require the same cargo. On the ED
        side, this is represented as multiple entries in the `Inventory` List with the same names etc. Just a differing
        MissionID. We (as in EDMC Core) dont want to support the multiple mission IDs, but DO want to have correct cargo
        counts. Thus, we reduce all existing cargo down to one total.
        >>> test = [
        ...     { "Name":"basicmedicines", "Name_Localised":"BM", "MissionID":684359162, "Count":147, "Stolen":0 },
        ...     { "Name":"survivalequipment", "Name_Localised":"SE", "MissionID":684358939, "Count":147, "Stolen":0 },
        ...     { "Name":"survivalequipment", "Name_Localised":"SE", "MissionID":684359344, "Count":36, "Stolen":0 }
        ... ]
        >>> EDLogs().coalesce_cargo(test) # doctest: +NORMALIZE_WHITESPACE
        [{'Name': 'basicmedicines', 'Name_Localised': 'BM', 'MissionID': 684359162, 'Count': 147, 'Stolen': 0},
        {'Name': 'survivalequipment', 'Name_Localised': 'SE', 'MissionID': 684358939, 'Count': 183, 'Stolen': 0}]

        :param raw_cargo: Raw cargo data (usually from Cargo.json)
        :return: Coalesced data
        """
        # self.state['Cargo'].update({self.canonicalise(x['Name']): x['Count'] for x in entry['Inventory']})
        out: List[MutableMapping[str, Any]] = []
        for inventory_item in raw_cargo:
            if not any(self.canonicalise(x['Name']) == self.canonicalise(inventory_item['Name']) for x in out):
                out.append(dict(inventory_item))
                continue

            # We've seen this before, update that count
            x = list(filter(lambda x: self.canonicalise(x['Name']) == self.canonicalise(inventory_item['Name']), out))

            if len(x) != 1:
                logger.debug(f'Unexpected number of items: {len(x)} where 1 was expected. {x}')

            x[0]['Count'] += inventory_item['Count']

        return out

    def suit_loadout_slots_array_to_dict(self, loadout: dict) -> dict:
        """
        Return a CAPI-style Suit loadout from a Journal style dict.

        :param loadout: e.g. Journal 'CreateSuitLoadout'->'Modules'.
        :return: CAPI-style dict for a suit loadout.
        """
        loadout_slots = {x['SlotName']: x for x in loadout}
        slots = {}
        for s in ('PrimaryWeapon1', 'PrimaryWeapon2', 'SecondaryWeapon'):
            if loadout_slots.get(s) is None:
                continue

            slots[s] = {
                'name':           loadout_slots[s]['ModuleName'],
                'id':             None,  # FDevID ?
                'weaponrackId':   loadout_slots[s]['SuitModuleID'],
                'locName':        loadout_slots[s].get('ModuleName_Localised', loadout_slots[s]['ModuleName']),
                'locDescription': '',
            }

        return slots


# singleton
monitor = EDLogs()
