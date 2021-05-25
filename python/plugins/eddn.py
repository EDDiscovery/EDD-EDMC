"""Handle exporting data to EDDN."""

import itertools
import json
import pathlib
import re
import sys
import tkinter as tk
from collections import OrderedDict
from os import SEEK_SET
from os.path import join
from platform import system
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Mapping, MutableMapping, Optional
from typing import OrderedDict as OrderedDictT
from typing import TextIO, Tuple

import requests

import killswitch
import myNotebook as nb  # noqa: N813
import plug
from config import applongname, appversion_nobuild, config
from EDMCLogging import get_main_logger
from monitor import monitor
from myNotebook import Frame
from prefs import prefsVersion
from ttkHyperlinkLabel import HyperlinkLabel

if sys.platform != 'win32':
    from fcntl import LOCK_EX, LOCK_NB, lockf


if TYPE_CHECKING:
    def _(x: str) -> str:
        return x

logger = get_main_logger()


class This:
    """Holds module globals."""

    def __init__(self):
        # Track if we're on foot
        self.on_foot = False

        # Running under Odyssey?
        self.odyssey = False

        # Track location to add to Journal events
        self.systemaddress: Optional[str] = None
        self.coordinates: Optional[Tuple] = None
        self.planet: Optional[str] = None

        # Avoid duplicates
        self.marketId: Optional[str] = None
        self.commodities: Optional[List[OrderedDictT[str, Any]]] = None
        self.outfitting: Optional[Tuple[bool, List[str]]] = None
        self.shipyard: Optional[Tuple[bool, List[Mapping[str, Any]]]] = None

        # For the tkinter parent window, so we can call update_idletasks()
        self.parent: tk.Tk

        # tkinter UI bits.
        self.eddn_station: tk.IntVar
        self.eddn_station_button: nb.Checkbutton

        self.eddn_system: tk.IntVar
        self.eddn_system_button: nb.Checkbutton

        self.eddn_delay: tk.IntVar
        self.eddn_delay_button: nb.Checkbutton


this = This()


HORIZ_SKU = 'ELITE_HORIZONS_V_PLANETARY_LANDINGS'


# Plugin callbacks

def plugin_start3(plugin_dir: str) -> str:
    """
    Start this plugin.

    :param plugin_dir: `str` - The full path to this plugin's directory.
    :return: `str` - Name of this plugin to use in UI.
    """
    return 'EDDN'


def journal_entry(  # noqa: C901, CCR001
        cmdr: str,
        is_beta: bool,
        system: str,
        station: str,
        entry: MutableMapping[str, Any],
        state: Mapping[str, Any]
) -> Optional[str]:
    """
    Process a new Journal entry.

    :param cmdr: `str` - Name of currennt Cmdr.
    :param is_beta: `bool` - True if this is a beta version of the Game.
    :param system: `str` - Name of system Cmdr is in.
    :param station: `str` - Name of station Cmdr is docked at, if applicable.
    :param entry: `dict` - The data for this Journal entry.
    :param state: `dict` - Current `monitor.state` data.
    :return: `str` - Error message, or `None` if no errors.
    """
    if (ks := killswitch.get_disabled("plugins.eddn.journal")).disabled:
        logger.warning(f'EDDN journal handler has been disabled via killswitch: {ks.reason}')
        plug.show_error(_('EDDN journal handler disabled. See Log.'))
        return None

    elif (ks := killswitch.get_disabled(f'plugins.eddn.journal.event.{entry["event"]}')).disabled:
        logger.warning(f'Handling of event {entry["event"]} disabled via killswitch: {ks.reason}')
        return None

    # Recursively filter '*_Localised' keys from dict
    def filter_localised(d: Mapping[str, Any]) -> OrderedDictT[str, Any]:
        filtered: OrderedDictT[str, Any] = OrderedDict()
        for k, v in d.items():
            if k.endswith('_Localised'):
                pass

            elif hasattr(v, 'items'):  # dict -> recurse
                filtered[k] = filter_localised(v)

            elif isinstance(v, list):  # list of dicts -> recurse
                filtered[k] = [filter_localised(x) if hasattr(x, 'items') else x for x in v]

            else:
                filtered[k] = v

        return filtered

    this.on_foot = state['OnFoot']

    # Note if we're under Odyssey
    # The only event this is already in is `LoadGame` which isn't sent to EDDN.
    this.odyssey = entry['odyssey'] = state['Odyssey']

    # Track location
    if entry['event'] in ('Location', 'FSDJump', 'Docked', 'CarrierJump'):
        if entry['event'] in ('Location', 'CarrierJump'):
            this.planet = entry.get('Body') if entry.get('BodyType') == 'Planet' else None

        elif entry['event'] == 'FSDJump':
            this.planet = None

        if 'StarPos' in entry:
            this.coordinates = tuple(entry['StarPos'])

        elif this.systemaddress != entry.get('SystemAddress'):
            this.coordinates = None  # Docked event doesn't include coordinates

        this.systemaddress = entry.get('SystemAddress')  # type: ignore

    elif entry['event'] == 'ApproachBody':
        this.planet = entry['Body']

    elif entry['event'] in ('LeaveBody', 'SupercruiseEntry'):
        this.planet = None

    # Send interesting events to EDDN, but not when on a crew
    if (config.get_int('output') & config.OUT_SYS_EDDN and not state['Captain'] and
        (entry['event'] in ('Location', 'FSDJump', 'Docked', 'Scan', 'SAASignalsFound', 'CarrierJump')) and
            ('StarPos' in entry or this.coordinates)):

        # strip out properties disallowed by the schema
        for thing in (
            'ActiveFine',
            'CockpitBreach',
            'BoostUsed',
            'FuelLevel',
            'FuelUsed',
            'JumpDist',
            'Latitude',
            'Longitude',
            'Wanted'
        ):
            entry.pop(thing, None)

        if 'Factions' in entry:
            # Filter faction state to comply with schema restrictions regarding personal data. `entry` is a shallow copy
            # so replace 'Factions' value rather than modify in-place.
            entry['Factions'] = [
                {
                    k: v for k, v in f.items() if k not in (
                        'HappiestSystem', 'HomeSystem', 'MyReputation', 'SquadronFaction'
                    )
                }
                for f in entry['Factions']
            ]

        # add planet to Docked event for planetary stations if known
        if entry['event'] == 'Docked' and this.planet:
            entry['Body'] = this.planet
            entry['BodyType'] = 'Planet'

        # add mandatory StarSystem, StarPos and SystemAddress properties to Scan events
        if 'StarSystem' not in entry:
            if not system:
                logger.warning("system is None, can't add StarSystem")
                return "system is None, can't add StarSystem"

            entry['StarSystem'] = system

        if 'StarPos' not in entry:
            if not this.coordinates:
                logger.warning("this.coordinates is None, can't add StarPos")
                return "this.coordinates is None, can't add StarPos"

            # Gazelle[TD] reported seeing a lagged Scan event with incorrect
            # augmented StarPos: <https://github.com/EDCD/EDMarketConnector/issues/961>
            if this.systemaddress is None or this.systemaddress != entry['SystemAddress']:
                logger.warning("event has no StarPos, but SystemAddress isn't current location")
                return "Wrong System! Delayed Scan event?"

            entry['StarPos'] = list(this.coordinates)

        if 'SystemAddress' not in entry:
            if not this.systemaddress:
                logger.warning("this.systemaddress is None, can't add SystemAddress")
                return "this.systemaddress is None, can't add SystemAddress"

            entry['SystemAddress'] = this.systemaddress

        try:
            this.eddn.export_journal_entry(cmdr, is_beta, filter_localised(entry))

        except requests.exceptions.RequestException as e:
            logger.debug('Failed in export_journal_entry', exc_info=e)
            return _("Error: Can't connect to EDDN")

        except Exception as e:
            logger.debug('Failed in export_journal_entry', exc_info=e)
            return str(e)

    elif (config.get_int('output') & config.OUT_MKT_EDDN and not state['Captain'] and
            entry['event'] in ('Market', 'Outfitting', 'Shipyard')):
        # Market.json, Outfitting.json or Shipyard.json to process

        try:
            if this.marketId != entry['MarketID']:
                this.commodities = this.outfitting = this.shipyard = None
                this.marketId = entry['MarketID']

            journaldir = config.get_str('journaldir')
            if journaldir is None or journaldir == '':
                journaldir = config.default_journal_dir

            path = pathlib.Path(journaldir) / f'{entry["event"]}.json'

            with path.open('rb') as f:
                entry = json.load(f)
                entry['odyssey'] = this.odyssey
                if entry['event'] == 'Market':
                    this.eddn.export_journal_commodities(cmdr, is_beta, entry)

                elif entry['event'] == 'Outfitting':
                    this.eddn.export_journal_outfitting(cmdr, is_beta, entry)

                elif entry['event'] == 'Shipyard':
                    this.eddn.export_journal_shipyard(cmdr, is_beta, entry)

        except requests.exceptions.RequestException as e:
            logger.debug(f'Failed exporting {entry["event"]}', exc_info=e)
            return _("Error: Can't connect to EDDN")

        except Exception as e:
            logger.debug(f'Failed exporting {entry["event"]}', exc_info=e)
            return str(e)

    return None


MAP_STR_ANY = Mapping[str, Any]


def is_horizons(economies: MAP_STR_ANY, modules: MAP_STR_ANY, ships: MAP_STR_ANY) -> bool:
    """
    Indicate if the supplied data indicates a player has Horizons access.

    :param economies: Economies of where the Cmdr is docked.
    :param modules: Modules available at the docked station.
    :param ships: Ships available at the docked station.
    :return: bool - True if the Cmdr has Horizons access.
    """
    economies_colony = False
    modules_horizons = False
    ship_horizons = False

    if isinstance(economies, dict):
        economies_colony = any(economy['name'] == 'Colony' for economy in economies.values())

    else:
        logger.error(f'economies type is {type(economies)}')

    if isinstance(modules, dict):
        modules_horizons = any(module.get('sku') == HORIZ_SKU for module in modules.values())

    else:
        logger.error(f'modules type is {type(modules)}')

    if isinstance(ships, dict):
        if ships.get('shipyard_list') is not None:
            if isinstance(ships.get('shipyard_list'), dict):
                ship_horizons = any(ship.get('sku') == HORIZ_SKU for ship in ships['shipyard_list'].values())

            else:
                logger.debug('ships["shipyard_list"] is not dict - FC or Damaged Station?')

        else:
            logger.debug('ships["shipyard_list"] is None - FC or Damaged Station?')

    else:
        logger.error(f'ships type is {type(ships)}')

    return economies_colony or modules_horizons or ship_horizons
