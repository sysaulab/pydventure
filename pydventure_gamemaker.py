#!/usr/bin/env python3
"""pydventure_gamemaker - single source of truth for pydventure tables.

Usage:
    python pydventure_gamemaker.py mygame --seed 42
    python pydventure_gamemaker.py mygame --seed 42 --no-generate
"""

import argparse, json, os, sys

ENEMIES = {
    # overworld blue tier
    "octorok_blue": {"difficulty": 1,  "description": "A common land octopus."},
    "bat_blue":     {"difficulty": 2,  "description": "A common cave bat."},
    "spider_blue":  {"difficulty": 3,  "description": "A skittering blue spider."},
    "fan":          {"difficulty": 5,  "description": "A giant flying insect."},
    "rhinos":       {"difficulty": 6,  "description": "A charging beast."},
    "knight_blue":  {"difficulty": 7,  "description": "A knight in blue armor."},
    # overworld red tier (= blue + 10)
    "octorok_red":  {"difficulty": 11, "description": "A red land octopus."},
    "bat_red":      {"difficulty": 12, "description": "A vampire bat."},
    "spider_red":   {"difficulty": 13, "description": "A venomous red spider."},
    "fan_red":      {"difficulty": 15, "description": "A crimson flying insect."},
    "rhinos_red":   {"difficulty": 16, "description": "A furious charging beast."},
    "knight_red":   {"difficulty": 17, "description": "A knight in red armor."},
    "ghosts":       {"difficulty": 19, "description": "Restless spirits of the drowned."},
    # dungeon tier
    "stalfos":      {"difficulty": 20, "description": "A skeleton in rusted armor."},
    "darknut":      {"difficulty": 24, "description": "An elite armored knight."},
    "wizzrobe":     {"difficulty": 27, "description": "A robed spellcaster."},
    "dragon":       {"difficulty": 50, "description": "A young dragon, scales still soft."},
    # shrine
    "dragon_red":   {"difficulty": 200, "description": "A dragon grown vast in the dark."},
}

DROPS = {
    "octorok_blue": {"coins": [0, 1]},
    "bat_blue":     {"coins": [0, 2]},
    "spider_blue":  {"coins": [0, 3]},
    "fan":          {"coins": [1, 4]},
    "rhinos":       {"coins": [1, 5]},
    "knight_blue":  {"coins": [2, 6]},
    "octorok_red":  {"coins": [3, 6]},
    "bat_red":      {"coins": [3, 7]},
    "spider_red":   {"coins": [4, 8]},
    "fan_red":      {"coins": [4, 9],  "bombs": [0, 1]},
    "rhinos_red":   {"coins": [5, 10], "bombs": [0, 1]},
    "knight_red":   {"coins": [6, 12], "bombs": [0, 1]},
    "ghosts":       {"coins": [5, 10], "bombs": [0, 1]},
    "stalfos":      {"coins": [8, 14],  "bombs": [0, 1]},
    "darknut":      {"coins": [10, 18], "bombs": [0, 2]},
    "wizzrobe":     {"coins": [12, 22], "bombs": [1, 2]},
    "dragon":       {"coins": [20, 35], "bombs": [2, 3], "heart": 1},
    "dragon_red":   {"coins": [25, 50], "bombs": [3, 5], "heart": 1},
}

ITEMS = {
    "sword":       {"name": "Sword",       "type": "weapon",     "description": "A simple iron blade."},
    "shield":      {"name": "Shield",      "type": "armor",      "description": "A wooden shield, well-worn."},
    "key":         {"name": "Key",         "type": "key",        "description": "A small iron key."},
    "bomb":        {"name": "Bomb",        "type": "consumable", "description": "A round black bomb."},
    "candle_blue": {"name": "Blue Candle", "type": "tool",       "description": "Burns with a cold flame."},
    "heart":       {"name": "Heart",       "type": "consumable", "description": "A glass heart, warm to hold."},
    "crystal":     {"name": "Crystal",     "type": "quest",      "description": "A shard of light, humming faintly."},
    "victory":     {"name": "Heart of the World", "type": "quest", "description": "The shrine's gift. Warm to the touch."},
}

SKILLS = {
    "fight":     {"name": "Fighting",  "description": "Prowess in combat."},
    "avoidance": {"name": "Avoidance", "description": "Skill at slipping past enemies."},
    "search":    {"name": "Searching", "description": "An eye for hidden things."},
}

TERRAINS = {
    # overworld surface
    "plains":     {"kind": "overworld", "floors": [1], "weight": 4,
                   "description": "an arid plain, cracked and dry",
                   "enemies": ["octorok_blue", "octorok_red"]},
    "forest":     {"kind": "overworld", "floors": [1], "weight": 3,
                   "description": "a dense forest, the canopy closing overhead",
                   "enemies": ["spider_blue", "bat_blue", "spider_red"]},
    "dead_plain": {"kind": "overworld", "floors": [1], "weight": 2,
                   "description": "a dead plain, the soil grey and lifeless",
                   "enemies": ["knight_blue", "knight_red"]},
    "cemetery":   {"kind": "overworld", "floors": [1], "weight": 1,
                   "description": "a dried lake bed littered with tombs",
                   "enemies": ["ghosts"]},
    "valley":     {"kind": "overworld", "floors": [1], "weight": 1,
                   "description": "a rocky valley, boulders strewn across the ground",
                   "enemies": ["rhinos", "rhinos_red"]},
    # overworld caves (z=0)
    "cave":       {"kind": "overworld", "floors": [0], "weight": 1,
                   "description": "a narrow cave, cold and quiet",
                   "enemies": ["bat_blue", "bat_red", "octorok_blue"]},
    # dungeons
    "stone_hall": {"kind": "dungeon", "floors": [0], "weight": 5,
                   "description": "a narrow stone hall",
                   "enemies": ["stalfos", "bat_red"]},
    "crypt":      {"kind": "dungeon", "floors": [0], "weight": 4,
                   "description": "a damp crypt, water pooling in the corners",
                   "enemies": ["stalfos", "spider_red"]},
    "armory":     {"kind": "dungeon", "floors": [0], "weight": 3,
                   "description": "a ruined armory, racks long since collapsed",
                   "enemies": ["darknut", "knight_red"]},
    "library":    {"kind": "dungeon", "floors": [0], "weight": 2,
                   "description": "a library of rotting books",
                   "enemies": ["wizzrobe", "bat_red"]},
    "sanctum":    {"kind": "dungeon", "floors": [0], "weight": 1,
                   "description": "a torch-lit sanctum",
                   "enemies": ["wizzrobe", "darknut"]},
    # shrine
    "shrine_hall": {"kind": "shrine", "floors": [0], "weight": 1,
                    "description": "a vast hall of black stone",
                    "enemies": ["wizzrobe", "darknut"]},
}

DESCRIPTION_SETS = {
    "overworld": {"patterns": [
        "You are in {terrain}. The way continues {exits}.",
        "{Terrain}, extending {exits}.",
        "You stand in {terrain}. {feature}The paths lead {exits}.",
        "{Terrain}. {feature}Passages run {exits}.",
        "This is {terrain}. {feature}Exits: {exits}.",
        "{Terrain} stretches away. {feature}The ways lead {exits}.",
    ]},
    "dungeon": {"patterns": [
        "A cramped passage of cold stone. {feature}{Exits} lead onward.",
        "{Terrain}, lit by a single guttering torch. {feature}{Exits}.",
        "The walls press close. {feature}You can go {exits}.",
        "Dust and old bones. {feature}Ways {exits}.",
        "Silence, save for your own breathing. {feature}Exits: {exits}.",
        "{Terrain}. Water drips somewhere out of sight. {feature}{Exits}.",
    ]},
    "shrine": {"patterns": [
        "The air is very still. {feature}You can go {exits}.",
        "{Terrain}. Something vast breathes nearby. {feature}{Exits}.",
        "Old stone, older silence. {feature}The way is {exits}.",
        "{Terrain}. The shadows feel deeper here. {feature}{Exits}.",
    ]},
}

FEATURE_PHRASES = {
    "stairs_up":       "A stone staircase ascends here. ",
    "stairs_down":     "A dark stairwell descends into the earth. ",
    "shop":            "An old man sits beside a small fire, wares on a cloth. ",
    "item":            "Something glints in the dust. ",
    "crystal":         "A crystal pulses with pale light. ",
    "crystal_chamber": "The air hums. A pedestal waits at the far end. ",
    "shrine":          "A stone altar hums in the center of the chamber. ",
}

DEFAULT_PLAYER = {
    "map": "overworld", "x": 0, "y": 0, "z": 1, "zone": 0,
    "coins": 0, "inventory": {},
    "skills": {"fight": 0, "avoidance": 0, "search": 0},
    "sword_level": 0, "won": False,
    "hp": 5, "max_hp": 5,
}


def build_world(seed, ow_w=8, ow_h=8, ow_d=2, dungeons=7):
    dw = ow_w
    dh = max(4, ow_h // 2)
    maps = [{
        "name": "overworld", "kind": "overworld",
        "width": ow_w, "height": ow_h, "depth": ow_d,
        "braid": 0.25, "enemy_chance": 0.5,
        "description_set": "overworld",
        "start": [0, 0, 1],
        "features": {
            "swords": {"count": 3, "floors": [1, 0],
                       "guarded_by": ["knight_red", "bat_red"]},
            "shops": [{"floor": 0,
                       "items": ["shield@100", "key@100", "candle_blue@60"]}],
            "loose_items": [{"name": "bomb", "count": 3, "floor": 1}],
            "stair_pairs": 2,
        },
    }]
    for i in range(1, dungeons + 1):
        maps.append({
            "name": f"level{i}", "kind": "dungeon",
            "width": dw, "height": dh, "depth": 1,
            "braid": 0.10, "enemy_chance": 0.85,
            "description_set": "dungeon",
            "crystal": True, "boss": "dragon",
        })
    maps.append({
        "name": "level8", "kind": "shrine",
        "width": dw, "height": dh, "depth": 1,
        "braid": 0.08, "enemy_chance": 0.9,
        "description_set": "shrine",
        "boss": "dragon_red",
        "shrine": {"requires": "crystal-7", "victory_item": "victory"},
    })
    return {
        "seed": seed,
        "goal": {
            "name": "Collect the seven crystals",
            "item": "crystal", "count": dungeons,
            "victory_item": "victory",
            "victory_message": "You place the seven crystals on the altar. "
                               "The shrine fills with light, and the world is quiet again.",
        },
        "respawn": {
            "minutes": 5,
            "chance": 0.2,
            "no_respawn": ["dragon", "dragon_red"],
        },
        "combat": {
            "damage_per_fail": 1,
            "heart_item": "heart",
            "death": {
                "coin_loss_fraction": 0.5,
                "restore_hp": True,
            },
        },
        "terrains": TERRAINS,
        "description_sets": DESCRIPTION_SETS,
        "feature_phrases": FEATURE_PHRASES,
        "maps": maps,
    }


def build_maps_json(world):
    meta = {}
    for m in world["maps"]:
        meta[m["name"]] = {
            "kind": m["kind"],
            "description": {"overworld": "The world above.",
                            "dungeon":   "A crystal palace.",
                            "shrine":    "The shrine."}.get(m["kind"], ""),
            "dimensions": {"x": m["width"], "y": m["height"], "z": m["depth"]},
        }
    return {
        "start_map": "overworld",
        "goal": world["goal"],
        "respawn": world["respawn"],
        "combat": world["combat"],
        "maps": meta,
    }


def write_json(path, data, force=False):
    if os.path.exists(path) and not force:
        print(f"  skip  {path}")
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"  write {path}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--seed", default="0")
    ap.add_argument("--width", type=int, default=8)
    ap.add_argument("--height", type=int, default=8)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--dungeons", type=int, default=7)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-generate", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.target, exist_ok=True)
    print(f"gamemaker -> {args.target}/")

    write_json(os.path.join(args.target, "enemies.json"), ENEMIES, args.force)
    write_json(os.path.join(args.target, "drops.json"),   DROPS,   args.force)
    write_json(os.path.join(args.target, "items.json"),   ITEMS,   args.force)
    write_json(os.path.join(args.target, "skills.json"),  SKILLS,  args.force)

    world = build_world(args.seed, args.width, args.height, args.depth, args.dungeons)
    write_json(os.path.join(args.target, "world.json"), world, args.force)
    write_json(os.path.join(args.target, "maps.json"),  build_maps_json(world), args.force)
    write_json(os.path.join(args.target, "player.json"), DEFAULT_PLAYER, args.force)

    if not args.no_generate:
        try:
            import pydventure_mazemaker as mm
        except ImportError:
            print("mazemaker not found; run it manually.", file=sys.stderr)
        else:
            print("generating rooms/ ...")
            mm.generate_from_config(
                os.path.join(args.target, "world.json"),
                os.path.join(args.target, "rooms"),
            )
            print("done.")


if __name__ == "__main__":
    main()