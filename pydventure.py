#!/usr/bin/env python3
"""
pydventure - A text adventure engine.
Brand: pydventure
Game name derived from the containing folder.

Usage:
    python pydventure.py [--tui] [game_directory]

Tables (enemies.json, drops.json, items.json, skills.json, maps.json,
recipes.json) are loaded from the game directory. Run
pydventure_gamemaker.py to create them.
"""

import json
import os
import random
import sys
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

PROGRAM_NAME = "pydventure"

DIRECTIONS = {'N', 'E', 'S', 'W', 'U', 'D'}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E', 'U': 'D', 'D': 'U'}
SKILL_NAMES = {'fight', 'avoidance', 'search'}

# ----------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------
@dataclass
class Requirement:
    name: str
    consume: int = 0
    @property
    def is_skill(self): return self.name in SKILL_NAMES
    @property
    def is_consumable(self): return self.consume > 0
    def to_string(self): return f"{self.name}-{self.consume}" if self.consume > 0 else self.name

@dataclass
class TeleportTarget:
    map_name: str
    x: int
    y: int
    z: int
    entrance_dir: str
    def to_string(self): return f"<{self.map_name}:{self.x},{self.y},{self.z},{self.entrance_dir}>"

@dataclass
class DoorInfo:
    reach: Optional[Requirement] = None
    pass_reqs: List[Requirement] = field(default_factory=list)
    teleport: Optional[TeleportTarget] = None

@dataclass
class ItemInfo:
    name: str
    count: int = 1
    requirements: List[Requirement] = field(default_factory=list)
    price: Optional[int] = None

    @property
    def for_sale(self):
        return self.price is not None

@dataclass
class Zone:
    doors: Dict[str, DoorInfo] = field(default_factory=dict)
    enemies: List[Tuple[str, int]] = field(default_factory=list)
    items: List[ItemInfo] = field(default_factory=list)

@dataclass
class Room:
    zones: List[Zone] = field(default_factory=list)
    description: Optional[str] = None

# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------
def parse_requirement(text: str) -> Requirement:
    text = text.strip()
    if not text:
        raise ValueError("Empty requirement")
    m = re.match(r'^(.+?)-(\d+)$', text)
    if m:
        return Requirement(m.group(1).strip(), int(m.group(2)))
    return Requirement(text, 0)

def parse_requirements(text: str) -> List[Requirement]:
    reqs = []
    for part in text.split(','):
        part = part.strip()
        if part:
            reqs.append(parse_requirement(part))
    return reqs

def parse_enemies(enemy_str: str) -> List[Tuple[str, int]]:
    enemies = []
    for part in enemy_str.split(','):
        part = part.strip()
        if not part: continue
        if '+' in part:
            eid, delta = part.split('+', 1)
            count = 1 + int(delta)
        else:
            eid = part
            count = 1
        enemies.append((eid.strip(), count))
    return enemies

def parse_items(item_str: str) -> List[Tuple[str, int, Optional[int]]]:
    items = []
    for part in item_str.split(','):
        part = part.strip()
        if not part: continue
        price = None
        if '@' in part:
            part, price_str = part.rsplit('@', 1)
            try:
                price = int(price_str.strip())
            except ValueError:
                raise ValueError(f"Invalid price in item spec: {part}@{price_str}")
        if '+' in part:
            iid, delta = part.split('+', 1)
            count = 1 + int(delta)
        else:
            iid, count = part, 1
        items.append((iid.strip(), count, price))
    return items

def parse_teleport(text: str) -> TeleportTarget:
    text = text.strip()
    if ':' not in text:
        raise ValueError("Invalid teleport format")
    map_name, coords = text.split(':', 1)
    parts = coords.split(',')
    if len(parts) != 4:
        raise ValueError("Teleport needs x,y,z,entrance_dir")
    x, y, z, entrance = int(parts[0]), int(parts[1]), int(parts[2]), parts[3].strip()
    if entrance not in DIRECTIONS:
        raise ValueError(f"Invalid entrance direction: {entrance}")
    return TeleportTarget(map_name.strip(), x, y, z, entrance)

def tokenize_flow(flow_str: str) -> List[Tuple[str, str]]:
    tokens = []
    i = 0
    while i < len(flow_str):
        ch = flow_str[i]
        if ch in DIRECTIONS:
            tokens.append(('dir', ch)); i += 1
        elif ch == '[':
            j = flow_str.find(']', i)
            if j == -1: raise ValueError("Unclosed '['")
            tokens.append(('req', flow_str[i+1:j].strip())); i = j+1
        elif ch == '{':
            j = flow_str.find('}', i)
            if j == -1: raise ValueError("Unclosed '{'")
            tokens.append(('enemies', flow_str[i+1:j])); i = j+1
        elif ch == '(':
            j = flow_str.find(')', i)
            if j == -1: raise ValueError("Unclosed '('")
            tokens.append(('items', flow_str[i+1:j])); i = j+1
        elif ch == '<':
            j = flow_str.find('>', i)
            if j == -1: raise ValueError("Unclosed '<'")
            tokens.append(('teleport', flow_str[i+1:j])); i = j+1
        elif ch.isspace():
            i += 1
        else:
            raise ValueError(f"Unexpected character: {ch}")
    return tokens

def parse_flow(flow_str: str, seen_directions: set) -> Zone:
    zone = Zone()
    tokens = tokenize_flow(flow_str)
    consumed = [False] * len(tokens)

    for idx, (tok_type, tok_val) in enumerate(tokens):
        if tok_type != 'dir': continue
        direction = tok_val
        if direction in seen_directions:
            raise ValueError(f"Duplicate door '{direction}' in room")
        seen_directions.add(direction)

        reach_req = None
        pass_reqs = []
        teleport = None

        if idx > 0 and tokens[idx-1][0] == 'req' and not consumed[idx-1]:
            reach_req = parse_requirement(tokens[idx-1][1])
            consumed[idx-1] = True

        j = idx + 1
        if j < len(tokens) and tokens[j][0] == 'req' and not consumed[j]:
            pass_reqs = parse_requirements(tokens[j][1])
            consumed[j] = True
            j += 1
        if j < len(tokens) and tokens[j][0] == 'teleport' and not consumed[j]:
            teleport = parse_teleport(tokens[j][1])
            consumed[j] = True
            j += 1
        if not pass_reqs and teleport is None:
            j = idx + 1
            if j < len(tokens) and tokens[j][0] == 'teleport' and not consumed[j]:
                teleport = parse_teleport(tokens[j][1])
                consumed[j] = True
                j += 1
            if j < len(tokens) and tokens[j][0] == 'req' and not consumed[j]:
                pass_reqs = parse_requirements(tokens[j][1])
                consumed[j] = True

        zone.doors[direction] = DoorInfo(reach=reach_req, pass_reqs=pass_reqs, teleport=teleport)

    for idx, (tok_type, tok_val) in enumerate(tokens):
        if tok_type == 'enemies':
            zone.enemies.extend(parse_enemies(tok_val))
        elif tok_type == 'items':
            parsed_items = parse_items(tok_val)
            item_reqs = []
            if idx+1 < len(tokens) and tokens[idx+1][0] == 'req' and not consumed[idx+1]:
                item_reqs = parse_requirements(tokens[idx+1][1])
                consumed[idx+1] = True
            for name, count, price in parsed_items:
                zone.items.append(ItemInfo(name, count, item_reqs.copy(), price))
        elif tok_type == 'req' and not consumed[idx]:
            raise ValueError(f"Requirement '{tok_val}' not attached to any door or item")
        elif tok_type == 'teleport' and not consumed[idx]:
            raise ValueError(f"Teleport '{tok_val}' not attached to any door")
    return zone

def parse_room(room_str: str) -> Room:
    flows = []
    current = []
    depth_braces = depth_brackets = depth_parens = depth_angle = 0
    for ch in room_str:
        if ch == '{': depth_braces += 1
        elif ch == '}': depth_braces -= 1
        elif ch == '[': depth_brackets += 1
        elif ch == ']': depth_brackets -= 1
        elif ch == '(': depth_parens += 1
        elif ch == ')': depth_parens -= 1
        elif ch == '<': depth_angle += 1
        elif ch == '>': depth_angle -= 1
        elif ch == ',' and depth_braces == 0 and depth_brackets == 0 and depth_parens == 0 and depth_angle == 0:
            flows.append(''.join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        flows.append(''.join(current).strip())

    room = Room()
    seen_directions = set()
    for flow_str in flows:
        if flow_str:
            room.zones.append(parse_flow(flow_str, seen_directions))
    return room

# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------
def enemies_to_string(enemies):
    parts = [name if count == 1 else f"{name}+{count-1}" for name, count in enemies]
    return "{" + ",".join(parts) + "}" if parts else ""

def reqs_to_string(reqs):
    return "[" + ",".join(r.to_string() for r in reqs) + "]" if reqs else ""

def items_to_string(items):
    parts = []
    for item in items:
        s = item.name if item.count == 1 else f"{item.name}+{item.count-1}"
        if item.requirements:
            s += reqs_to_string(item.requirements)
        if item.price is not None:
            s += f"@{item.price}"
        parts.append(s)
    return "(" + ",".join(parts) + ")" if parts else ""

def zone_to_string(zone):
    parts = []
    for d in ['N','E','S','W','U','D']:
        if d in zone.doors:
            di = zone.doors[d]
            if di.reach: parts.append(f"[{di.reach.to_string()}]")
            parts.append(d)
            if di.pass_reqs: parts.append(reqs_to_string(di.pass_reqs))
            if di.teleport: parts.append(di.teleport.to_string())
    if zone.enemies: parts.append(enemies_to_string(zone.enemies))
    if zone.items: parts.append(items_to_string(zone.items))
    return ''.join(parts)

def room_to_string(room):
    return ",".join(zone_to_string(z) for z in room.zones)

# ----------------------------------------------------------------------
# Player state
# ----------------------------------------------------------------------
class PlayerState:
    def __init__(self, inventory=None, skills=None, map_name='overworld',
                 x=0, y=0, z=0, zone=0, sword_level=0, coins=0, won=False,
                 hp=5, max_hp=5):
        self.inventory = inventory or {}
        self.skills = skills or {'fight':0, 'avoidance':0, 'search':0}
        self.map_name = map_name
        self.x, self.y, self.z, self.zone = x, y, z, zone
        self.sword_level = sword_level
        self.coins = coins
        self.won = won
        self.hp = hp
        self.max_hp = max_hp
        self.current_room = None

    def take_damage(self, n):
        self.hp = max(0, self.hp - n)

    def heal_full(self):
        self.hp = self.max_hp

    def add_item(self, item, count=1): self.inventory[item] = self.inventory.get(item, 0) + count
    def remove_item(self, item, count=1):
        if self.inventory.get(item, 0) >= count:
            self.inventory[item] -= count
            if self.inventory[item] == 0: del self.inventory[item]
            return True
        return False
    def has_item(self, item, count=1): return self.inventory.get(item, 0) >= count
    def get_skill(self, skill): return self.skills.get(skill, 0)
    def increase_skill(self, skill): self.skills[skill] = self.skills.get(skill, 0) + 1

    def spend_coins(self, n):
        if self.coins >= n:
            self.coins -= n
            return True
        return False

    def grant(self, name, count=1):
        if name == "sword":
            self.sword_level += 1
        else:
            self.add_item(name, count)

    def to_json(self):
        return json.dumps({"map": self.map_name, "x": self.x, "y": self.y,
                           "z": self.z, "zone": self.zone,
                           "coins": self.coins,
                           "inventory": self.inventory, "skills": self.skills,
                           "sword_level": self.sword_level,
                           "won": self.won,
                           "hp": self.hp, "max_hp": self.max_hp}, indent=2)

    @classmethod
    def from_json(cls, json_str):
        data = json.loads(json_str)
        return cls(inventory=data.get('inventory', {}),
                   skills=data.get('skills', {}),
                   map_name=data.get('map', 'overworld'),
                   x=data.get('x',0), y=data.get('y',0),
                   z=data.get('z',0), zone=data.get('zone',0),
                   sword_level=data.get('sword_level', 0),
                   coins=data.get('coins', 0),
                   won=data.get('won', False),
                   hp=data.get('hp', 5),
                   max_hp=data.get('max_hp', 5))

# ----------------------------------------------------------------------
# Room state
# ----------------------------------------------------------------------
def _roll(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return random.randint(int(v[0]), int(v[1]))
    return int(v)

class RoomState:
    def __init__(self, room, player, difficulty_func=None, drops_func=None, combat=None):
        self.room = room
        self.player = player
        self.difficulty_func = difficulty_func or (lambda name: 1)
        self.drops_func = drops_func or (lambda name: {})
        self.combat = combat
        self.current_zone = player.zone if 0 <= player.zone < len(room.zones) else 0
        self.zone_cleared = [False] * len(room.zones)

    def _zone_entry_requirement(self, idx):
        zone = self.room.zones[idx]
        if not zone.doors: return None
        return next(iter(zone.doors.values())).reach

    def can_enter_zone(self, idx):
        if idx < 0 or idx >= len(self.room.zones): return False
        if idx == self.current_zone: return True
        req = self._zone_entry_requirement(idx)
        if req is None: return True
        if req.is_consumable: return self.player.has_item(req.name, req.consume)
        if req.is_skill: return self.player.get_skill(req.name) > 0
        return self.player.has_item(req.name)

    def enter_zone(self, idx):
        if not self.can_enter_zone(idx): return False
        req = self._zone_entry_requirement(idx)
        if req:
            if req.is_consumable:
                self.player.remove_item(req.name, req.consume)
                zone = self.room.zones[idx]
                if zone.doors: next(iter(zone.doors.values())).reach = None
            elif req.is_skill:
                self.player.increase_skill(req.name)
        self.current_zone = idx
        self.player.zone = idx
        return True

    def current_doors(self): return self.room.zones[self.current_zone].doors

    def is_door_visible(self, direction):
        di = self.current_doors().get(direction)
        if di is None: return False
        if di.pass_reqs and di.pass_reqs[0].name == 'search':
            return False
        return True

    def is_item_visible(self, item_name):
        for item in self.room.zones[self.current_zone].items:
            if item.name == item_name:
                if item.requirements and item.requirements[0].name == 'search':
                    return False
                return True
        return False

    def can_use_door(self, direction):
        if not self.is_door_visible(direction): return False
        di = self.current_doors().get(direction)
        if not di.pass_reqs: return True
        req = di.pass_reqs[0]
        if req.is_consumable: return self.player.has_item(req.name, req.consume)
        if req.is_skill: return self.player.get_skill(req.name) > 0
        return self.player.has_item(req.name)

    def use_door(self, direction):
        if not self.can_use_door(direction): return False
        di = self.current_doors()[direction]
        if di.pass_reqs:
            req = di.pass_reqs[0]
            if req.is_consumable:
                if not self.player.has_item(req.name, req.consume): return False
                self.player.remove_item(req.name, req.consume)
            elif req.is_skill:
                if self.player.get_skill(req.name) <= 0: return False
                self.player.increase_skill(req.name)
            else:
                if not self.player.has_item(req.name): return False
            di.pass_reqs.pop(0)
        return True

    def search_zone(self, direction=None):
        revealed = []
        if direction:
            di = self.current_doors().get(direction)
            if di and di.pass_reqs and di.pass_reqs[0].name == 'search':
                di.pass_reqs.pop(0)
                revealed.append(f"Door {direction}")
        else:
            for d, di in self.current_doors().items():
                if di.pass_reqs and di.pass_reqs[0].name == 'search':
                    di.pass_reqs.pop(0)
                    revealed.append(f"Door {d}")
            for item in self.room.zones[self.current_zone].items:
                if item.requirements and item.requirements[0].name == 'search':
                    item.requirements.pop(0)
                    revealed.append(f"Item {item.name}")
        self.player.increase_skill('search')
        if revealed:
            return (True, "You search and discover: " + ", ".join(revealed))
        else:
            return (True, "You search but find nothing new.")

    def current_enemies(self):
        if self.zone_cleared[self.current_zone]: return []
        return self.room.zones[self.current_zone].enemies

    def _enemy_power(self, enemies):
        total = 0
        for name, count in enemies:
            diff = self.difficulty_func(name)
            total += diff * count
        return total

    def _roll_drops(self, enemies):
        """Roll drops for a defeated enemy group. Returns a dict of
        {item_name: count} containing everything that fell.

        The drop table for each enemy is a dict whose "items" key maps
        item names to either an int (fixed count) or a [min, max] pair
        (inclusive random roll). Zero rolls are elided.

            {"items": {"wood": [0, 2], "rock": [1, 1]}}
        """
        totals = {}
        for name, count in enemies:
            drop = self.drops_func(name) or {}
            items = drop.get("items", {})
            if not items:
                continue
            for _ in range(count):
                for iname, irange in items.items():
                    n = _roll(irange)
                    if n:
                        totals[iname] = totals.get(iname, 0) + n
        return totals

    def fight_enemies(self):
        enemies = self.current_enemies()
        if not enemies:
            return (False, "No enemies here.")
        ep = self._enemy_power(enemies)
        pool = 1 + self.player.get_skill('fight') + 20 * self.player.sword_level
        roll = random.randint(0, pool)
        enemy_roll = random.randint(0, ep)
        if roll < enemy_roll:
            dmg = self.combat["damage_per_fail"]
            self.player.take_damage(dmg)
            return (False,
                    f"You are driven back! (-{dmg} HP) "
                    f"(you {roll} vs them {enemy_roll}; FP {pool} vs EP {ep})")
        self.player.increase_skill('fight')
        loot = self._roll_drops(enemies)
        self.zone_cleared[self.current_zone] = True
        self.room.zones[self.current_zone].enemies = []
        msg = (f"You defeat the enemies! "
               f"(you {roll} vs them {enemy_roll}; FP {pool} vs EP {ep})")
        if loot:
            parts = []
            for iname, n in sorted(loot.items()):
                self.player.grant(iname, n)
                parts.append(iname if n == 1 else f"{iname} x{n}")
            msg += " You collect " + ", ".join(parts) + "."
        return (True, msg)

    def avoid_enemies(self):
        enemies = self.current_enemies()
        if not enemies:
            return (False, "No enemies here.")
        ep = self._enemy_power(enemies)
        pool = 1 + self.player.get_skill('avoidance')
        roll = random.randint(0, pool)
        enemy_roll = random.randint(0, ep)
        if roll < enemy_roll:
            dmg = self.combat["damage_per_fail"]
            self.player.take_damage(dmg)
            return (False,
                    f"You fail to slip past. (-{dmg} HP) "
                    f"(you {roll} vs them {enemy_roll}; AP {pool} vs EP {ep})")
        self.player.increase_skill('avoidance')
        return (True,
                f"You slip past the enemies! "
                f"(you {roll} vs them {enemy_roll}; AP {pool} vs EP {ep})")

    def clear_with_fire(self):
        """Burn out the current zone. Guaranteed, silent, no drops.
        Enemies scatter; they do not die, so nothing falls."""
        enemies = self.current_enemies()
        if not enemies:
            return (False, "No enemies here.")
        self.zone_cleared[self.current_zone] = True
        self.room.zones[self.current_zone].enemies = []
        self.player.increase_skill('avoidance')
        return (True,
                "You hurl the fire. It flares, and the enemies scatter "
                "into the dark. You slip through unseen. (avoidance +1)")
    
    def current_items(self):
        return [item for item in self.room.zones[self.current_zone].items if self.is_item_visible(item.name)]

    def _consume_requirement(self, item):
        if not item.requirements:
            return (True, None)
        req = item.requirements[0]
        if req.is_consumable:
            if not self.player.has_item(req.name, req.consume):
                return (False, f"You need {req.name}.")
            self.player.remove_item(req.name, req.consume)
        elif req.is_skill:
            if self.player.get_skill(req.name) <= 0:
                return (False, f"You need {req.name} skill.")
            self.player.increase_skill(req.name)
        else:
            if not self.player.has_item(req.name):
                return (False, f"You need {req.name}.")
        item.requirements.pop(0)
        return (True, f"You uncover the {item.name}.")

    def _find_item(self, name):
        for i, item in enumerate(self.room.zones[self.current_zone].items):
            if item.name == name: return i, item
        return -1, None

    def take_item(self, item_name):
        if not self.is_item_visible(item_name): return (False, "You don't see that here.")
        i, item = self._find_item(item_name)
        if item is None: return (False, "That item is not here.")
        if item.for_sale:
            return (False, f"The {item.name} is for sale ({item.price} coins). Try 'buy {item.name}'.")
        ok, msg = self._consume_requirement(item)
        if not ok: return (False, msg)
        if msg: return (True, msg)
        del self.room.zones[self.current_zone].items[i]
        self.player.grant(item.name, item.count)
        return (True, f"You take {item.name} x{item.count}.")

    def buy_item(self, item_name):
        if not self.is_item_visible(item_name): return (False, "You don't see that here.")
        i, item = self._find_item(item_name)
        if item is None: return (False, "That item is not here.")
        if not item.for_sale:
            return (False, f"The {item.name} isn't for sale.")
        ok, msg = self._consume_requirement(item)
        if not ok: return (False, msg)
        if msg: return (True, msg)
        if not self.player.spend_coins(item.price):
            return (False, f"You need {item.price} coins (you have {self.player.coins}).")
        if item.count > 1:
            item.count -= 1
            self.player.grant(item.name, 1)
            return (True, f"You buy {item.name} for {item.price} coins. ({item.count} remaining)")
        del self.room.zones[self.current_zone].items[i]
        self.player.grant(item.name, 1)
        return (True, f"You buy {item.name} for {item.price} coins.")

# ----------------------------------------------------------------------
# File system manager
# ----------------------------------------------------------------------
class GameMap:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.rooms_base = os.path.join(base_dir, "rooms")
        os.makedirs(self.rooms_base, exist_ok=True)
        self.player_state_path = os.path.join(base_dir, "player.state")
        self.player_json_path = os.path.join(base_dir, "player.json")
        self.map_dims_cache = {}
        self.enemy_db = self._load_enemy_db()
        self.drops_db = self._load_drops()
        self.maps_db = self._load_maps_db()
        self.recipes = self._load_recipes()
        self.combat = self.maps_db["combat"]
        self.death_cfg = self.combat["death"]

        respawn = self.maps_db["respawn"]
        self.respawn_seconds = respawn["minutes"] * 60.0
        self.respawn_chance  = respawn["chance"]
        self.no_respawn      = set(respawn["no_respawn"])

    def _require(self, name):
        path = os.path.join(self.base_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} missing. Run pydventure_gamemaker.py to create the game tables."
            )
        return path

    def _load_enemy_db(self):
        with open(self._require("enemies.json")) as f:
            return json.load(f)

    def _load_drops(self):
        with open(self._require("drops.json")) as f:
            return json.load(f)

    def _load_maps_db(self):
        with open(self._require("maps.json")) as f:
            return json.load(f)

    def _load_recipes(self):
        with open(self._require("recipes.json")) as f:
            recipes = json.load(f)["recipes"]
        seen = set()
        for r in recipes:
            sig = tuple(sorted(r["inputs"].items()))
            if sig in seen:
                raise ValueError(f"Duplicate recipe signature in recipes.json: {r['inputs']}")
            seen.add(sig)
        return recipes

    def find_recipe(self, inputs: dict):
        sig = tuple(sorted(inputs.items()))
        for r in self.recipes:
            if tuple(sorted(r["inputs"].items())) == sig:
                return r
        return None

    def difficulty(self, enemy_name):
        entry = self.enemy_db.get(enemy_name, {})
        return entry.get("difficulty", 1)

    def drops(self, enemy_name):
        return self.drops_db.get(enemy_name, {})

    def goal(self):
        return self.maps_db.get("goal", {})

    def _get_map_dir(self, map_name):
        d = os.path.join(self.rooms_base, map_name)
        os.makedirs(d, exist_ok=True)
        return d

    def _room_filename(self, map_name, x, y, z, state=False):
        suffix = ".state" if state else ".room"
        return os.path.join(self._get_map_dir(map_name), f"{x}_{y}_{z}{suffix}")

    def load_room(self, map_name, x, y, z):
        state_path = self._room_filename(map_name, x, y, z, True)
        if os.path.exists(state_path):
            age = time.time() - os.path.getmtime(state_path)
            room = self._load_room_from_file(state_path)
            if age >= self.respawn_seconds and random.random() < self.respawn_chance:
                self._repopulate(room, map_name, x, y, z)
            return room
        room_path = self._room_filename(map_name, x, y, z, False)
        if os.path.exists(room_path):
            return self._load_room_from_file(room_path)
        return None

    def load_room_pristine(self, map_name, x, y, z):
        path = self._room_filename(map_name, x, y, z, False)
        if not os.path.exists(path):
            return None
        return self._load_room_from_file(path)

    def _repopulate(self, room, map_name, x, y, z):
        # Room-wide gate. If any zone still holds enemies, the room is
        # "in progress" and we don't touch it. Multi-zone rooms therefore
        # only ever respawn once every zone has been cleared.
        if any(zone.enemies for zone in room.zones):
            return
        original = self.load_room_pristine(map_name, x, y, z)
        if original is None:
            return
        for idx, orig_zone in enumerate(original.zones):
            if idx >= len(room.zones):
                break
            if not orig_zone.enemies:
                continue
            if any(name in self.no_respawn for name, _ in orig_zone.enemies):
                continue
            room.zones[idx].enemies = list(orig_zone.enemies)

    def _load_room_from_file(self, path):
        with open(path, 'r') as f:
            lines = f.read().splitlines()
        room_str = lines[0].strip() if lines else ""
        room = parse_room(room_str)
        if len(lines) > 1:
            room.description = lines[1].strip()
        return room

    def save_room_state(self, map_name, x, y, z, room):
        with open(self._room_filename(map_name, x, y, z, True), 'w') as f:
            f.write(room_to_string(room))
            if room.description:
                f.write("\n" + room.description)

    def save_player_state(self, player):
        with open(self.player_state_path, 'w') as f:
            f.write(player.to_json())

    def load_player_state(self):
        for path in (self.player_state_path, self.player_json_path):
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return PlayerState.from_json(f.read())
        start_map = self.maps_db.get("start_map", "overworld")
        return PlayerState(map_name=start_map, x=0, y=0, z=1, zone=0)

    def list_maps(self):
        if not os.path.isdir(self.rooms_base):
            return []
        return [d for d in os.listdir(self.rooms_base)
                if os.path.isdir(os.path.join(self.rooms_base, d))]

    def get_map_dimensions(self, map_name):
        if map_name in self.map_dims_cache:
            return self.map_dims_cache[map_name]
        map_dir = self._get_map_dir(map_name)
        max_x = max_y = max_z = -1
        pattern = re.compile(r'^(\d+)_(\d+)_(\d+)\.(room|state)$')
        for fname in os.listdir(map_dir):
            m = pattern.match(fname)
            if m:
                x, y, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                max_z = max(max_z, z)
        if max_x < 0:
            dims = {'x_size': 8, 'y_size': 8, 'z_size': 4}
        else:
            dims = {'x_size': max_x + 1, 'y_size': max_y + 1, 'z_size': max_z + 1}
        self.map_dims_cache[map_name] = dims
        return dims

# ----------------------------------------------------------------------
# Game session
# ----------------------------------------------------------------------
class GameSession:
    def __init__(self, base_dir, game_name=None):
        self.map = GameMap(base_dir)
        self.game_name = game_name or os.path.basename(os.path.abspath(base_dir))
        self.player = self.map.load_player_state()
        self.last_move_dir = None
        self.load_current_room()
        if self.player.won:
            print("The world is quiet. You have already won.")

    def load_current_room(self):
        room = self.map.load_room(self.player.map_name, self.player.x, self.player.y, self.player.z)
        if room:
            self.player.current_room = RoomState(
                room, self.player,
                difficulty_func=self.map.difficulty,
                drops_func=self.map.drops,
                combat=self.map.combat,
            )
        else:
            self.player.current_room = None

    def save_game(self):
        if self.player.current_room:
            self.map.save_room_state(self.player.map_name, self.player.x, self.player.y, self.player.z,
                                     self.player.current_room.room)
        self.map.save_player_state(self.player)

    def _find_zone_for_entrance(self, room, entrance_dir):
        for idx, zone in enumerate(room.zones):
            if entrance_dir in zone.doors:
                return idx
        return 0

    def _neighbor_coords(self, direction):
        """Coords of the cell one step in `direction` from the player."""
        dx = dy = dz = 0
        if direction == 'N': dy = 1
        elif direction == 'S': dy = -1
        elif direction == 'E': dx = 1
        elif direction == 'W': dx = -1
        elif direction == 'U': dz = 1
        elif direction == 'D': dz = -1
        else:
            return (None, None, None)
        return (self.player.x + dx, self.player.y + dy, self.player.z + dz)

    def _unlock_neighbor(self, map_name, x, y, z, direction, req_name):
        """Remove a matching pass requirement from the neighbor's state
        (or pristine room, which we then write as a state file) so that a
        consumed door — bomb wall, locked door — is open from both sides
        the first time it's opened. Called after a consumable requirement
        has been spent in the current room."""
        state_path = self.map._room_filename(map_name, x, y, z, True)
        pristine_path = self.map._room_filename(map_name, x, y, z, False)
        path = state_path if os.path.exists(state_path) else pristine_path
        if not os.path.exists(path):
            return
        room = self.map._load_room_from_file(path)
        changed = False
        for zone in room.zones:
            di = zone.doors.get(direction)
            if di and di.pass_reqs and di.pass_reqs[0].name == req_name:
                di.pass_reqs.pop(0)
                changed = True
                break
        if changed:
            self.map.save_room_state(map_name, x, y, z, room)

    def _open_door_with_item(self, direction, item_name):
        """Use an item on a door in the current room, mirroring the
        unlock to the neighbor when the requirement is consumable."""
        rs = self.player.current_room
        if rs is None:
            return (False, "No room.")
        di = rs.current_doors().get(direction)
        if di is None:
            return (False, f"No door {direction}.")
        if not (di.pass_reqs and di.pass_reqs[0].name == item_name):
            return (False, f"{direction} door doesn't need {item_name}.")
        req = di.pass_reqs[0]
        consumed = req.is_consumable
        if not rs.use_door(direction):
            return (False, "Cannot use that.")
        if consumed:
            nx, ny, nz = self._neighbor_coords(direction)
            if nx is not None:
                self._unlock_neighbor(
                    self.player.map_name, nx, ny, nz,
                    OPPOSITE[direction], req.name)
        return (True, f"Used {item_name} on {direction} door.")

    def _enemy_block(self, emit=None):
        emit = emit or print
        if self.player.current_room is None:
            return True
        rs = self.player.current_room
        if rs.current_enemies():
            success, msg = rs.avoid_enemies()
            if not success:
                emit(f"Enemies block your way! {msg}")
                return False
            else:
                emit(f"You slip past the enemies! ({msg})")
                return True
        return True

    def move_through_door(self, direction):
        if not self.player.current_room: return (False, "No room.")
        rs = self.player.current_room
        if direction not in DIRECTIONS: return (False, "Invalid direction.")
        if not rs.is_door_visible(direction):
            return (False, "There is no door in that direction.")
        if not rs.can_use_door(direction):
            di = rs.current_doors().get(direction)
            if di is None: return (False, "No door there.")
            if di.pass_reqs: return (False, f"You need {di.pass_reqs[0].name}.")
            return (False, "Cannot go that way.")

        # Capture the consumable requirement (if any) we are about to spend,
        # so we can mirror the unlock to the neighbor after use.
        di_pre = rs.current_doors().get(direction)
        consumed_req = None
        if di_pre and di_pre.pass_reqs and di_pre.pass_reqs[0].is_consumable:
            consumed_req = di_pre.pass_reqs[0].name

        if not rs.use_door(direction): return (False, "Failed to use door.")
        di = rs.current_doors().get(direction)
        old_map, old_x, old_y, old_z = self.player.map_name, self.player.x, self.player.y, self.player.z
        if di and di.teleport:
            t = di.teleport
            if t.map_name not in self.map.list_maps():
                return (False, f"Unknown map '{t.map_name}'.")
            target_room = self.map.load_room(t.map_name, t.x, t.y, t.z)
            if target_room is None:
                return (False, "Destination doesn't exist.")
            self.map.save_room_state(old_map, old_x, old_y, old_z, rs.room)
            self.player.map_name = t.map_name
            self.player.x, self.player.y, self.player.z = t.x, t.y, t.z
            self.player.zone = self._find_zone_for_entrance(target_room, t.entrance_dir)
            self.load_current_room()
            self.last_move_dir = direction
            return (True, f"Teleported to {t.map_name} ({t.x},{t.y},{t.z}).")
        else:
            dx=dy=dz=0
            if direction=='N': dy=1
            elif direction=='S': dy=-1
            elif direction=='E': dx=1
            elif direction=='W': dx=-1
            elif direction=='U': dz=1
            elif direction=='D': dz=-1
            new_x, new_y, new_z = old_x+dx, old_y+dy, old_z+dz
            dims = self.map.get_map_dimensions(self.player.map_name)
            if not (0 <= new_x < dims['x_size'] and 0 <= new_y < dims['y_size'] and 0 <= new_z < dims['z_size']):
                return (False, "Out of world.")
            self.map.save_room_state(old_map, old_x, old_y, old_z, rs.room)
            if consumed_req:
                self._unlock_neighbor(old_map, new_x, new_y, new_z,
                                      OPPOSITE[direction], consumed_req)
            self.player.x, self.player.y, self.player.z = new_x, new_y, new_z
            self.player.zone = 0
            self.load_current_room()
            self.last_move_dir = direction
            return (True, f"You move {direction}.")

    def _check_death(self, emit):
        if self.player.hp > 0:
            return
        cfg = self.map.death_cfg
        emit()
        emit("You collapse.")
        if cfg["restore_hp"]:
            self.player.heal_full()
        frac = cfg["coin_loss_fraction"]
        if frac > 0 and self.player.coins > 0:
            lost = int(self.player.coins * frac)
            self.player.coins -= lost
            emit(f"You wake at the entrance. You lost {lost} coins.")
        else:
            emit("You wake at the entrance.")
        if self.player.map_name == "overworld":
            self.player.x, self.player.y, self.player.z = 0, 0, 1
        else:
            self.player.x, self.player.y, self.player.z = 0, 0, 0
        self.player.zone = 0
        self.load_current_room()

    def use_item(self, item_name, direction=None):
        heart_item   = self.map.combat["heart_item"]
        shelter_item = self.map.combat.get("shelter_item", "shelter")
        fire_item    = self.map.combat.get("fire_item", "fire")
        if item_name == fire_item:
            if direction:
                return (False, "Fire doesn't take a direction.")
            if not self.player.has_item(fire_item):
                return (False, f"You have no {fire_item}.")
            if self.player.current_room is None:
                return (False, "No room.")
            ok, msg = self.player.current_room.clear_with_fire()
            if ok:
                self.player.remove_item(fire_item, 1)
            return (ok, msg)
        if item_name == shelter_item:
            if not self.player.has_item(shelter_item):
                return (False, f"You have no {shelter_item}.")
            self.player.remove_item(shelter_item, 1)
            self.player.heal_full()
            return (True, "You rest by the fire and recover your strength.")
        if item_name == heart_item:
            if not self.player.has_item(heart_item):
                return (False, f"You have no {heart_item}.")
            self.player.remove_item(heart_item, 1)
            self.player.max_hp += 1
            self.player.hp = min(self.player.hp + 1, self.player.max_hp)
            return (True, f"Your maximum HP rises to {self.player.max_hp}.")
        if not self.player.current_room:
            return (False, "No room.")
        rs = self.player.current_room
        if item_name in SKILL_NAMES:
            if item_name == 'fight': return rs.fight_enemies()
            elif item_name == 'avoidance': return rs.avoid_enemies()
            elif item_name == 'search':
                if direction: return rs.search_zone(direction)
                else: return rs.search_zone()
            else: return (False, "Unknown skill.")
        if direction:
            return self._open_door_with_item(direction, item_name)
        else:
            candidates = []
            for d, di in rs.current_doors().items():
                if di.pass_reqs and di.pass_reqs[0].name == item_name:
                    candidates.append(d)
            if not candidates: return (False, f"No door requires {item_name}.")
            if len(candidates) > 1:
                return (False, f"Multiple doors require {item_name}; specify direction.")
            return self._open_door_with_item(candidates[0], item_name)

    def take_item(self, item_name):
        if not self.player.current_room: return (False, "No room.")
        return self.player.current_room.take_item(item_name)

    def buy_item(self, item_name):
        if not self.player.current_room: return (False, "No room.")
        return self.player.current_room.buy_item(item_name)

    def combine(self, inputs):
        """Consume inputs and grant the recipe's output. Inputs are a dict
        of {item_name: count}. Order does not matter; the recipe table is
        keyed on the sorted signature of the input set."""
        pretty = " + ".join(
            f"{n} x{c}" if c > 1 else n for n, c in sorted(inputs.items())
        )
        recipe = self.map.find_recipe(inputs)
        if recipe is None:
            return (False, f"You don't know how to combine {pretty}.")
        for name, count in inputs.items():
            if not self.player.has_item(name, count):
                return (False, f"You need {count} {name}.")
        for name, count in inputs.items():
            self.player.remove_item(name, count)
        out = recipe["output"]
        out_count = out.get("count", 1)
        self.player.grant(out["item"], out_count)
        if out_count > 1:
            return (True, f"You combine {pretty} into {out['item']} x{out_count}.")
        return (True, f"You combine {pretty} into {out['item']}.")

    def reset_game(self, emit=None):
        emit = emit or print
        for p in (self.map.player_state_path, self.map.player_json_path):
            if os.path.exists(p):
                os.remove(p)
        for map_name in self.map.list_maps():
            map_dir = os.path.join(self.map.rooms_base, map_name)
            for fname in os.listdir(map_dir):
                if fname.endswith(".state"):
                    os.remove(os.path.join(map_dir, fname))
        self.player = self.map.load_player_state()
        self.last_move_dir = None
        self.load_current_room()
        emit("Game reset. You are back at the start.")

    def describe_room(self):
        if not self.player.current_room:
            return f"Map: {self.player.map_name} | Room ({self.player.x},{self.player.y},{self.player.z}) - Empty void."
        rs = self.player.current_room
        lines = [f"Map: {self.player.map_name} | Room ({self.player.x},{self.player.y},{self.player.z})"]
        if rs.room.description: lines.append(rs.room.description)
        if len(rs.room.zones) > 1: lines.append(f"Zone {rs.current_zone+1}/{len(rs.room.zones)}")
        doors = rs.current_doors()
        visible_doors = {d: di for d, di in doors.items() if rs.is_door_visible(d)}
        if visible_doors:
            door_parts = []
            for d, di in visible_doors.items():
                s = d
                if di.reach: s += f" (reach: {di.reach.name})"
                if di.pass_reqs: s += f" (pass: {', '.join(r.name for r in di.pass_reqs)})"
                if di.teleport: s += f" -> {di.teleport.to_string()}"
                door_parts.append(s)
            lines.append("Doors: " + ", ".join(door_parts))
        else:
            lines.append("Doors: none visible")
        enemies = rs.current_enemies()
        if enemies:
            lines.append("Enemies: " + ", ".join(f"{n} x{c}" for n,c in enemies))
        items = rs.current_items()
        if items:
            item_parts = []
            for it in items:
                s = f"{it.name} x{it.count}"
                if it.price is not None:
                    s += f" ({it.price} coins)"
                if it.requirements:
                    s += f" (requires {it.requirements[0].name})"
                item_parts.append(s)
            lines.append("Items here: " + ", ".join(item_parts))
        skills = self.player.skills
        lines.append("Skills: " + ", ".join(f"{k}:{v}" for k,v in skills.items()))
        lines.append(f"HP: {self.player.hp}/{self.player.max_hp}")
        lines.append(f"Sword level: {self.player.sword_level}")
        lines.append(f"Coins: {self.player.coins}")
        goal = self.map.goal()
        if goal and goal.get("count"):
            item = goal.get("item", "crystal")
            have = self.player.inventory.get(item, 0)
            target = goal["count"]
            label = goal.get("name", "Goal")
            lines.append(f"{label}: {have}/{target}")
        inv = self.player.inventory
        lines.append("Inventory: " + (", ".join(f"{k}:{v}" for k,v in inv.items()) if inv else "empty"))
        return "\n".join(lines)

    # -------------------------------------------------------------- commands

    def handle_command(self, cmd):
        out = []
        def emit(s=""): out.append(str(s))

        def finish(quit_=False):
            if not quit_:
                self._check_death(emit)
            return (out, quit_)

        cmd = cmd.strip()
        if not cmd:
            return (out, False)

        parts = cmd.lower().split()
        action = parts[0]

        heart_item = self.map.combat["heart_item"]
        shelter_item = self.map.combat.get("shelter_item", "shelter")

        heart_item   = self.map.combat["heart_item"]
        shelter_item = self.map.combat.get("shelter_item", "shelter")
        fire_item    = self.map.combat.get("fire_item", "fire")

        is_fight = action == 'fight' or (
            action == 'use' and len(parts) >= 2 and parts[1] == 'fight')
        is_flee = action in ('flee', 'avoid') or (
            action == 'use' and len(parts) >= 2
            and parts[1] in ('avoidance', 'flee', 'avoid'))
        is_heal = action == 'use' and len(parts) >= 2 and parts[1] in (heart_item, shelter_item)
        is_fire = action == 'use' and len(parts) >= 2 and parts[1] == fire_item
        # Actions that must run *before* the enemy-block preamble. Fire
        # belongs here: it resolves the enemies itself, and it must not
        # cost an avoid roll to reach.
        is_meta = (action in ('save', 'quit', 'exit', 'reset', 'retreat')
                   or is_heal or is_fire)

        if not (is_fight or is_flee or is_meta):
            if not self._enemy_block(emit=emit):
                return finish()

        if action in ('quit', 'exit'):
            self.save_game()
            emit("Saved. Bye!")
            return (out, True)
        elif action == 'save':
            self.save_game()
            emit("Saved.")
        elif action == 'reset':
            self.reset_game(emit=emit)
        elif action == 'retreat':
            if not self.last_move_dir:
                emit("You can't retreat; you haven't moved yet.")
            else:
                back = OPPOSITE[self.last_move_dir]
                ok, msg = self.move_through_door(back)
                emit(f"You retreat. {msg}")
        elif action == 'move':
            if len(parts) < 2:
                emit("Move where?")
                return finish()
            _, msg = self.move_through_door(parts[1].upper())
            emit(msg)
        elif action == 'use':
            if len(parts) < 2:
                emit("Use what?")
                return finish()
            item = parts[1]
            direction = parts[2].upper() if len(parts) >= 3 else None
            _, msg = self.use_item(item, direction)
            emit(msg)
        elif action == 'combine' or action == 'craft' or action == 'make':
            if len(parts) < 2:
                emit("Combine what? e.g. 'combine rock rock'")
                return finish()
            inputs = {}
            for name in parts[1:]:
                inputs[name] = inputs.get(name, 0) + 1
            _, msg = self.combine(inputs)
            emit(msg)
        elif action == 'fight':
            _, msg = self.use_item('fight')
            emit(msg)
        elif action in ('flee', 'avoid'):
            _, msg = self.use_item('avoidance')
            emit(msg)
        elif action == 'take':
            if len(parts) < 2:
                emit("Take what?")
                return finish()
            item_name = parts[1]
            ok, msg = self.take_item(item_name)
            emit(msg)
            if ok:
                goal = self.map.goal()
                victory_item = goal.get("victory_item") if goal else None
                if victory_item and item_name == victory_item:
                    emit()
                    emit("=" * 52)
                    emit("  VICTORY")
                    emit("=" * 52)
                    emit(goal.get("victory_message", "You have saved the world."))
                    emit()
                    self.player.won = True
                    self.save_game()
                    emit("Your legend is saved. Farewell.")
                    return (out, True)
        elif action == 'buy':
            if len(parts) < 2:
                emit("Buy what?")
                return finish()
            _, msg = self.buy_item(parts[1])
            emit(msg)
        elif action == 'enter':
            if len(parts) < 2:
                emit("Enter which zone?")
                return finish()
            try:
                z = int(parts[1]) - 1
            except ValueError:
                emit("Invalid zone.")
                return finish()
            if self.player.current_room and self.player.current_room.enter_zone(z):
                emit(f"Moved to zone {z+1}.")
            else:
                emit("Cannot enter that zone.")
        else:
            emit("Unknown command.")
        return finish()

    # ------------------------------------------------------------- plain loop

    def run(self):
        print(f"=== {PROGRAM_NAME} - {self.game_name} ===")
        print("Commands: move <N/E/S/W/U/D>, retreat, use <item/skill> [direction], "
              "take <item>, buy <item>, combine <item> <item> [...], "
              "enter <zone>, fight, flee, save, reset, quit")
        while True:
            print("\n" + self.describe_room())
            try:
                cmd = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            out, quit_ = self.handle_command(cmd)
            for line in out:
                print(line)
            if quit_:
                break


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def main(argv):
    args = list(argv)
    use_tui = False
    if "--tui" in args:
        args.remove("--tui")
        use_tui = True
    if "--no-tui" in args:
        args.remove("--no-tui")
        use_tui = False

    base_dir = args[-1] if args else "./"
    if not os.path.isdir(base_dir):
        print(f"Error: directory '{base_dir}' does not exist.")
        return 1

    game_name = os.path.basename(os.path.abspath(base_dir))
    try:
        session = GameSession(base_dir, game_name)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    if use_tui:
        try:
            from pydventure_tui import run_tui
            run_tui(session)
            return 0
        except ImportError as e:
            print(f"TUI unavailable ({e}); falling back to plain.")
        except Exception as e:
            print(f"TUI crashed ({e}); falling back to plain.")

    session.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))