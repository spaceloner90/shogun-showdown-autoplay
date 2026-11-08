"""Picks the core boards: a small, stable subset of the logged boards that everyday checks run on.

    python tools/condense.py --add       # add boards from logs not yet condensed, keeping the rest (the usual)
    python tools/condense.py --rebuild   # choose again from scratch, when the criteria change
    python tools/condense.py --stats     # what the core holds, without changing it

Every board stays in its raw log under research/logs/, and `--full` on the replay and principle test still runs them
all; the core only decides what runs by default. It's chosen by meaning, in this order:

1. Pinned: every logged board a test in solver/test_positions.py names.
2. Coverage: for every feature a board can show (each hero, special move, tile, tile effect, skill, potion, enemy,
   elite, status, hazard, trap, Nobunaga's lights, a last wave, a full queue, low HP), at least COVERAGE boards
   showing it, rarest features first, preferring close calls.
3. Changed before: every board whose choice differed between two consecutive versions' full replays in
   research/replays/. A board that a past change moved is sensitive, and it records what that change was about.
4. Close calls: boards whose top two choices score within CLOSE of each other, as the version building the set saw
   them, closest first. Small changes flip these first, so they're the most telling.

At most PER_FIGHT boards come from any one fight, pinned and changed ones aside, so long fights don't crowd out the
rest. Adding a log only adds its boards, chosen against what the core already covers, so the core stays the same from
one version to the next and their replays can be compared on it. `--add` also takes in boards that changed between
versions since the last run, so run it after each full replay.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOLVER = str(ROOT / "solver")
sys.path.insert(0, SOLVER)
CORE = ROOT / "research" / "boards" / "core.json"
MARGINS = ROOT / "research" / "boards" / "margins.json"

COVERAGE = 4
CLOSE = 3.0
PER_FIGHT = 4


def _init():
    sys.path.insert(0, SOLVER)


def _margin(item):
    """How close the top two choices are on a board, as the current version sees them."""
    from evaluator import rank_actions
    from rules import state_from_log
    key, row = item
    lines = rank_actions(state_from_log(row), depth=1)
    # Reorderings of the same attack score the same for the same reasons: they aren't a real alternative.
    others = [line for line in lines[1:] if line.terms != lines[0].terms]
    return key, (lines[0].score - others[0].score) if others else float("inf")


def features(row):
    """Everything a board shows that a rule or a term reads, as (kind, name) pairs."""
    found = set()
    hero = row["hero"]
    found.add(("hero", hero["kind"]))
    found.add(("special", (hero.get("special") or {}).get("name")))
    for status in ("shield", "curse"):
        if hero.get(status):
            found.add(("hero status", status))
    for status in ("ice", "poison"):
        if hero.get(status):
            found.add(("hero status", status))
    if hero["hp"] * 3 <= hero["maxHp"]:
        found.add(("hero", "low HP"))
    loaded = 0
    for tile in row["tiles"]:
        attack = tile["attack"]
        found.add(("tile", attack["name"]))
        if attack.get("effect") not in (None, "None"):
            found.add(("effect", attack["effect"]))
            found.add(("tile with effect", f"{attack['name']} {attack['effect']}"))
        if attack.get("tileEffect") not in (None, "None"):
            found.add(("tile effect", attack["tileEffect"]))
        if "AttackQueue" in tile["where"]:
            loaded += 1
        if attack["name"] == "Crossbow" and not attack.get("value"):
            found.add(("tile state", "empty Crossbow"))
    if loaded >= 3:
        found.add(("queue", "full"))
    for skill in row.get("skills") or []:
        found.add(("skill", skill["name"] if isinstance(skill, dict) else skill))
    for potion in row.get("potions") or []:
        found.add(("potion", potion))
    for enemy in row["enemies"]:
        found.add(("enemy", enemy["kind"]))
        if enemy.get("elite") not in (None, "None"):
            found.add(("elite", enemy["elite"]))
        for trait in enemy.get("traits") or []:
            found.add(("trait", trait))
        for status in ("ice", "poison", "curse", "shield"):
            if enemy.get(status):
                found.add(("enemy status", status))
    for hazard in row.get("hazards") or []:
        found.add(("hazard", hazard.get("kind") or "hazard"))
    for trap in row.get("traps") or []:
        found.add(("trap", trap.get("effect") or "None"))
    if row.get("litCells") is not None:
        found.add(("boss", "Nobunaga's lights"))
    wave = row.get("wave")
    if wave and wave.get("isLast"):
        found.add(("wave", "last"))
    return found


def _version(name):
    return tuple(int(n) for n in re.findall(r"\d+", name))


def changed_keys():
    """Boards whose choice differed between consecutive versions' full replays, with the versions."""
    files = sorted((p for p in (ROOT / "research" / "replays").glob("v*.json") if not p.name.endswith(".core.json")),
                   key=lambda p: _version(p.stem))
    changed = {}
    for older, newer in zip(files, files[1:]):
        a = json.loads(older.read_text(encoding="utf-8"))
        b = json.loads(newer.read_text(encoding="utf-8"))
        for key in set(a) & set(b):
            if a[key]["label"] != b[key]["label"]:
                changed.setdefault(key, f"changed {older.stem} to {newer.stem}")
    return changed


def fight_of(key):
    return key.rsplit(":", 1)[0]


def pinned_keys(available):
    """The logged boards solver/test_positions.py names, by fight and turn or by sequence number."""
    text = (ROOT / "solver" / "test_positions.py").read_text(encoding="utf-8")
    keys = set()
    for fight, turn, log in re.findall(r"(?:position|choice)\((\d+), (\d+)(?:, \"(\w+)\")?\)", text):
        keys.add(f"{log or 'run2_complete'} {fight}:{turn}")
    seqs = {(int(seq), log) for seq, log in re.findall(r"at_seq\((\d+), \"(\w+)\"\)", text)}
    seqs |= {(int(seq), log) for group, log in re.findall(r"for seq in \(([\d, ]+)\):.*?\"(\w+)\"", text, re.S)
             for seq in re.findall(r"\d+", group)}
    for key, row in available.items():
        if (row.get("seq"), key.split()[0]) in seqs:
            keys.add(key)
    return {k for k in keys if k in available}


def choose(candidates, core, margins, changed):
    """Adds to `core` (key -> reasons) from `candidates` (key -> row), against what it already covers."""
    per_fight = Counter(fight_of(k) for k, reasons in core.items() if reasons != ["pinned"])
    covered = Counter()
    found = {key: features(row) for key, row in candidates.items()}
    for key in core:
        if key in found:
            covered.update(found[key])

    def add(key, reason):
        if key in core:
            if reason not in core[key]:
                core[key].append(reason)
            return True
        exempt = reason == "pinned" or reason.startswith("changed")
        if not exempt and per_fight[fight_of(key)] >= PER_FIGHT:
            return False
        core[key] = [reason]
        if key in found:
            covered.update(found[key])
        if not exempt:
            per_fight[fight_of(key)] += 1
        return True

    for key in sorted(pinned_keys(candidates)):
        add(key, "pinned")
    for key, reason in sorted(changed.items()):
        add(key, reason)

    by_feature = defaultdict(list)
    for key, feats in found.items():
        for feature in feats:
            by_feature[feature].append(key)
    for feature in sorted(by_feature, key=lambda f: (len(by_feature[f]), str(f))):
        for key in sorted(by_feature[feature], key=lambda k: (margins.get(k, float("inf")), k)):
            if covered[feature] >= COVERAGE:
                break
            if key not in core:
                add(key, f"covers {feature[0]}: {feature[1]}")

    for key in sorted((k for k in candidates if margins.get(k, float("inf")) < CLOSE), key=lambda k: (margins[k], k)):
        add(key, f"close call ({margins[key]:.1f})")
    return core


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true")
    group.add_argument("--rebuild", action="store_true")
    group.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    from evaluator import VERSION
    from logged_boards import logged_boards
    boards = dict(logged_boards())
    saved = json.loads(CORE.read_text(encoding="utf-8")) if CORE.exists() else {"logs": [], "boards": {}}
    if args.stats:
        reasons = Counter(r.split(":")[0].split(" (")[0] for rs in saved["boards"].values() for r in rs)
        print(f"{len(saved['boards'])} of {len(boards)} boards, built with {saved.get('built_with')}: {dict(reasons)}")
        return
    if args.rebuild:
        saved = {"logs": [], "boards": {}}
    logs = sorted({k.split()[0] for k in boards})
    new = [log for log in logs if log not in saved["logs"]]
    candidates = {k: r for k, r in boards.items() if k.split()[0] in new}
    changed = {k: r for k, r in changed_keys().items() if k in boards and k not in saved["boards"]}
    if not candidates and not changed:
        print("Every log is already condensed, and no new board changed between versions.")
        return
    with ProcessPoolExecutor(max_workers=os.cpu_count(), initializer=_init) as pool:
        margins = dict(pool.map(_margin, candidates.items(), chunksize=8))
    # Kept for looking at how close boards run, and so a rebuild with other thresholds needn't recompute them.
    stored = json.loads(MARGINS.read_text(encoding="utf-8")) if MARGINS.exists() and not args.rebuild else {}
    stored.update({k: round(v, 2) if v != float("inf") else None for k, v in margins.items()})
    MARGINS.parent.mkdir(parents=True, exist_ok=True)
    MARGINS.write_text(json.dumps(dict(sorted(stored.items())), indent=0) + "\n", encoding="utf-8")
    before = len(saved["boards"])
    core = choose(candidates, saved["boards"], margins, changed)
    saved = {"built_with": VERSION, "params": {"coverage": COVERAGE, "close": CLOSE, "per_fight": PER_FIGHT},
             "logs": sorted(set(saved["logs"]) | set(new)), "boards": dict(sorted(core.items()))}
    CORE.parent.mkdir(parents=True, exist_ok=True)
    CORE.write_text(json.dumps(saved, indent=1) + "\n", encoding="utf-8")
    print(f"Added {len(core) - before} boards ({', '.join(new) or 'no new logs'}, {len(changed)} changed between "
          f"versions): {len(core)} of {len(boards)} in the core.")


if __name__ == "__main__":
    main()
