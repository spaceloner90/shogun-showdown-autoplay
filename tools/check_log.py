"""Sanity-checks BepInEx/autoplay/state.jsonl: event counts, catalog text, wave countdown,
and whether the predicted threat cells matched the hits that actually happened."""
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_LOG = r"C:\Program Files\Epic Games\ShogunShowdown611f6\BepInEx\autoplay\state.jsonl"


def load(path):
    rows = []
    bad = 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def report_catalog(rows):
    print("\n--- catalog ---")
    for r in rows:
        if r["type"] == "catalog":
            print(f"{r['kind']:6} {r['key']:32} {r['name']!r}: {r['description'][:110]!r}")


def report_waves(states):
    print("\n--- wave countdown (turn, wave, turnsUntilNext, blocked, enemies) ---")
    previous = None
    for s in states:
        w = s.get("wave")
        if not w:
            continue
        row = (s["turn"], w["number"], w["total"], w["turnsUntilNext"], w["nextBlockedByCrowding"], len(s["enemies"]))
        if row != previous:
            print(row)
        previous = row


def report_threats(rows):
    """For each hit on the hero, was the hero's pre-turn cell or an adjacent move predicted?"""
    print("\n--- enemy attacks vs predicted threat cells ---")
    last_state = None
    predicted_total = 0
    hero_hits = 0
    mismatches = []
    for r in rows:
        if r["type"] == "state":
            last_state = r
        elif r["type"] == "event" and r["event"] == "hit" and last_state and r["to"].startswith("HERO"):
            hero_hits += 1
            attacker_kind, _, attacker_cell = r["from"].partition("@")
            hero_cell = int(r["to"].partition("@")[2])
            matches = [e for e in last_state["enemies"] if e["kind"] == attacker_kind and e["action"] == "Attack"]
            predicted = any(hero_cell in e["threatens"] for e in matches)
            if predicted:
                predicted_total += 1
            else:
                mismatches.append((r["turn"], r["text"], [(e["cell"], e["facing"], e["threatens"]) for e in matches]))
    print(f"hits on hero: {hero_hits}, hero's cell was predicted: {predicted_total}")
    for m in mismatches:
        print("  NOT PREDICTED:", m)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    rows, bad = load(path)
    print(f"lines: {len(rows)}, unparseable: {bad}")
    print("types:", dict(Counter(r["type"] for r in rows)))
    print("events:", dict(Counter(r["event"] for r in rows if r["type"] == "event")))
    states = [r for r in rows if r["type"] == "state"]
    print("rooms:", dict(Counter(s["room"] for s in states)))
    print("enemy kinds:", dict(Counter(e["kind"] for s in states for e in s["enemies"])))
    print("skills seen:", sorted({k["name"] for s in states for k in s["skills"]}))
    print("potions seen:", sorted({p for s in states for p in s["potions"]}))
    print("special:", sorted({str(s["hero"].get("special")) for s in states})[:6])
    report_catalog(rows)
    report_waves(states)
    report_threats(rows)
    print("\n--- all events ---")
    for r in rows:
        if r["type"] == "event":
            print(f"t{r['turn']:>3} {r['text']}")


if __name__ == "__main__":
    main()
