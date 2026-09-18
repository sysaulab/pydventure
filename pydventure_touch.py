#!/usr/bin/env python3
"""pydventure_touch - a tkinter front-end for pydventure.

A room visual: procedural terrain art on a Canvas with a compass rose of
door buttons around the edges and the description panel in the middle.
The log is drawn directly on the canvas as white (and tinted) text, so
it superimposes over the terrain without a widget background.

Terrain is chosen by scanning the room's description for known keywords
("forest", "lake bed", "stone hall", ...). The engine never needs to
expose a terrain name.

Only stdlib. Drives GameSession via handle_command.

Usage:
    python pydventure_touch.py mygame
"""

import os
import random
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from pydventure import GameSession


# ------------------------------------------------------------------ palette

BG_PANEL         = "#0e1218"
BG_BUTTON        = "#1a2838"
BG_BUTTON_HOVER  = "#26394e"
BG_BUTTON_ACTIVE = "#0a1828"
FG_OPEN          = "#004608"
FG_LOCKED        = "#704c00"
FG_TEXT          = "#38383a"
FG_DIM           = "#8892a0"
FG_TITLE         = "#e8c67f"
FG_GOOD          = "#9de8a8"
FG_BAD           = "#e89090"
FG_PROMPT        = "#7fb8e8"

FONT_SIZE = 14

# Log entry tag -> colour, used when drawing log lines on the canvas
LOG_COLORS = {
    None:     "#f4f4f6",   # plain: near white
    "title":  FG_TITLE,
    "good":   FG_GOOD,
    "bad":    FG_BAD,
    "dim":    "#8892a0",
    "prompt": FG_PROMPT,
}


# ------------------------------------------------------------------ terrain

def _gradient(canvas, w, h, top, bottom, steps=6, y0=0.0, y1=0.55):
    tr = int(top[1:3], 16); tg = int(top[3:5], 16); tb = int(top[5:7], 16)
    br = int(bottom[1:3], 16); bg_ = int(bottom[3:5], 16); bb = int(bottom[5:7], 16)
    y_start = int(h * y0)
    y_end   = int(h * y1)
    band = max(1, (y_end - y_start) // steps)
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = int(tr + (br - tr) * t)
        g = int(tg + (bg_ - tg) * t)
        b = int(tb + (bb - tb) * t)
        color = f"#{r:02x}{g:02x}{b:02x}"
        canvas.create_rectangle(
            0, y_start + i * band,
            w, y_start + (i + 1) * band + 1,
            fill=color, outline="", tags="terrain")


def _sky_and_ground(canvas, w, h, sky_top, sky_bot, ground, ground_y=0.55):
    _gradient(canvas, w, h, sky_top, sky_bot, steps=6, y0=0.0, y1=ground_y)
    canvas.create_rectangle(0, int(h * ground_y), w, h,
                            fill=ground, outline="", tags="terrain")


def _draw_plains(c, w, h, rng):
    _sky_and_ground(c, w, h, "#9fb8cf", "#d8d0b8", "#b8a878", ground_y=0.58)
    for _ in range(6):
        x = rng.randint(20, w - 20)
        y = int(h * 0.58) + rng.randint(10, int(h * 0.4) - 10)
        r = rng.randint(6, 14)
        c.create_oval(x - r, y - r // 2, x + r, y + r // 2,
                      fill="#8a9a60", outline="", tags="terrain")


def _draw_forest(c, w, h, rng):
    _sky_and_ground(c, w, h, "#7a9a78", "#3a5a3a", "#1e3a1e", ground_y=0.5)
    for _ in range(12):
        x = rng.randint(0, w)
        size = rng.randint(40, 110)
        base = int(h * 0.5) + rng.randint(0, int(h * 0.15))
        c.create_polygon(x, base - size, x - size * 0.35, base,
                         x + size * 0.35, base,
                         fill="#2a4a2a", outline="", tags="terrain")
    for _ in range(6):
        x = rng.randint(0, w)
        size = rng.randint(60, 140)
        base = int(h * 0.85) + rng.randint(0, 30)
        c.create_polygon(x, base - size, x - size * 0.4, base,
                         x + size * 0.4, base,
                         fill="#0e2a0e", outline="", tags="terrain")


def _draw_dead_plain(c, w, h, rng):
    _sky_and_ground(c, w, h, "#a8a8a0", "#c8c0b0", "#6a6050", ground_y=0.55)
    for _ in range(5):
        x = rng.randint(40, w - 40)
        y = int(h * 0.65) + rng.randint(0, int(h * 0.3))
        s = rng.randint(20, 50)
        c.create_polygon(x - s, y, x - s * 0.4, y - s * 0.6,
                         x + s * 0.3, y - s * 0.4,
                         x + s, y, x, y + s * 0.3,
                         fill="#4a4038", outline="", tags="terrain")


def _draw_lakebed(c, w, h, rng):
    _sky_and_ground(c, w, h, "#5a6a80", "#303a48", "#2a2820", ground_y=0.62)
    for _ in range(8):
        x = rng.randint(30, w - 30)
        y = int(h * 0.62) + rng.randint(0, int(h * 0.25))
        bw = rng.randint(14, 26)
        bh = rng.randint(30, 55)
        c.create_rectangle(x - bw // 2, y - bh, x + bw // 2, y,
                           fill="#888078", outline="", tags="terrain")
        c.create_oval(x - bw // 2, y - bh - bw // 2,
                      x + bw // 2, y - bh + bw // 2,
                      fill="#888078", outline="", tags="terrain")


def _draw_valley(c, w, h, rng):
    _sky_and_ground(c, w, h, "#8fb0d0", "#d8e0e8", "#706050", ground_y=0.65)
    for _ in range(4):
        x = rng.randint(-50, w + 50)
        size = rng.randint(80, 200)
        base = int(h * 0.65) + rng.randint(-20, 20)
        c.create_polygon(x - size, base, x, base - size,
                         x + size, base,
                         fill="#5a5048", outline="", tags="terrain")
    for _ in range(6):
        x = rng.randint(20, w - 20)
        y = int(h * 0.75) + rng.randint(0, int(h * 0.2))
        s = rng.randint(10, 28)
        c.create_oval(x - s, y - s, x + s, y + s,
                      fill="#6a5850", outline="", tags="terrain")


def _draw_cave(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#0a0c10",
                       outline="", tags="terrain")
    for _ in range(10):
        x = rng.randint(0, w)
        length = rng.randint(20, 90)
        c.create_polygon(x - 6, 0, x + 6, 0, x, length,
                         fill="#1a1c22", outline="", tags="terrain")
    for _ in range(5):
        x = rng.randint(0, w)
        y = rng.randint(int(h * 0.7), h)
        r = rng.randint(20, 60)
        c.create_oval(x - r, y - r // 3, x + r, y + r // 3,
                      fill="#14161c", outline="", tags="terrain")


def _draw_stone_hall(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#22242a",
                       outline="", tags="terrain")
    for row in range(0, h, 40):
        for col in range(0, w, 80):
            offset = 40 if (row // 40) % 2 else 0
            c.create_rectangle(col + offset + 2, row + 2,
                               col + offset + 76, row + 36,
                               fill="#2c2e34", outline="#1a1c22",
                               tags="terrain")


def _draw_crypt(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#1a2420",
                       outline="", tags="terrain")
    for _ in range(20):
        x = rng.randint(0, w)
        y = rng.randint(0, int(h * 0.6))
        length = rng.randint(20, 80)
        c.create_line(x, y, x, y + length,
                      fill="#2a3430", width=1, tags="terrain")


def _draw_armory(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#28201a",
                       outline="", tags="terrain")
    for _ in range(6):
        x = rng.randint(40, w - 40)
        c.create_rectangle(x - 4, 60, x + 4, int(h * 0.8),
                           fill="#3a2a20", outline="", tags="terrain")


def _draw_library(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#26180e",
                       outline="", tags="terrain")
    for _ in range(6):
        x = rng.randint(40, w - 80)
        y = rng.randint(60, int(h * 0.5))
        c.create_rectangle(x, y, x + 60, y + 100,
                           fill="#3a2818", outline="#1a1008",
                           tags="terrain")
        for row in range(4):
            c.create_rectangle(x + 4, y + 6 + row * 24,
                               x + 56, y + 22 + row * 24,
                               fill="#5a4020", outline="",
                               tags="terrain")


def _draw_sanctum(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#140c1c",
                       outline="", tags="terrain")
    for _ in range(4):
        x = rng.randint(60, w - 60)
        y = rng.randint(80, h - 80)
        for r in (60, 40, 20):
            shade = 20 + (60 - r) // 2
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=f"#{shade:02x}{shade//2:02x}{shade:02x}",
                          outline="", tags="terrain")


def _draw_shrine_hall(c, w, h, rng):
    c.create_rectangle(0, 0, w, h, fill="#080810",
                       outline="", tags="terrain")
    cx, cy = w // 2, int(h * 0.6)
    for r, shade in ((180, 30), (120, 45), (70, 60), (35, 80)):
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill=f"#{shade:02x}{shade//2:02x}{shade//3:02x}",
                      outline="", tags="terrain")


# Keyword -> renderer. First match wins, so longer / more specific
# phrases must precede shorter ones ("dead plain" before "plain").
KEYWORD_RENDERERS = [
    ("dead plain",  _draw_dead_plain),
    ("lake bed",    _draw_lakebed),
    ("tombs",       _draw_lakebed),
    ("stone hall",  _draw_stone_hall),
    ("black stone", _draw_shrine_hall),
    ("forest",      _draw_forest),
    ("valley",      _draw_valley),
    ("boulders",    _draw_valley),
    ("plain",       _draw_plains),
    ("cave",        _draw_cave),
    ("crypt",       _draw_crypt),
    ("armory",      _draw_armory),
    ("library",     _draw_library),
    ("sanctum",     _draw_sanctum),
]


def _pick_renderer(description):
    low = (description or "").lower()
    for keyword, fn in KEYWORD_RENDERERS:
        if keyword in low:
            return fn
    return _draw_cave


# ------------------------------------------------------------------ GUI

class GUI:
    COMPASS = {
        #  dir: (relx, rely, anchor, xoff, yoff)
        'N': (0.5, 0.0, "n",   0,  16),
        'S': (0.5, 1.0, "s",   0, -16),
        'E': (1.0, 0.5, "e", -16,   0),
        'W': (0.0, 0.5, "w",  16,   0),
        'U': (0.0, 0.0, "nw", 16,  16),
        'D': (0.0, 1.0, "sw", 16, -16),
    }

    # Vertical anchor for the description panel (0=top, 1=bottom of canvas)
    DESC_RELY = 0.36
    # Where the log begins, and how many lines it may occupy
    LOG_RELY  = 0.56
    LOG_LINES = 8

    def __init__(self, root, session):
        self.root = root
        self.session = session
        self.game_over = False

        root.title(f"pydventure - {session.game_name}")
        root.geometry("1100x780")
        root.minsize(800, 620)
        root.configure(bg=BG_PANEL)

        base = tkfont.nametofont("TkDefaultFont").copy()
        base.configure(size=FONT_SIZE)
        root.option_add("*Font", base)

        self.history = []
        self.hist_idx = 0
        self.log_entries = []

        self._build()
        self._init_log()
        root.protocol("WM_DELETE_WINDOW", self._on_quit)
        root.update_idletasks()
        self.refresh()
        self.entry.focus_set()

    # ------------------------------------------------------------- layout

    def _build(self):
        # Status bar
        self.status_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.status_var,
                 anchor="w", bg="#0a1620", fg="#f0f4f8",
                 padx=10, pady=6, font=(None, FONT_SIZE, "bold")
                 ).pack(fill="x", side="top")
        self.inv_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.inv_var,
                 anchor="w", bg="#182028", fg="#c8d0d8",
                 padx=10, pady=4, font=("Courier", FONT_SIZE)
                 ).pack(fill="x", side="top")

        # HUD strip
        self.hud = tk.Frame(self.root, bg="#0a0e14",
                            highlightthickness=1,
                            highlightbackground="#2a3440")
        self.hud.pack(fill="x", side="top")
        self.hud_inner = tk.Frame(self.hud, bg="#0a0e14")
        self.hud_inner.pack(fill="x", padx=10, pady=8)

        # Command line
        bar = tk.Frame(self.root, bg="#0a0e14")
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, text=">", bg="#0a0e14", fg=FG_PROMPT,
                 font=("Courier", FONT_SIZE, "bold")
                 ).pack(side="left", padx=(10, 4), pady=6)
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(bar, textvariable=self.entry_var,
                              font=("Courier", FONT_SIZE),
                              bg="#141a22", fg="#e0e8f0",
                              insertbackground="#e0e8f0",
                              relief="flat", bd=4)
        self.entry.pack(side="left", fill="x", expand=True,
                        padx=(0, 6), pady=6)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Up>", self._history_up)
        self.entry.bind("<Down>", self._history_down)
        tk.Button(bar, text="Send", command=self._on_enter,
                  bg=BG_BUTTON, fg=FG_TEXT,
                  activebackground=BG_BUTTON_HOVER,
                  activeforeground=FG_TEXT,
                  font=(None, FONT_SIZE),
                  relief="flat", padx=12
                  ).pack(side="right", padx=(0, 10), pady=6)

        # Play area (canvas + overlays)
        self.play = tk.Frame(self.root, bg="#000")
        self.play.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.play, bg="#000",
                                highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Description panel (over the canvas)
        self.desc_panel = tk.Frame(self.play, bg="#0a1018",
                                   highlightthickness=1,
                                   highlightbackground="#3a4858")
        self.desc_text = tk.Label(
            self.desc_panel, text="", bg="#0a1018", fg="#e8ecf0",
            wraplength=460, justify="left", anchor="nw",
            padx=18, pady=14, font=(None, FONT_SIZE))
        self.desc_text.pack()
        self.desc_panel.place(relx=0.5, rely=self.DESC_RELY, anchor="center")

        # Door buttons created fresh on refresh
        self.door_widgets = {}

        self.play.bind("<Configure>", self._on_play_resize)

    # ------------------------------------------------------------- terrain

    def _on_play_resize(self, event):
        self._draw_terrain()
        self.desc_text.configure(wraplength=max(280, int(event.width * 0.44)))

    def _draw_terrain(self):
        c = self.canvas
        c.delete("terrain")
        w = self.play.winfo_width()
        h = self.play.winfo_height()
        if w < 10 or h < 10:
            return
        p = self.session.player
        rs = p.current_room
        desc = rs.room.description if rs and rs.room.description else ""
        fn = _pick_renderer(desc)
        rng = random.Random(f"{p.map_name}:{p.x},{p.y},{p.z}")
        fn(c, w, h, rng)
        self._draw_log()   # log lives on the same canvas; re-place it

    # ------------------------------------------------------------- log

    def _init_log(self):
        self._log(f"Welcome to {self.session.game_name}.", tag="title")
        self._log("Click a door to move. Type 'combine rock rock' to craft.",
                  tag="dim")

    def _log(self, text, tag=None):
        self.log_entries.append((text, tag))
        if len(self.log_entries) > 200:
            self.log_entries = self.log_entries[-200:]
        self._draw_log()

    def _draw_log(self):
        c = self.canvas
        c.delete("log")
        w = self.play.winfo_width()
        h = self.play.winfo_height()
        if w < 10 or h < 10:
            return
        log_top = int(h * self.LOG_RELY)
        line_h  = FONT_SIZE + 10
        cx      = w // 2
        entries = self.log_entries[-self.LOG_LINES:]
        for i, (text, tag) in enumerate(entries):
            color = LOG_COLORS.get(tag, "#f4f4f6")
            c.create_text(cx, log_top + i * line_h,
                          text=text, fill=color,
                          font=(None, FONT_SIZE),
                          anchor="n", tags="log")

    # ------------------------------------------------------------- command

    def _on_enter(self, event=None):
        if self.game_over:
            return
        cmd = self.entry_var.get().strip()
        if not cmd:
            return
        self.entry_var.set("")
        self.history.append(cmd)
        self.hist_idx = len(self.history)
        self._send(cmd)

    def _history_up(self, event):
        if not self.history: return "break"
        self.hist_idx = max(0, self.hist_idx - 1)
        self.entry_var.set(self.history[self.hist_idx])
        self.entry.icursor("end")
        return "break"

    def _history_down(self, event):
        if not self.history: return "break"
        self.hist_idx = min(len(self.history), self.hist_idx + 1)
        self.entry_var.set(self.history[self.hist_idx]
                           if self.hist_idx < len(self.history) else "")
        self.entry.icursor("end")
        return "break"

    def _send(self, cmd):
        if self.game_over:
            return
        self._log(f"> {cmd}", tag="prompt")
        try:
            out, quit_ = self.session.handle_command(cmd)
        except Exception as e:
            self._log(f"[internal error: {e}]", tag="bad")
            return
        for line in out:
            self._log(line, tag=self._classify(line))
        if quit_:
            self.game_over = True
            self._log("Game over. Close the window to exit.", tag="title")
            self.entry.configure(state="disabled")
            return
        self.refresh()

    def _on_quit(self):
        try:
            self.session.save_game()
        except Exception:
            pass
        self.root.destroy()

    def _classify(self, line):
        if not line.strip(): return None
        low = line.lower()
        if ("victory" in low or "defeat the" in low or "you take" in low
                or "you combine" in low or "you rest" in low
                or "you collect" in low or "you buy" in low):
            return "good"
        if ("driven back" in low or "fail" in low or "need " in low
                or "collapse" in low or "don't" in low or "cannot" in low
                or "unknown" in low):
            return "bad"
        if "===" in line:
            return "title"
        return None

    # ------------------------------------------------------------- refresh

    def refresh(self):
        self.status_var.set(self._make_status())
        self.inv_var.set(self._make_inventory())
        self._draw_terrain()
        self._rebuild_description()
        self._rebuild_doors()
        self._rebuild_hud()

    def _make_status(self):
        p = self.session.player
        parts = [f"{p.map_name}:{p.x},{p.y},{p.z}"]
        if p.coins:
            parts.append(f"coins {p.coins}")
        parts.append(f"sword {p.sword_level}")
        goal = self.session.map.goal()
        if goal and goal.get("count"):
            item = goal.get("item", "crystal")
            have = p.inventory.get(item, 0)
            parts.append(f"{item} {have}/{goal['count']}")
        parts.append(f"hp {p.hp}/{p.max_hp}")
        s = p.skills
        parts.append("skills " + "/".join(f"{k[0]}{v}" for k, v in s.items()))
        return "  |  ".join(parts)

    def _make_inventory(self):
        inv = self.session.player.inventory
        if not inv:
            return "inv  (empty)"
        return "inv  " + "  ".join(f"{k}:{v}" for k, v in inv.items())

    def _rebuild_description(self):
        rs = self.session.player.current_room
        if rs is None:
            self.desc_text.configure(
                text="Empty void. There is nothing here.",
                fg="#e89090")
            return
        parts = []
        if rs.room.description:
            parts.append(rs.room.description)
        if len(rs.room.zones) > 1:
            parts.append(f"[zone {rs.current_zone+1} of {len(rs.room.zones)}]")
        self.desc_text.configure(
            text="\n".join(parts) or "(no description)",
            fg="#e8ecf0")

    def _rebuild_doors(self):
        for w in self.door_widgets.values():
            w.destroy()
        self.door_widgets.clear()

        rs = self.session.player.current_room
        if rs is None:
            return
        doors = rs.current_doors()
        for d, di in doors.items():
            if not rs.is_door_visible(d):
                continue
            if d not in self.COMPASS:
                continue
            self.door_widgets[d] = self._make_door_button(d, di)

    def _make_door_button(self, d, di):
        locked = bool(di.pass_reqs)
        if locked:
            req = di.pass_reqs[0].name
            text = f"{d}\n{req}"
            fg = FG_LOCKED
        else:
            text = d
            fg = FG_OPEN

        btn = tk.Button(
            self.play, text=text,
            font=(None, FONT_SIZE, "bold"),
            bg=BG_BUTTON, fg=fg,
            activebackground=BG_BUTTON_HOVER, activeforeground=fg,
            relief="raised", bd=3,
            width=4, height=2,
            cursor="hand2",
            command=lambda dd=d: self._send(f"move {dd}"))

        relx, rely, anchor, xoff, yoff = self.COMPASS[d]
        btn.place(relx=relx, rely=rely, anchor=anchor,
                  x=xoff, y=yoff)
        return btn

    # ------------------------------------------------------------- HUD

    def _rebuild_hud(self):
        for w in self.hud_inner.winfo_children():
            w.destroy()

        rs = self.session.player.current_room

        left = tk.Frame(self.hud_inner, bg="#0a0e14")
        left.pack(side="left", fill="both", expand=True)

        if rs is not None:
            enemies = rs.current_enemies()
            if enemies:
                row = tk.Frame(left, bg="#0a0e14")
                row.pack(fill="x", anchor="w", pady=(0, 4))
                tk.Label(row, text="Enemies:", bg="#0a0e14", fg=FG_BAD,
                         font=(None, FONT_SIZE, "bold")
                         ).pack(side="left", padx=(0, 8))
                ep = rs._enemy_power(enemies)
                for name, count in enemies:
                    diff = self.session.map.difficulty(name)
                    tk.Label(row, text=f"{name} x{count} (d{diff})",
                             bg="#1a0a0a", fg=FG_BAD,
                             padx=8, pady=3,
                             font=("Courier", FONT_SIZE)
                             ).pack(side="left", padx=3)
                tk.Label(row, text=f"EP {ep}", bg="#0a0e14", fg=FG_DIM,
                         font=("Courier", FONT_SIZE)
                         ).pack(side="left", padx=8)

            items = rs.current_items()
            if items:
                row = tk.Frame(left, bg="#0a0e14")
                row.pack(fill="x", anchor="w")
                tk.Label(row, text="Items:", bg="#0a0e14", fg="#c090e8",
                         font=(None, FONT_SIZE, "bold")
                         ).pack(side="left", padx=(0, 8))
                for it in items:
                    self._item_chip(row, it)

        right = tk.Frame(self.hud_inner, bg="#0a0e14")
        right.pack(side="right", fill="y")

        if rs is not None:
            enemies = rs.current_enemies()
            if enemies:
                self._action_button(right, "Fight", "fight", accent="bad")
                self._action_button(right, "Flee",  "flee",  accent="dim")
                if self.session.player.has_item("fire"):
                    self._action_button(right, "Fire", "use fire", accent="good")

    def _item_chip(self, parent, item):
        locked = bool(item.requirements)
        fg = "#c090e8" if not locked else "#e8c67f"
        text = f"{item.name} x{item.count}"
        if item.price is not None:
            text += f" ({item.price}c)"
        if locked:
            text += f" [{item.requirements[0].name}]"

        chip = tk.Frame(parent, bg="#1a1028",
                        highlightthickness=1,
                        highlightbackground="#3a2a4a")
        chip.pack(side="left", padx=3)
        tk.Label(chip, text=text, bg="#1a1028", fg=fg,
                 padx=8, pady=2, font=("Courier", FONT_SIZE)
                 ).pack(side="left")
        verb = "buy" if item.for_sale else "take"
        tk.Button(chip, text=verb.capitalize(),
                  bg=BG_BUTTON, fg=fg,
                  activebackground=BG_BUTTON_HOVER, activeforeground=fg,
                  relief="flat", bd=0, padx=8,
                  font=(None, FONT_SIZE, "bold"),
                  command=lambda n=item.name, v=verb: self._send(f"{v} {n}")
                  ).pack(side="left")

    def _action_button(self, parent, label, cmd, accent="dim"):
        fg = {"good": FG_GOOD, "bad": FG_BAD, "dim": FG_TEXT}[accent]
        btn = tk.Button(parent, text=label, bg=BG_BUTTON, fg=fg,
                        activebackground=BG_BUTTON_HOVER, activeforeground=fg,
                        relief="raised", bd=2, width=8,
                        font=(None, FONT_SIZE, "bold"), cursor="hand2",
                        command=lambda c=cmd: self._send(c))
        btn.pack(side="left", padx=3)
        return btn


# ------------------------------------------------------------------ main

def main(argv):
    if not argv:
        print("usage: pydventure_touch.py <game_directory>")
        return 1
    base_dir = argv[-1]
    if not os.path.isdir(base_dir):
        print(f"Error: directory '{base_dir}' does not exist.")
        return 1
    game_name = os.path.basename(os.path.abspath(base_dir))
    session = GameSession(base_dir, game_name)

    root = tk.Tk()
    GUI(root, session)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))