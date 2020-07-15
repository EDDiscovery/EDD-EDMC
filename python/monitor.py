from collections import defaultdict, OrderedDict
import time
import json
import re

from time import gmtime, localtime, sleep, strftime, strptime, time
import os
from os import listdir, SEEK_SET, SEEK_CUR, SEEK_END
from os.path import dirname, expanduser, isdir, join
from calendar import timegm
if __debug__:
    from traceback import print_exc

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from config import config

class EDLogs:

    def __init__(self):
        # EDMC Compatible

        self.event_queue = []		# For communicating journal entries back to main thread

        self.live = False       # true between Commander and Shutdown

        self.version = None
        self.is_beta = False
        self.mode = None
        self.group = None
        self.cmdr = None
        self.planet = None
        self.system = None
        self.station = None
        self.station_marketid = None
        self.stationtype = None
        self.coordinates = None
        self.systemaddress = None
        self.started = None	# Timestamp of the LoadGame event

        self.logposstored = 0
        self.logposcurrent = 0

        self.state = {
            'Captain'      : None,	# On a crew
            'Cargo'        : defaultdict(int),
            'Credits'      : None,
            'FID'          : None,	# Frontier Cmdr ID
            'Horizons'     : None,	# Does this user have Horizons?
            'Loan'         : None,
            'Raw'          : defaultdict(int),
            'Manufactured' : defaultdict(int),
            'Encoded'      : defaultdict(int),
            'Engineers'    : {},
            'Rank'         : {},
            'Reputation'   : {},
            'Statistics'   : {},
            'Role'         : None,	# Crew role - None, Idle, FireCon, FighterCon
            'Friends'      : set(),	# Online friends
            'ShipID'       : None,
            'ShipIdent'    : None,
            'ShipName'     : None,
            'ShipType'     : None,
            'HullValue'    : None,
            'ModulesValue' : None,
            'Rebuy'        : None,
            'Modules'      : None,
        }

        self.my_observer = None

        self.lastloc = None

    def start(self,root):
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

        stored = join(path,"stored.edd")
        if os.path.exists(stored):
            print("Stored exists, processing")
            self.readfile(stored)

        current = join(path,"current.edd")
        if os.path.exists(current):
            print("Current exists, processing")
            self.readfile(current)

        my_observer = Observer()
        my_observer.schedule(my_event_handler, path, recursive=go_recursively)
        my_observer.start()

        #print(f"Monitor started on {path}")

    def stop(self):
        print("Monitor stopping")
        if self.my_observer:
            self.my_observer.stop()
        if self.my_observer:
            self.my_observer.join()
            self.my_observer = None
        print("Monitor stopped")

    def close(self):
        self.stop()

    def on_created(self,event):
        print(f"{event.src_path} has been created!")

    def on_modified(self, event):
        #print(f"{event.src_path} has been modified")
        self.readfile(event.src_path)

    def readfile(self,path):
        loghandle = open(path, 'rb', 0)	# unbuffered

        if 'current' in path:
            loghandle.seek(self.logposcurrent, SEEK_SET)	# reset EOF flag

            for line in loghandle:
                print(f'Current Line {line}')
                self.event_queue.append(line)
                self.root.event_generate('<<JournalEvent>>', when="tail")

            self.logposcurrent = loghandle.tell();

        elif 'stored' in path:
            loghandle.seek(self.logposstored, SEEK_SET)	# reset EOF flag

            for line in loghandle:
                print(f'Stored Line {line}')
                entry = self.parse_entry(line)             # stored ones are parsed now for state update

                if entry['event'] == 'Location' or entry['event'] == 'FSDJump':     # for now, not going to do anything with this, but may feed it thru if required later
                    self.lastloc = entry

                elif entry['event'] == 'RefreshOver':       # its stored, and we have a refresh over, its the end of the refresh cycle.
                    if not (self.lastloc is None):
                        print("Send a Startup as we have a location")
                        entry = OrderedDict([
                            ('timestamp', strftime('%Y-%m-%dT%H:%M:%SZ', gmtime())),
                            ('event', 'StartUp'),
                            ('StarSystem', self.system),
                            ('StarPos', self.coordinates),
                            ('SystemAddress', self.systemaddress),
                        ])
                        if self.planet:
                            entry['Body'] = self.planet
                        entry['Docked'] = bool(self.station)
                        if self.station:
                            entry['StationName'] = self.station
                            entry['StationType'] = self.stationtype

                        self.event_queue.append(json.dumps(entry, separators=(', ', ':')))
                    else:
                        print("No location, send a None")
                        self.event_queue.append(None)	# Generate null event to update the display (with possibly out-of-date info)

                    self.root.event_generate('<<JournalEvent>>', when="tail")   # generate an event for the foreground

            self.logposstored = loghandle.tell();

    def get_entry(self):
        if not self.event_queue:
            return None
        else:
            entry = self.parse_entry(self.event_queue.pop(0))
            return entry

# Direct from EDMC, synced 15 July 2020 with f7aa85a02d9e20c68bffc84161b620af5431cf7a

    def parse_entry(self, line):
        if line is None:
            return { 'event': None }	# Fake startup event

        try:
            entry = json.loads(line, object_pairs_hook=OrderedDict)	# Preserve property order because why not?
            entry['timestamp']	# we expect this to exist
            if entry['event'] == 'Fileheader':
                self.live = False
                self.version = entry['gameversion']
                self.is_beta = 'beta' in entry['gameversion'].lower()
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
                self.state = {
                    'Captain'      : None,
                    'Cargo'        : defaultdict(int),
                    'Credits'      : None,
                    'FID'          : None,
                    'Horizons'     : None,
                    'Loan'         : None,
                    'Raw'          : defaultdict(int),
                    'Manufactured' : defaultdict(int),
                    'Encoded'      : defaultdict(int),
                    'Engineers'    : {},
                    'Rank'         : {},
                    'Reputation'   : {},
                    'Statistics'   : {},
                    'Role'         : None,
                    'Friends'      : set(),
                    'ShipID'       : None,
                    'ShipIdent'    : None,
                    'ShipName'     : None,
                    'ShipType'     : None,
                    'HullValue'    : None,
                    'ModulesValue' : None,
                    'Rebuy'        : None,
                    'Modules'      : None,
                }
            elif entry['event'] == 'Commander':
                self.live = True	# First event in 3.0
            elif entry['event'] == 'LoadGame':
                self.cmdr = entry['Commander']
                self.mode = entry.get('GameMode')	# 'Open', 'Solo', 'Group', or None for CQC (and Training - but no LoadGame event)
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
                self.state.update({	# Don't set Ship, ShipID etc since this will reflect Fighter or SRV if starting in those
                    'Captain'      : None,
                    'Credits'      : entry['Credits'],
                    'FID'          : entry.get('FID'),	# From 3.3
                    'Horizons'     : entry['Horizons'],	# From 3.0
                    'Loan'         : entry['Loan'],
                    'Engineers'    : {},
                    'Rank'         : {},
                    'Reputation'   : {},
                    'Statistics'   : {},
                    'Role'         : None,
                })
            elif entry['event'] == 'NewCommander':
                self.cmdr = entry['Name']
                self.group = None
            elif entry['event'] == 'SetUserShipName':
                self.state['ShipID']    = entry['ShipID']
                if 'UserShipId' in entry:	# Only present when changing the ship's ident
                    self.state['ShipIdent'] = entry['UserShipId']
                self.state['ShipName']  = entry.get('UserShipName')
                self.state['ShipType']  = self.canonicalise(entry['Ship'])
            elif entry['event'] == 'ShipyardBuy':
                self.state['ShipID'] = None
                self.state['ShipIdent'] = None
                self.state['ShipName']  = None
                self.state['ShipType'] = self.canonicalise(entry['ShipType'])
                self.state['HullValue'] = None
                self.state['ModulesValue'] = None
                self.state['Rebuy'] = None
                self.state['Modules'] = None
            elif entry['event'] == 'ShipyardSwap':
                self.state['ShipID'] = entry['ShipID']
                self.state['ShipIdent'] = None
                self.state['ShipName']  = None
                self.state['ShipType'] = self.canonicalise(entry['ShipType'])
                self.state['HullValue'] = None
                self.state['ModulesValue'] = None
                self.state['Rebuy'] = None
                self.state['Modules'] = None
            elif (entry['event'] == 'Loadout' and
                  not 'fighter' in self.canonicalise(entry['Ship']) and
                  not 'buggy' in self.canonicalise(entry['Ship'])):
                self.state['ShipID'] = entry['ShipID']
                self.state['ShipIdent'] = entry['ShipIdent']
                self.state['ShipName']  = entry['ShipName']
                self.state['ShipType']  = self.canonicalise(entry['Ship'])
                self.state['HullValue'] = entry.get('HullValue')	# not present on exiting Outfitting
                self.state['ModulesValue'] = entry.get('ModulesValue')	#   "
                self.state['Rebuy'] = entry.get('Rebuy')
                # Remove spurious differences between initial Loadout event and subsequent
                self.state['Modules'] = {}
                for module in entry['Modules']:
                    module = dict(module)
                    module['Item'] = self.canonicalise(module['Item'])
                    if ('Hardpoint' in module['Slot'] and
                        not module['Slot'].startswith('TinyHardpoint') and
                        module.get('AmmoInClip') == module.get('AmmoInHopper') == 1):	# lasers
                        module.pop('AmmoInClip')
                        module.pop('AmmoInHopper')
                    self.state['Modules'][module['Slot']] = module
            elif entry['event'] == 'ModuleBuy':
                self.state['Modules'][entry['Slot']] = {
                    'Slot'     : entry['Slot'],
                    'Item'     : self.canonicalise(entry['BuyItem']),
                    'On'       : True,
                    'Priority' : 1,
                    'Health'   : 1.0,
                    'Value'    : entry['BuyPrice'],
                }
            elif entry['event'] == 'ModuleSell':
                self.state['Modules'].pop(entry['Slot'], None)
            elif entry['event'] == 'ModuleSwap':
                toitem = self.state['Modules'].get(entry['ToSlot'])
                self.state['Modules'][entry['ToSlot']] = self.state['Modules'][entry['FromSlot']]
                if toitem:
                    self.state['Modules'][entry['FromSlot']] = toitem
                else:
                    self.state['Modules'].pop(entry['FromSlot'], None)
            elif entry['event'] in ['Undocked']:
                self.station = None
                self.station_marketid = None
                self.stationtype = None
                self.stationservices = None
            elif entry['event'] in ['Location', 'FSDJump', 'Docked', 'CarrierJump']:
                if entry['event'] in ('Location', 'CarrierJump'):
                    self.planet = entry.get('Body') if entry.get('BodyType') == 'Planet' else None
                elif entry['event'] == 'FSDJump':
                    self.planet = None
                if 'StarPos' in entry:
                    self.coordinates = tuple(entry['StarPos'])
                elif self.system != entry['StarSystem']:
                    self.coordinates = None	# Docked event doesn't include coordinates
                self.systemaddress = entry.get('SystemAddress')

                if entry['event'] in ['Location', 'FSDJump', 'CarrierJump']:
                    self.systempopulation = entry.get('Population')

                (self.system, self.station) = (entry['StarSystem'] == 'ProvingGround' and 'CQC' or entry['StarSystem'],
                                               entry.get('StationName'))	# May be None
                self.station_marketid = entry.get('MarketID') # May be None
                self.stationtype = entry.get('StationType')	# May be None
                self.stationservices = entry.get('StationServices')	# None under E:D < 2.4
            elif entry['event'] == 'ApproachBody':
                self.planet = entry['Body']
            elif entry['event'] in ['LeaveBody', 'SupercruiseEntry']:
                self.planet = None

            elif entry['event'] in ['Rank', 'Promotion']:
                payload = dict(entry)
                payload.pop('event')
                payload.pop('timestamp')
                for k,v in payload.items():
                    self.state['Rank'][k] = (v,0)
            elif entry['event'] == 'Progress':
                for k,v in entry.items():
                    if k in self.state['Rank']:
                        self.state['Rank'][k] = (self.state['Rank'][k][0], min(v, 100))	# perhaps not taken promotion mission yet
            elif entry['event'] in ['Reputation', 'Statistics']:
                payload = OrderedDict(entry)
                payload.pop('event')
                payload.pop('timestamp')
                self.state[entry['event']] = payload

            elif entry['event'] == 'EngineerProgress':
                if 'Engineers' in entry:	# Startup summary
                    self.state['Engineers'] = { e['Engineer']: (e['Rank'], e.get('RankProgress', 0)) if 'Rank' in e else e['Progress'] for e in entry['Engineers'] }
                else:	# Promotion
                    self.state['Engineers'][entry['Engineer']] = (entry['Rank'], entry.get('RankProgress', 0)) if 'Rank' in entry else entry['Progress']

            elif entry['event'] == 'Cargo' and entry.get('Vessel') == 'Ship':
                self.state['Cargo'] = defaultdict(int)
                if 'Inventory' not in entry:	# From 3.3 full Cargo event (after the first one) is written to a separate file
                    with open(join(self.currentdir, 'Cargo.json'), 'rb') as h:
                        entry = json.load(h, object_pairs_hook=OrderedDict)	# Preserve property order because why not?
                self.state['Cargo'].update({ self.canonicalise(x['Name']): x['Count'] for x in entry['Inventory'] })
            elif entry['event'] in ['CollectCargo', 'MarketBuy', 'BuyDrones', 'MiningRefined']:
                commodity = self.canonicalise(entry['Type'])
                self.state['Cargo'][commodity] += entry.get('Count', 1)
            elif entry['event'] in ['EjectCargo', 'MarketSell', 'SellDrones']:
                commodity = self.canonicalise(entry['Type'])
                self.state['Cargo'][commodity] -= entry.get('Count', 1)
                if self.state['Cargo'][commodity] <= 0:
                    self.state['Cargo'].pop(commodity)
            elif entry['event'] == 'SearchAndRescue':
                for item in entry.get('Items', []):
                    commodity = self.canonicalise(item['Name'])
                    self.state['Cargo'][commodity] -= item.get('Count', 1)
                    if self.state['Cargo'][commodity] <= 0:
                        self.state['Cargo'].pop(commodity)

            elif entry['event'] == 'Materials':
                for category in ['Raw', 'Manufactured', 'Encoded']:
                    self.state[category] = defaultdict(int)
                    self.state[category].update({ self.canonicalise(x['Name']): x['Count'] for x in entry.get(category, []) })
            elif entry['event'] == 'MaterialCollected':
                material = self.canonicalise(entry['Name'])
                self.state[entry['Category']][material] += entry['Count']
            elif entry['event'] in ['MaterialDiscarded', 'ScientificResearch']:
                material = self.canonicalise(entry['Name'])
                self.state[entry['Category']][material] -= entry['Count']
                if self.state[entry['Category']][material] <= 0:
                    self.state[entry['Category']].pop(material)
            elif entry['event'] == 'Synthesis':
                for category in ['Raw', 'Manufactured', 'Encoded']:
                    for x in entry['Materials']:
                        material = self.canonicalise(x['Name'])
                        if material in self.state[category]:
                            self.state[category][material] -= x['Count']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)
            elif entry['event'] == 'MaterialTrade':
                category = self.category(entry['Paid']['Category'])
                self.state[category][entry['Paid']['Material']] -= entry['Paid']['Quantity']
                if self.state[category][entry['Paid']['Material']] <= 0:
                    self.state[category].pop(entry['Paid']['Material'])
                category = self.category(entry['Received']['Category'])
                self.state[category][entry['Received']['Material']] += entry['Received']['Quantity']

            elif entry['event'] == 'EngineerCraft' or (entry['event'] == 'EngineerLegacyConvert' and not entry.get('IsPreview')):
                for category in ['Raw', 'Manufactured', 'Encoded']:
                    for x in entry.get('Ingredients', []):
                        material = self.canonicalise(x['Name'])
                        if material in self.state[category]:
                            self.state[category][material] -= x['Count']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)
                module = self.state['Modules'][entry['Slot']]
                assert(module['Item'] == self.canonicalise(entry['Module']))
                module['Engineering'] = {
                    'Engineer'      : entry['Engineer'],
                    'EngineerID'    : entry['EngineerID'],
                    'BlueprintName' : entry['BlueprintName'],
                    'BlueprintID'   : entry['BlueprintID'],
                    'Level'         : entry['Level'],
                    'Quality'       : entry['Quality'],
                    'Modifiers'     : entry['Modifiers'],
                    }
                if 'ExperimentalEffect' in entry:
                    module['Engineering']['ExperimentalEffect'] = entry['ExperimentalEffect']
                    module['Engineering']['ExperimentalEffect_Localised'] = entry['ExperimentalEffect_Localised']
                else:
                    module['Engineering'].pop('ExperimentalEffect', None)
                    module['Engineering'].pop('ExperimentalEffect_Localised', None)

            elif entry['event'] == 'MissionCompleted':
                for reward in entry.get('CommodityReward', []):
                    commodity = self.canonicalise(reward['Name'])
                    self.state['Cargo'][commodity] += reward.get('Count', 1)
                for reward in entry.get('MaterialsReward', []):
                    if 'Category' in reward:	# Category not present in E:D 3.0
                        category = self.category(reward['Category'])
                        material = self.canonicalise(reward['Name'])
                        self.state[category][material] += reward.get('Count', 1)
            elif entry['event'] == 'EngineerContribution':
                commodity = self.canonicalise(entry.get('Commodity'))
                if commodity:
                    self.state['Cargo'][commodity] -= entry['Quantity']
                    if self.state['Cargo'][commodity] <= 0:
                        self.state['Cargo'].pop(commodity)
                material = self.canonicalise(entry.get('Material'))
                if material:
                    for category in ['Raw', 'Manufactured', 'Encoded']:
                        if material in self.state[category]:
                            self.state[category][material] -= entry['Quantity']
                            if self.state[category][material] <= 0:
                                self.state[category].pop(material)
            elif entry['event'] == 'TechnologyBroker':
                for thing in entry.get('Ingredients', []):	# 3.01
                    for category in ['Cargo', 'Raw', 'Manufactured', 'Encoded']:
                        item = self.canonicalise(thing['Name'])
                        if item in self.state[category]:
                            self.state[category][item] -= thing['Count']
                            if self.state[category][item] <= 0:
                                self.state[category].pop(item)
                for thing in entry.get('Commodities', []):	# 3.02
                    commodity = self.canonicalise(thing['Name'])
                    self.state['Cargo'][commodity] -= thing['Count']
                    if self.state['Cargo'][commodity] <= 0:
                        self.state['Cargo'].pop(commodity)
                for thing in entry.get('Materials', []):	# 3.02
                    material = self.canonicalise(thing['Name'])
                    category = thing['Category']
                    self.state[category][material] -= thing['Count']
                    if self.state[category][material] <= 0:
                        self.state[category].pop(material)

            elif entry['event'] == 'JoinACrew':
                self.state['Captain'] = entry['Captain']
                self.state['Role'] = 'Idle'
                self.planet = None
                self.system = None
                self.station = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None
            elif entry['event'] == 'ChangeCrewRole':
                self.state['Role'] = entry['Role']
            elif entry['event'] == 'QuitACrew':
                self.state['Captain'] = None
                self.state['Role'] = None
                self.planet = None
                self.system = None
                self.station = None
                self.stationtype = None
                self.stationservices = None
                self.coordinates = None
                self.systemaddress = None

            elif entry['event'] == 'Friends':
                if entry['Status'] in ['Online', 'Added']:
                    self.state['Friends'].add(entry['Name'])
                else:
                    self.state['Friends'].discard(entry['Name'])

            elif entry['event'] == 'Shutdown':
                self.live = False

            return entry
        except:
            if __debug__:
                print('Invalid journal entry "%s"' % repr(line))
                print_exc()
            return { 'event': None }

    _RE_CANONICALISE = re.compile(r'\$(.+)_name;')
    _RE_CATEGORY = re.compile(r'\$MICRORESOURCE_CATEGORY_(.+);')

    # Commodities, Modules and Ships can appear in different forms e.g. "$HNShockMount_Name;", "HNShockMount", and "hnshockmount",
    # "$int_cargorack_size6_class1_name;" and "Int_CargoRack_Size6_Class1", "python" and "Python", etc.
    # This returns a simple lowercased name e.g. 'hnshockmount', 'int_cargorack_size6_class1', 'python', etc
    def canonicalise(self, item):
        if not item: return ''
        item = item.lower()
        match = self._RE_CANONICALISE.match(item)
        return match and match.group(1) or item

    def category(self, item):
        match = self._RE_CATEGORY.match(item)
        return (match and match.group(1) or item).capitalize()


    # Return a subset of the received data describing the current ship as a Loadout event
    def ship(self, timestamped=True):
        if not self.state['Modules']:
            return None

        standard_order = ['ShipCockpit', 'CargoHatch', 'Armour', 'PowerPlant', 'MainEngines', 'FrameShiftDrive', 'LifeSupport', 'PowerDistributor', 'Radar', 'FuelTank']

        d = OrderedDict()
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
        for slot in sorted(self.state['Modules'], key=lambda x: ('Hardpoint' not in x, x not in standard_order and len(standard_order) or standard_order.index(x), 'Slot' not in x, x)):
            module = dict(self.state['Modules'][slot])
            module.pop('Health', None)
            module.pop('Value', None)
            d['Modules'].append(module)
        return d

    # Export ship loadout as a Loadout event
    def export_ship(self, filename=None):
        string = json.dumps(self.ship(False), ensure_ascii=False, indent=2, separators=(',', ': '))	# pretty print

        if filename:
            with open(filename, 'wt') as h:
                h.write(string)
            return

        ship = ship_file_name(self.state['ShipName'], self.state['ShipType'])
        regexp = re.compile(re.escape(ship) + '\.\d\d\d\d\-\d\d\-\d\dT\d\d\.\d\d\.\d\d\.txt')
        oldfiles = sorted([x for x in listdir(config.get('outdir')) if regexp.match(x)])
        if oldfiles:
            with open(join(config.get('outdir'), oldfiles[-1]), 'rU') as h:
                if h.read() == string:
                    return	# same as last time - don't write

        # Write
        filename = join(config.get('outdir'), '%s.%s.txt' % (ship, strftime('%Y-%m-%dT%H.%M.%S', localtime(time()))))
        with open(filename, 'wt') as h:
            h.write(string)



# singleton
monitor = EDLogs()

