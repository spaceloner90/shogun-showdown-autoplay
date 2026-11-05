"""Checks the step button's behaviour from BepInEx/autoplay/state.jsonl."""
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_LOG = r"C:\Program Files\Epic Games\ShogunShowdown611f6\BepInEx\autoplay\state.jsonl"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()]
    events = [r for r in rows if r["type"] == "event"]
    by_seq = {r["seq"]: r for r in rows}

    print("event counts:", dict(Counter(e["event"] for e in events)))
    print("action sources:", dict(Counter(e["source"] for e in events if e["event"] == "hero_action")))
    print("ignored reasons:", dict(Counter(e["why"] for e in events if e["event"] == "step_ignored")))
    print("refused:", [e["text"] for e in events if e["event"] == "step_refused"])

    # Test 1: each decision should be followed by exactly one action from that source, before the next decision.
    print("\n--- decision -> action pairing ---")
    decisions = [i for i, e in enumerate(events) if e["event"] == "decision"]
    bad_pairs = 0
    for n, i in enumerate(decisions):
        end = decisions[n + 1] if n + 1 < len(decisions) else len(events)
        stepped = [e for e in events[i + 1:end] if e["event"] == "hero_action" and e["source"] == events[i]["source"]]
        if len(stepped) != 1 or stepped[0]["turn"] != events[i]["turn"] or stepped[0]["action"] != events[i]["action"]:
            bad_pairs += 1
            print("  MISMATCH at decision:", events[i]["text"], "| turn", events[i]["turn"],
                  "| actions:", [(s["turn"], s["action"]) for s in stepped])
    print(f"decisions: {len(decisions)}, mismatched: {bad_pairs}")

    # Each decision should point at a state line from the same turn.
    print("\n--- basedOnStateSeq ---")
    bad_refs = 0
    for i in decisions:
        d = events[i]
        state = by_seq.get(d["basedOnStateSeq"])
        if state is None or state["type"] != "state" or state["turn"] != d["turn"] or state["seq"] > d["seq"]:
            bad_refs += 1
            print("  BAD:", d["seq"], d["turn"], "->", d["basedOnStateSeq"], state and (state["type"], state["turn"]))
    print(f"bad references: {bad_refs}")

    # Test 5: turn numbers should only ever move forward within a combat, by at most one.
    print("\n--- turn numbering ---")
    previous = None
    problems = 0
    for r in rows:
        if r["type"] == "event" and r["event"] == "combat_start":
            previous = None
            continue
        if previous is not None and not (previous <= r["turn"] <= previous + 1):
            problems += 1
            print("  JUMP:", previous, "->", r["turn"], r.get("text", r["type"]))
        previous = r["turn"]
    print(f"numbering problems: {problems}")

    print("\n--- timeline ---")
    for r in rows:
        if r["type"] == "event":
            print(f"seq{r['seq']:>4} t{r['turn']:>3} @{r['time']:>7} {r['text']}")
        elif r["type"] == "state":
            hero = r["hero"]
            enemies = ", ".join(f"{e['kind']}@{e['cell']}:{e['hp']}hp:{e['action']}" for e in r["enemies"])
            wave = r.get("wave")
            wave_text = f" wave {wave['number']}/{wave['total']} next={wave['turnsUntilNext']}" if wave else ""
            print(f"seq{r['seq']:>4} t{r['turn']:>3} STATE {r['room']}{wave_text} hero@{hero['cell']} {hero['hp']}hp | {enemies}")


if __name__ == "__main__":
    main()
