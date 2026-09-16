#!/usr/bin/env python3
"""pydventure_mapdrawer - render a maze as Unicode box-drawing art.

Two-space horizontal corridors, one-row vertical corridors, box-drawing
junctions. Works on anything with the shape:

    walls[(x, y)] = {'N': bool, 'E': bool, 'S': bool, 'W': bool}
        True  = wall present
        False = passage open
"""


# (up, right, down, left) -> character
_JUNCTIONS = {
    (1, 1, 1, 1): "┼",
    (1, 1, 1, 0): "├",
    (1, 1, 0, 1): "┴",
    (1, 1, 0, 0): "└",
    (1, 0, 1, 1): "┤",
    (1, 0, 1, 0): "│",
    (1, 0, 0, 1): "┘",
    (1, 0, 0, 0): "╵",
    (0, 1, 1, 1): "┬",
    (0, 1, 1, 0): "┌",
    (0, 1, 0, 1): "─",
    (0, 1, 0, 0): "╶",
    (0, 0, 1, 1): "┐",
    (0, 0, 1, 0): "╷",
    (0, 0, 0, 1): "╴",
    (0, 0, 0, 0): " ",
}

_ASCII = {
    "┼": "+", "├": "+", "┤": "+", "┬": "+", "┴": "+",
    "┌": "+", "┐": "+", "└": "+", "┘": "+",
    "─": "-", "│": "|",
    "╵": "|", "╷": "|", "╶": "-", "╴": "-",
    "\u2191": "^", "\u2193": "v",
}


def render_maze(walls, width, height, marks=None, axis=True, ascii_only=False):
    """
    Render a maze as Unicode box art.

    walls:       dict {(x, y): {'N': bool, 'E': bool, 'S': bool, 'W': bool}}
    width,height: grid size
    marks:       optional dict {(x, y): str | (str, ...)} — a single char
                 (or a tuple whose first element is a char) drawn in that cell
    axis:        if True, prefix y-labels and prepend an x-label row
    ascii_only:  fall back to +, -, | if Unicode isn't welcome
    """
    marks = marks or {}

    def has_wall(x, y, d):
        return walls[(x, y)][d]

    def vwall_at(i, y):
        """Vertical wall at column boundary i (0..width), in cell row y."""
        if i == 0:
            return has_wall(0, y, 'W')
        if i == width:
            return has_wall(width - 1, y, 'E')
        return has_wall(i - 1, y, 'E')

    def hwall_at(x, j):
        """Horizontal wall at row boundary j (0..height), over cell x."""
        if j == 0:
            return has_wall(x, 0, 'S')
        if j == height:
            return has_wall(x, height - 1, 'N')
        return has_wall(x, j - 1, 'N')

    total_cols = 3 * width + 1
    total_rows = 2 * height + 1
    grid = [[' '] * total_cols for _ in range(total_rows)]

    # Boundary rows: junctions + horizontal wall segments
    for j in range(0, height + 1):
        sr = 2 * (height - j)
        for i in range(0, width + 1):
            up    = 1 if (j < height and vwall_at(i, j)) else 0
            down  = 1 if (j > 0 and vwall_at(i, j - 1)) else 0
            left  = 1 if (i > 0 and hwall_at(i - 1, j)) else 0
            right = 1 if (i < width and hwall_at(i, j)) else 0
            grid[sr][3 * i] = _JUNCTIONS[(up, right, down, left)]
        for i in range(0, width):
            seg = "──" if hwall_at(i, j) else "  "
            grid[sr][3 * i + 1] = seg[0]
            grid[sr][3 * i + 2] = seg[1]

    # Cell rows: vertical wall segments + cell content
    for y in range(0, height):
        sr = 2 * (height - 1 - y) + 1
        for i in range(0, width + 1):
            grid[sr][3 * i] = "│" if vwall_at(i, y) else " "
        for x in range(0, width):
            m = marks.get((x, y))
            if m:
                if isinstance(m, tuple):
                    left = m[0] if len(m) > 0 else ' '
                    right = m[1] if len(m) > 1 else ' '
                elif isinstance(m, str):
                    if len(m) >= 2:
                        left, right = m[0], m[1]
                    else:
                        left, right = m, ' '
                else:
                    left, right = '?', ' '
                grid[sr][3 * x + 1] = left
                grid[sr][3 * x + 2] = right

    # Assemble
    lines = []
    if axis:
        xlab = "     "  # aligns with map column 1
        for x in range(width):
            xlab += f"{x:02d}"
            if x < width - 1:
                xlab += " "
        lines.append(xlab)

    for sr in range(total_rows):
        if axis:
            if sr % 2 == 1:
                y = height - 1 - (sr // 2)
                prefix = f"{y:02d}  "
            else:
                prefix = "    "
        else:
            prefix = ""
        row = "".join(grid[sr])
        if ascii_only:
            row = "".join(_ASCII.get(c, c) for c in row)
        lines.append(prefix + row)

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Standalone entry: draw a maze straight from a rooms directory
# ----------------------------------------------------------------------

def walls_from_rooms(map_dir, z):
    """Rebuild walls and stair info for a given z-level from .room files.

    Returns (walls, width, height, stairs):
        walls  -- {(x,y): {'N': bool, 'E': bool, 'S': bool, 'W': bool}}
        stairs -- {(x,y): {'U': is_teleport, 'D': is_teleport}}
    """
    import os, re
    pat = re.compile(r'^(\d+)_(\d+)_(\d+)\.room$')
    cells = {}
    max_x = max_y = -1
    for fname in sorted(os.listdir(map_dir)):
        m = pat.match(fname)
        if not m:
            continue
        x, y, fz = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if fz != z:
            continue
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        with open(os.path.join(map_dir, fname)) as f:
            line = f.readline().strip()

        exits = set()
        teleports = set()
        depth = 0
        i = 0
        while i < len(line):
            ch = line[i]
            if ch in "[{(<":
                depth += 1
                i += 1
            elif ch in "]})>":
                depth -= 1
                i += 1
            elif depth == 0 and ch in "NESWUD":
                exits.add(ch)
                if i + 1 < len(line) and line[i + 1] == '<':
                    teleports.add(ch)
                i += 1
            else:
                i += 1
        cells[(x, y)] = (exits, teleports)

    if max_x < 0:
        return {}, 0, 0, {}

    width, height = max_x + 1, max_y + 1
    walls = {}
    stairs = {}
    for y in range(height):
        for x in range(width):
            exits, teleports = cells.get((x, y), (set(), set()))
            exists = (x, y) in cells
            walls[(x, y)] = {
                'N': (not exists) or ('N' not in exits),
                'E': (not exists) or ('E' not in exits),
                'S': (not exists) or ('S' not in exits),
                'W': (not exists) or ('W' not in exits),
            }
            if exists:
                info = {}
                if 'U' in exits:
                    info['U'] = 'U' in teleports
                if 'D' in exits:
                    info['D'] = 'D' in teleports
                if info:
                    stairs[(x, y)] = info
    return walls, width, height, stairs

def _draw_once(args):
    import os, re
    if args.all:
        zs = []
        pat = re.compile(r'^\d+_\d+_(\d+)\.room$')
        for fname in os.listdir(args.map_dir):
            m = pat.match(fname)
            if m:
                zs.append(int(m.group(1)))
        zs = sorted(set(zs))
    else:
        zs = [args.z if args.z is not None else 0]

    legend_printed = False
    for z in zs:
        walls, w, h, stairs = walls_from_rooms(args.map_dir, z)
        if not walls:
            print(f"(no rooms at z={z})")
            continue

        marks = {} if args.no_stairs else _stair_marks(stairs)
        if args.player:
            px, py = args.player
            if 0 <= px < w and 0 <= py < h:
                marks[(px, py)] = '@'

        print(f"=== z = {z} ===")
        print(render_maze(walls, w, h, marks=marks,
                          axis=not args.no_axis,
                          ascii_only=args.ascii))
        if stairs and not legend_printed and not args.no_stairs:
            arrow_up   = '^' if args.ascii else '\u2191'
            arrow_down = 'v' if args.ascii else '\u2193'
            print(f"Legend: U/D = stairs   {arrow_up}/{arrow_down} = teleport   @ = you")
            legend_printed = True
        print()

def _stair_marks(stairs):
    """Map {(x,y): {'U':bool,'D':bool}} to two-char cell marks.

    Left char carries the up exit, right char the down exit.
    Plain letters for stairs, arrows for teleports."""
    marks = {}
    for (x, y), info in stairs.items():
        left = ' '
        right = ' '
        if 'U' in info:
            left = '\u2191' if info['U'] else 'U'
        if 'D' in info:
            right = '\u2193' if info['D'] else 'D'
        if left != ' ' or right != ' ':
            marks[(x, y)] = (left, right)
    return marks


def _main():
    import argparse, os, sys, time
    p = argparse.ArgumentParser(description="Draw a pydventure map.")
    p.add_argument("map_dir", help="path to a map directory, e.g. mygame/rooms/overworld")
    p.add_argument("-z", type=int, default=None,
                   help="floor to draw (default: 0)")
    p.add_argument("--player", nargs=2, type=int, metavar=("X", "Y"),
                   help="mark the player's position with @")
    p.add_argument("--ascii", action="store_true", help="ASCII fallback")
    p.add_argument("--no-axis", action="store_true", help="hide axis labels")
    p.add_argument("--no-stairs", action="store_true",
                   help="hide U/D and teleport markers")
    p.add_argument("--all", action="store_true", help="draw every floor")
    p.add_argument("--watch", action="store_true",
                   help="redraw when any .room file changes (Ctrl-C to exit)")
    p.add_argument("--interval", type=float, default=1.0,
                   help="watch poll interval in seconds (default 1.0)")
    args = p.parse_args()

    if not os.path.isdir(args.map_dir):
        print(f"error: {args.map_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if args.watch:
        _watch_loop(args)
    else:
        _draw_once(args)


if __name__ == "__main__":
    _main()