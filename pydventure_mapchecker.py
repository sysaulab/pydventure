#!/usr/bin/env python3
"""List rooms in a pydventure map directory and flag dangling exits.

Usage: python mapcheck.py [map_directory]
"""
import os, re, sys

DIRS = "NESWUD"
DELTA = {'N': (0, 1, 0), 'S': (0, -1, 0), 'E': (1, 0, 0),
         'W': (-1, 0, 0), 'U': (0, 0, 1), 'D': (0, 0, -1)}

def read_exits(path):
    with open(path) as f:
        line = f.readline().strip()
    exits = set()
    depth = 0
    for ch in line:
        if ch in "[{(<":
            depth += 1
        elif ch in "]})>":
            depth -= 1
        elif depth == 0 and ch in DIRS:
            exits.add(ch)
    return exits

def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "rooms/overworld"
    rooms = {}
    pat = re.compile(r'^(\d+)_(\d+)_(\d+)\.room$')
    for fname in os.listdir(base):
        m = pat.match(fname)
        if m:
            x, y, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
            rooms[(x, y, z)] = read_exits(os.path.join(base, fname))

    if not rooms:
        print(f"no .room files in {base}")
        return

    zs = sorted({k[2] for k in rooms})
    for z in zs:
        print(f"\n=== z={z} ===")
        zrooms = sorted((k for k in rooms if k[2] == z), key=lambda k: (k[1], k[0]))
        for k in zrooms:
            x, y, _ = k
            ex = rooms[k]
            dangling = []
            for d in sorted(ex):
                dx, dy, dz = DELTA[d]
                if (x + dx, y + dy, z + dz) not in rooms:
                    dangling.append(d)
            line = f"({x},{y},{z})  exits={''.join(sorted(ex)) or '-':<6}"
            if dangling:
                line += f"  dangling: {''.join(sorted(dangling))}"
            print(line)

    # Also flag one-way inconsistencies: a room has an exit E, but the
    # room to the east has no W exit back.
    print("\n=== one-way exits ===")
    found = False
    for (x, y, z), ex in sorted(rooms.items()):
        for d in ex:
            dx, dy, dz = DELTA[d]
            nb = (x + dx, y + dy, z + dz)
            if nb not in rooms:
                continue  # dangling, already reported
            opposite = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E', 'U': 'D', 'D': 'U'}[d]
            if opposite not in rooms[nb]:
                print(f"  ({x},{y},{z}) has {d} -> {nb}, but {nb} has no {opposite} back")
                found = True
    if not found:
        print("  none")

if __name__ == "__main__":
    main()