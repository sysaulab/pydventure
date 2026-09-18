#!/usr/bin/env python3
"""pydventure_mazemaker - generate a multi-level pydventure world.

Usage:
    python pydventure_mazemaker.py --config mygame/world.json --out mygame/rooms
"""

import argparse, hashlib, json, os, random, sys
from collections import deque

DIRS = ['N', 'E', 'S', 'W']
DELTA = {'N': (0, 1), 'S': (0, -1), 'E': (1, 0), 'W': (-1, 0)}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
DIR_NAMES = {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west',
             'U': 'up', 'D': 'down'}


def seed_from_any(s):
    try: return int(s)
    except (TypeError, ValueError):
        return int(hashlib.sha256(str(s).encode()).hexdigest()[:16], 16)


def weighted_choice(rng, options):
    total = sum(w for _, w in options)
    r = rng.random() * total
    acc = 0.0
    for key, w in options:
        acc += w
        if r < acc: return key
    return options[-1][0]


def bfs_distances(maze, start):
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for d, nx, ny in maze.neighbors(x, y):
            if maze.walls[(x, y)][d]: continue
            if (nx, ny) in dist: continue
            dist[(nx, ny)] = dist[(x, y)] + 1
            q.append((nx, ny))
    return dist


class Maze:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.walls = {(x, y): {'N': True, 'E': True, 'S': True, 'W': True}
                      for y in range(h) for x in range(w)}

    def in_bounds(self, x, y): return 0 <= x < self.w and 0 <= y < self.h

    def neighbors(self, x, y):
        for d in DIRS:
            dx, dy = DELTA[d]
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                yield d, nx, ny

    def open_wall(self, x, y, d):
        dx, dy = DELTA[d]
        nx, ny = x + dx, y + dy
        if not self.in_bounds(nx, ny): return
        self.walls[(x, y)][d] = False
        self.walls[(nx, ny)][OPPOSITE[d]] = False

    def exits(self, x, y):
        return [d for d in DIRS if not self.walls[(x, y)][d]]

    def is_dead_end(self, x, y):
        return len(self.exits(x, y)) == 1

    def carve(self, rng):
        start = (rng.randrange(self.w), rng.randrange(self.h))
        visited = {start}
        stack = [start]
        while stack:
            x, y = stack[-1]
            unvisited = [(d, nx, ny) for d, nx, ny in self.neighbors(x, y)
                         if (nx, ny) not in visited]
            if not unvisited:
                stack.pop(); continue
            d, nx, ny = rng.choice(unvisited)
            self.open_wall(x, y, d)
            visited.add((nx, ny))
            stack.append((nx, ny))

    def braid(self, rng, amount):
        dead = [(x, y) for y in range(self.h) for x in range(self.w)
                if self.is_dead_end(x, y)]
        rng.shuffle(dead)
        n = int(len(dead) * amount)
        for x, y in dead[:n]:
            cands = [(d, nx, ny) for d, nx, ny in self.neighbors(x, y)
                     if self.walls[(x, y)][d]]
            if not cands: continue
            d, nx, ny = rng.choice(cands)
            self.open_wall(x, y, d)


class Level:
    def __init__(self, cfg, world_cfg, rng):
        self.cfg = cfg
        self.world = world_cfg
        self.rng = rng
        self.descr_rng = random.Random(seed_from_any(
            f"{world_cfg['seed']}:{cfg['name']}:descr"))
        self.name = cfg["name"]
        self.kind = cfg["kind"]
        self.width = cfg["width"]
        self.height = cfg["height"]
        self.depth = cfg["depth"]
        self.floors = {}
        self.terrains = {}
        self.enemies = {}
        self.items = {}
        self.features = {}
        self.door_reqs = {}   # (x,y,z,dir) -> req
        self.teleports = {}   # (x,y,z,dir) -> target
        self.descriptions = {}

    # -------------------------------------------------------------- generate

    def generate(self):
        self._carve()
        self._assign_terrain()
        if self.kind == "overworld":
            self._place_stairs()
            self._place_shops()
            self._place_loose_items()
            self._clear_start()
        elif self.kind == "dungeon":
            self._place_crystal()
        elif self.kind == "shrine":
            self._place_shrine()
        self._place_resources()
        self._place_ore()
        self._place_enemies()
        # Bomb walls placed last so they don't disturb dead-end
        # calculations used by swords / crystals / shrines. Opening a
        # previously closed wall can only increase connectivity, so the
        # maze stays traversable from the entrance.
        self._place_bomb_walls()

    def _carve(self):
        for z in range(self.depth):
            m = Maze(self.width, self.height)
            m.carve(self.rng)
            m.braid(self.rng, self.cfg.get("braid", 0.25))
            self.floors[z] = m

    def _assign_terrain(self):
        for z in range(self.depth):
            pool = []
            for tname, tdata in sorted(self.world["terrains"].items()):
                if tdata.get("kind") != self.kind: continue
                if z not in tdata.get("floors", []): continue
                pool.append((tname, tdata["weight"]))
            if not pool: continue
            for y in range(self.height):
                for x in range(self.width):
                    self.terrains[(x, y, z)] = weighted_choice(self.rng, pool)

    def _empty_cells(self, z):
        cells = [(x, y) for y in range(self.height) for x in range(self.width)
                 if not self.features.get((x, y, z))
                 and not self.items.get((x, y, z))
                 and not self.enemies.get((x, y, z))]
        self.rng.shuffle(cells)
        return cells

    def _place_stairs(self):
        count = self.cfg.get("features", {}).get("stair_pairs", 0)
        if self.depth < 2 or count == 0: return
        cands = [(x, y) for y in range(self.height) for x in range(self.width)]
        self.rng.shuffle(cands)
        pairs = [(z, z + 1) for z in range(self.depth - 1)]
        placed = 0
        for x, y in cands:
            if placed >= count: break
            z_lo, z_hi = self.rng.choice(pairs)
            if (self.features.get((x, y, z_lo)) or
                self.features.get((x, y, z_hi))): continue
            self.features.setdefault((x, y, z_lo), []).append("stairs_up")
            self.features.setdefault((x, y, z_hi), []).append("stairs_down")
            placed += 1

    def _place_shops(self):
        for shop in self.cfg.get("features", {}).get("shops", []):
            z = shop.get("floor", 0)
            if z >= self.depth: continue
            cells = self._empty_cells(z)
            if not cells: continue
            x, y = cells[0]
            self.features.setdefault((x, y, z), []).append("shop")
            self.items.setdefault((x, y, z), []).extend(shop.get("items", []))

    def _place_swords(self):
        spec = self.cfg.get("features", {}).get("swords")
        if not spec: return
        count = spec.get("count", 3)
        floors = spec.get("floors", [1])
        guards = spec.get("guarded_by", [])
        cands = []
        for z in floors:
            if z >= self.depth: continue
            m = self.floors[z]
            for y in range(self.height):
                for x in range(self.width):
                    if (m.is_dead_end(x, y)
                            and not self.features.get((x, y, z))
                            and not self.items.get((x, y, z))
                            and not self.enemies.get((x, y, z))):
                        cands.append((x, y, z))
        self.rng.shuffle(cands)
        for x, y, z in cands[:count]:
            self.items.setdefault((x, y, z), []).append("sword")
            if guards:
                self.enemies[(x, y, z)] = [self.rng.choice(guards)]

    def _place_loose_items(self):
        for spec in self.cfg.get("features", {}).get("loose_items", []):
            z = spec.get("floor", 0)
            if z >= self.depth: continue
            count = spec.get("count", 1)
            cells = self._empty_cells(z)
            if not cells: continue
            x, y = cells[0]
            payload = spec["name"]
            if count > 1: payload += f"+{count - 1}"
            self.features.setdefault((x, y, z), []).append("item")
            self.items.setdefault((x, y, z), []).append(payload)

    def _place_resources(self):
        """Sprinkle terrain-appropriate materials across the map.

        Overworld yields rock and wood. Dungeons yield ore and coal.
        """
        chance = self.cfg.get("resource_chance", 0.0)
        if chance <= 0:
            return
        table = self.world.get("terrain_resources", {})
        if not table:
            return
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    if (x, y, z) in self.items or (x, y, z) in self.features:
                        continue
                    if self.rng.random() >= chance:
                        continue
                    pool = table.get(self.terrains.get((x, y, z)), [])
                    if not pool:
                        continue
                    name = weighted_choice(self.rng, pool)
                    self.items[(x, y, z)] = [name]

    def _place_bomb_walls(self):
        """Open N currently closed interior walls and gate them on both
        sides with a `bomb-1` requirement. The runtime unlocks both sides
        the first time a bomb is spent, so the wall is one-way expensive
        and two-way free."""
        count = self.cfg.get("bomb_walls", 0)
        if count <= 0:
            return
        for z in range(self.depth):
            m = self.floors[z]
            placed = 0
            attempts = 0
            while placed < count and attempts < 200:
                attempts += 1
                x = self.rng.randrange(self.width)
                y = self.rng.randrange(self.height)
                walled = [d for d in "NESW"
                          if m.walls[(x, y)][d]
                          and m.in_bounds(x + DELTA[d][0], y + DELTA[d][1])]
                if not walled:
                    continue
                d = self.rng.choice(walled)
                dx, dy = DELTA[d]
                nx, ny = x + dx, y + dy
                back = OPPOSITE[d]
                if (x, y, z, d) in self.door_reqs:
                    continue
                if (nx, ny, z, back) in self.door_reqs:
                    continue
                m.open_wall(x, y, d)
                self.door_reqs[(x, y, z, d)] = "bomb-1"
                self.door_reqs[(nx, ny, z, back)] = "bomb-1"
                placed += 1

    def _far_dead_end(self, z=0, avoid=(0, 0)):
        m = self.floors[z]
        dist = bfs_distances(m, avoid)
        best, best_d = None, -1
        for (x, y), d in sorted(dist.items()):
            if (x, y) == avoid: continue
            if not m.is_dead_end(x, y): continue
            if d > best_d:
                best_d, best = d, (x, y)
        if best is None:
            for (x, y), d in sorted(dist.items()):
                if (x, y) == avoid: continue
                if d > best_d:
                    best_d, best = d, (x, y)
        return best

    def _place_crystal(self):
        if not self.cfg.get("crystal"): return
        cell = self._far_dead_end()
        if cell is None: return
        x, y = cell
        self.items.setdefault((x, y, 0), []).append("crystal")
        self.features.setdefault((x, y, 0), []).append("crystal_chamber")
        self.enemies[(x, y, 0)] = [self.cfg.get("boss", "dragon")]

    def _place_shrine(self):
        cfg = self.cfg.get("shrine")
        if not cfg: return
        cell = self._far_dead_end()
        if cell is None: return
        sx, sy = cell
        m = self.floors[0]
        ex = m.exits(sx, sy)
        if not ex: return
        ed = ex[0]
        dx, dy = DELTA[ed]
        nx, ny = sx + dx, sy + dy
        if not m.in_bounds(nx, ny): return
        back = OPPOSITE[ed]
        self.door_reqs[(nx, ny, 0, back)] = cfg["requires"]
        self.items.setdefault((sx, sy, 0), []).append(cfg["victory_item"])
        self.features.setdefault((sx, sy, 0), []).append("shrine")
        if self.cfg.get("boss"):
            self.enemies[(sx, sy, 0)] = [self.cfg["boss"]]

    def _place_enemies(self):
        density = self.cfg.get("enemy_density")
        chance  = self.cfg.get("enemy_chance")
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    if (x, y, z) in self.enemies:
                        continue
                    tname = self.terrains.get((x, y, z))
                    if tname is None:
                        continue
                    pool = self.world["terrains"].get(tname, {}).get("enemies", [])
                    if not pool:
                        continue
                    if density is not None:
                        # Triangular distribution: mean = density,
                        # peak at density, range 0..2*density.
                        count = (self.rng.randint(0, density)
                                 + self.rng.randint(0, density))
                        if count <= 0:
                            continue
                        self.enemies[(x, y, z)] = [
                            self.rng.choice(pool) for _ in range(count)
                        ]
                    elif chance is not None:
                        if self.rng.random() >= chance:
                            continue
                        self.enemies[(x, y, z)] = [self.rng.choice(pool)]

    def _place_ore(self):
        """Place exactly ore_count ore cells. Runs after _place_resources
        so it can't overwrite coal or items, and after _place_crystal so
        the crystal cell is already marked. Enemies may still land on the
        ore cell via _place_enemies (called later) -- a guarded ore is a
        feature, not a bug."""
        count = self.cfg.get("ore_count", 0)
        if count <= 0:
            return
        for z in range(self.depth):
            placed = 0
            attempts = 0
            while placed < count and attempts < 500:
                attempts += 1
                x = self.rng.randrange(self.width)
                y = self.rng.randrange(self.height)
                if (x, y, z) in self.items or (x, y, z) in self.features:
                    continue
                self.items[(x, y, z)] = ["ore"]
                placed += 1

    def _clear_start(self):
        sx, sy, sz = self.cfg.get("start", [0, 0, 0])
        self.enemies.pop((sx, sy, sz), None)

    # -------------------------------------------------------------- linking

    def set_teleport(self, x, y, z, direction, target):
        self.teleports[(x, y, z, direction)] = target

    # ----------------------------------------------------------- describing

    def compose_descriptions(self):
        patterns = (self.world["description_sets"]
                    .get(self.cfg.get("description_set", "overworld"), {})
                    .get("patterns", []))
        if not patterns:
            patterns = ["You are in {terrain}."]
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    self.descriptions[(x, y, z)] = self._describe(x, y, z, patterns)

    def _describe(self, x, y, z, patterns):
        tname = self.terrains.get((x, y, z), "?")
        terrain = self.world["terrains"].get(tname, {}).get("description", tname)
        feats = self.features.get((x, y, z), [])
        m = self.floors[z]
        exits = list(m.exits(x, y))
        for d in "UD":
            tp = self.teleports.get((x, y, z, d))
            if tp: exits.append(d)
            else:
                key = "stairs_up" if d == "U" else "stairs_down"
                if key in feats: exits.append(d)
        exits_text = self._format_exits(exits)
        feature_text = "".join(self.world["feature_phrases"].get(f, "") for f in feats)
        pattern = patterns[self.descr_rng.randrange(len(patterns))]
        return pattern.format(
            terrain=terrain,
            Terrain=terrain[:1].upper() + terrain[1:] if terrain else "",
            exits=exits_text,
            Exits=exits_text[:1].upper() + exits_text[1:] if exits_text else "",
            feature=feature_text,
        )

    @staticmethod
    def _format_exits(exits):
        words = [DIR_NAMES[e] for e in exits if e in DIR_NAMES]
        if not words: return "nowhere"
        if len(words) == 1: return words[0]
        if len(words) == 2: return f"{words[0]} and {words[1]}"
        return ", ".join(words[:-1]) + ", and " + words[-1]

    # --------------------------------------------------------------- output

    def room_flow(self, x, y, z):
        m = self.floors[z]
        parts = []
        for d in "NESW":
            if m.walls[(x, y)][d]: continue
            req = self.door_reqs.get((x, y, z, d))
            parts.append(f"{d}[{req}]" if req else d)
        for d in "UD":
            tp = self.teleports.get((x, y, z, d))
            if tp:
                parts.append(f"{d}{tp}")
            else:
                feats = self.features.get((x, y, z), [])
                key = "stairs_up" if d == "U" else "stairs_down"
                if key in feats: parts.append(d)
        enemies = self.enemies.get((x, y, z))
        if enemies:
            if isinstance(enemies, str): enemies = [enemies]
            parts.append("{" + ",".join(enemies) + "}")
        items = self.items.get((x, y, z))
        if items:
            parts.append("(" + ",".join(items) + ")")
        return "".join(parts)

    def write(self, out_dir, keep_existing=False):
        os.makedirs(out_dir, exist_ok=True)
        n = 0
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    path = os.path.join(out_dir, f"{x}_{y}_{z}.room")
                    if keep_existing and os.path.exists(path): continue
                    flow = self.room_flow(x, y, z)
                    desc = self.descriptions.get((x, y, z), "")
                    with open(path, "w") as f:
                        f.write(flow + "\n" + desc + "\n")
                    n += 1
        return n


class World:
    def __init__(self, config):
        self.cfg = config
        self.rng = random.Random(seed_from_any(config["seed"]))
        self.levels = {}

    def generate(self):
        for mcfg in self.cfg["maps"]:
            lvl = Level(mcfg, self.cfg, self.rng)
            lvl.generate()
            self.levels[mcfg["name"]] = lvl
        self._link_dungeons()
        for lvl in self.levels.values():
            lvl.compose_descriptions()

    def _link_dungeons(self):
        ow = self.levels.get("overworld")
        if not ow: return
        m = ow.floors[0]
        used = set()
        cells = [(x, y) for y in range(ow.height) for x in range(ow.width)]
        dead = [c for c in cells if m.is_dead_end(*c)]
        other = [c for c in cells if c not in dead]
        self.rng.shuffle(dead)
        self.rng.shuffle(other)
        ordered = dead + other

        for name, lvl in self.levels.items():
            if name == "overworld": continue
            cell = next((c for c in ordered if c not in used), None)
            if cell is None: continue
            used.add(cell)
            ox, oy = cell

            dm = lvl.floors[0]
            dm_exits = dm.exits(0, 0)
            if not dm_exits: continue
            entry_dir = dm_exits[0]

            ow_exits = m.exits(ox, oy)
            back_dir = ow_exits[0] if ow_exits else 'N'

            ow.set_teleport(ox, oy, 0, 'D',
                            f"<{name}:0,0,0,{entry_dir}>")
            lvl.set_teleport(0, 0, 0, 'U',
                             f"<overworld:{ox},{oy},0,{back_dir}>")

    def write(self, rooms_base, keep_existing=False):
        total = 0
        for name, lvl in self.levels.items():
            out = os.path.join(rooms_base, name)
            n = lvl.write(out, keep_existing=keep_existing)
            print(f"  {name}: {n} rooms")
            total += n
        return total


def generate_from_config(config_path, rooms_base, keep_existing=False):
    with open(config_path) as f:
        cfg = json.load(f)
    w = World(cfg)
    w.generate()
    return w.write(rooms_base, keep_existing=keep_existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-existing", action="store_true")
    args = ap.parse_args()
    generate_from_config(args.config, args.out, args.keep_existing)


if __name__ == "__main__":
    main()