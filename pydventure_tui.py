#!/usr/bin/env python3
"""pydventure_tui - a curses front-end for pydventure.

Imports GameSession and replaces only its presentation layer.
All parsing, combat, movement, and save/load logic is unchanged.

Usage:
    python pydventure_tui.py mygame
    python pydventure.py mygame --tui
"""

import curses
import locale
import os
import sys

from pydventure import GameSession


# ------------------------------------------------------------- color pairs

C_DEFAULT     = 0
C_HEADER      = 1
C_STATUS      = 2
C_DOOR_OPEN   = 3
C_DOOR_LOCKED = 4
C_DOOR_HIDDEN = 5
C_ENEMY       = 6
C_ITEM        = 7
C_QUEST       = 8
C_FEATURE     = 9
C_DIM         = 10
C_PROMPT      = 11
C_WARN        = 12
C_GOOD        = 13
C_LOG         = 14


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass

    def pair(n, fg, bg=-1):
        try:
            curses.init_pair(n, fg, bg)
        except curses.error:
            pass

    pair(C_HEADER,      curses.COLOR_CYAN,    -1)
    pair(C_STATUS,      curses.COLOR_BLACK,   curses.COLOR_CYAN)
    pair(C_DOOR_OPEN,   curses.COLOR_GREEN,   -1)
    pair(C_DOOR_LOCKED, curses.COLOR_YELLOW,  -1)
    pair(C_DOOR_HIDDEN, curses.COLOR_BLACK,   -1)
    pair(C_ENEMY,       curses.COLOR_RED,     -1)
    pair(C_ITEM,        curses.COLOR_MAGENTA, -1)
    pair(C_QUEST,       curses.COLOR_YELLOW,  -1)
    pair(C_FEATURE,     curses.COLOR_CYAN,    -1)
    pair(C_DIM,         curses.COLOR_BLACK,   -1)
    pair(C_PROMPT,      curses.COLOR_GREEN,   -1)
    pair(C_WARN,        curses.COLOR_RED,     -1)
    pair(C_GOOD,        curses.COLOR_GREEN,   -1)
    pair(C_LOG,         curses.COLOR_WHITE,   -1)


def attr(pair_id):
    return curses.color_pair(pair_id)


# ---------------------------------------------------------------- helpers

def wrap(text, width):
    if width <= 0:
        return [text]
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def room_lines(session, width):
    """Yield (pair_id, text) pairs describing the current room."""
    p = session.player
    rs = p.current_room

    if rs is None:
        yield (C_WARN, f"  Empty void at ({p.x},{p.y},{p.z}).")
        return

    if rs.room.description:
        for line in wrap(rs.room.description, width - 4):
            yield (C_DEFAULT, "  " + line)
        yield (C_DEFAULT, "")

    if len(rs.room.zones) > 1:
        yield (C_DIM, f"  Zone {rs.current_zone+1}/{len(rs.room.zones)}")
        yield (C_DEFAULT, "")

    doors = rs.current_doors()
    if doors:
        yield (C_HEADER, "  Doors")
        for d in "NESWUD":
            di = doors.get(d)
            if di is None:
                continue
            if not rs.is_door_visible(d):
                yield (C_DOOR_HIDDEN, f"    [{d}] ???")
                continue
            locked = bool(di.pass_reqs)
            style = C_DOOR_LOCKED if locked else C_DOOR_OPEN
            label = "open"
            if di.pass_reqs:
                label = "locked: " + ", ".join(r.name for r in di.pass_reqs)
            extra = ""
            if di.reach:
                extra += f"  reach: {di.reach.name}"
            if di.teleport:
                extra += f"  -> {di.teleport.to_string()}"
            yield (style, f"    [{d}] {label}{extra}")
        yield (C_DEFAULT, "")

    enemies = rs.current_enemies()
    if enemies:
        ep = rs._enemy_power(enemies)
        yield (C_HEADER, "  Enemies")
        for name, count in enemies:
            diff = session.map.difficulty(name)
            yield (C_ENEMY, f"    {name} x{count}   diff {diff} each")
        yield (C_ENEMY, f"    total EP {ep}")
        yield (C_DEFAULT, "")

    items = rs.current_items()
    if items:
        yield (C_HEADER, "  Items")
        for it in items:
            style = C_QUEST if it.name in ("crystal", "victory") else C_ITEM
            line = f"    {it.name} x{it.count}"
            if it.price is not None:
                line += f"   ({it.price} coins)"
            if it.requirements:
                line += f"   [requires {it.requirements[0].name}]"
            yield (style, line)
        yield (C_DEFAULT, "")


def status_line(session):
    p = session.player
    parts = [f"{session.game_name}"]
    parts.append(f"({p.x},{p.y},{p.z})")
    parts.append(f"coins {p.coins}")
    parts.append(f"sword {p.sword_level}")
    goal = session.map.goal()
    if goal and goal.get("count"):
        item = goal.get("item", "crystal")
        have = p.inventory.get(item, 0)
        parts.append(f"{item} {have}/{goal['count']}")
    parts.append(f"hp {p.hp}/{p.max_hp}")
    skills = p.skills
    parts.append("skills " + "/".join(f"{k[0]}{v}" for k, v in skills.items()))
    inv = p.inventory
    if inv:
        parts.append("inv " + " ".join(f"{k}:{v}" for k, v in inv.items()))
    return "  |  ".join(parts)


def log_lines(log, width):
    yield (C_HEADER, "  Log")
    if not log:
        yield (C_DIM, "    (nothing yet)")
        return
    for entry in log[-6:]:
        for line in wrap(entry, width - 4):
            yield (C_LOG, "    " + line)


# ----------------------------------------------------------------- the UI

class TUI:
    def __init__(self, session):
        self.session = session
        self.log = []
        self.history = []
        self.hist_idx = 0

    def draw(self, stdscr):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 12 or w < 40:
            try:
                stdscr.addstr(0, 0, "terminal too small")
                stdscr.refresh()
            except curses.error:
                pass
            return

        # Row 0: status bar
        status = status_line(self.session)[: w - 1]
        try:
            stdscr.addstr(0, 0, status.ljust(w - 1),
                          attr(C_STATUS) | curses.A_BOLD)
        except curses.error:
            pass

        sep = "─" * (w - 1)

        # Reserve log rows based on terminal size. The log gets as many
        # rows as fit; the room pane gets the rest.
        log_rows = 8
        if h < 22:
            log_rows = 5
        if h < 16:
            log_rows = 3

        log_end   = h - 3             # last row used by the log
        log_start = log_end - log_rows + 1
        mid_sep   = log_start - 1
        room_start = 2
        room_end   = mid_sep - 1

        # --- room pane
        room = list(room_lines(self.session, w))
        room_rows = max(0, room_end - room_start + 1)
        for i, (pair_id, text) in enumerate(room[:room_rows]):
            try:
                stdscr.addstr(room_start + i, 0, text[: w - 1], attr(pair_id))
            except curses.error:
                pass

        try:
            stdscr.addstr(mid_sep, 0, sep, attr(C_DIM))
        except curses.error:
            pass

        # --- log pane: walk newest-first, collecting wrapped lines until
        # we have filled log_rows. Then reverse so they draw top-down.
        rendered = []
        for entry in reversed(self.log):
            for line in reversed(wrap(entry, w - 4)):
                rendered.append("    " + line)
                if len(rendered) >= log_rows:
                    break
            if len(rendered) >= log_rows:
                break
        rendered.reverse()

        # Bottom-align: newest line sits on the last log row.
        pad = log_rows - len(rendered)
        for i, text in enumerate(rendered):
            try:
                stdscr.addstr(log_start + pad + i, 0,
                              text[: w - 1], attr(C_LOG))
            except curses.error:
                pass

        try:
            stdscr.addstr(h - 2, 0, sep, attr(C_DIM))
        except curses.error:
            pass

        stdscr.refresh()



        
    def read_command(self, stdscr):
        h, w = stdscr.getmaxyx()
        prompt = "> "
        buf = []
        pos = 0

        while True:
            try:
                stdscr.move(h - 1, 0)
                stdscr.clrtoeol()
                display = prompt + "".join(buf)
                stdscr.addstr(h - 1, 0, display[: w - 1],
                              attr(C_PROMPT) | curses.A_BOLD)
                stdscr.move(h - 1, min(len(prompt) + pos, w - 2))
                stdscr.refresh()
            except curses.error:
                pass

            ch = stdscr.getch()

            if ch in (10, 13, curses.KEY_ENTER):
                return "".join(buf)
            elif ch == 27:
                # ESC: clear buffer
                buf = []
                pos = 0
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if pos > 0:
                    buf.pop(pos - 1)
                    pos -= 1
            elif ch == curses.KEY_DC:
                if pos < len(buf):
                    buf.pop(pos)
            elif ch == curses.KEY_LEFT:
                pos = max(0, pos - 1)
            elif ch == curses.KEY_RIGHT:
                pos = min(len(buf), pos + 1)
            elif ch == curses.KEY_HOME:
                pos = 0
            elif ch == curses.KEY_END:
                pos = len(buf)
            elif ch == curses.KEY_UP:
                if self.history:
                    self.hist_idx = max(0, self.hist_idx - 1)
                    buf = list(self.history[self.hist_idx])
                    pos = len(buf)
            elif ch == curses.KEY_DOWN:
                if self.history:
                    self.hist_idx = min(len(self.history), self.hist_idx + 1)
                    if self.hist_idx < len(self.history):
                        buf = list(self.history[self.hist_idx])
                    else:
                        buf = []
                    pos = len(buf)
            elif ch == curses.KEY_RESIZE:
                return ""
            elif 32 <= ch < 127:
                buf.insert(pos, chr(ch))
                pos += 1

    def run(self, stdscr):
        locale.setlocale(locale.LC_ALL, "")
        init_colors()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        stdscr.keypad(True)

        self.log.append(f"Welcome to {self.session.game_name}.")
        self.log.append("Try: move n, search, fight, take crystal, save, quit")

        while True:
            self.draw(stdscr)
            cmd = self.read_command(stdscr)
            if not cmd or not cmd.strip():
                continue
            self.history.append(cmd)
            self.hist_idx = len(self.history)
            self.log.append(f"> {cmd}")
            out, quit_ = self.session.handle_command(cmd)
            for line in out:
                self.log.append(line)
            if quit_:
                self.draw(stdscr)
                try:
                    h, w = stdscr.getmaxyx()
                    stdscr.addstr(h - 1, 0, " — press any key — "[: w - 1],
                                  attr(C_PROMPT))
                    stdscr.refresh()
                    stdscr.getch()
                except curses.error:
                    pass
                return


def run_tui(session):
    curses.wrapper(TUI(session).run)


def main(argv):
    if not argv:
        print("usage: pydventure_tui.py <game_directory>")
        return 1
    base_dir = argv[-1]
    if not os.path.isdir(base_dir):
        print(f"Error: directory '{base_dir}' does not exist.")
        return 1
    game_name = os.path.basename(os.path.abspath(base_dir))
    session = GameSession(base_dir, game_name)
    run_tui(session)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))