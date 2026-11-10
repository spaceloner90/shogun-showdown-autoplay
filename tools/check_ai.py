"""Checks the ported enemy AI against the logs: on every logged turn, the action each enemy telegraphs next, as
solver/enemy_ai.py predicts it from the turn the hero actually played, against what the game showed.

    python tools/check_ai.py                  # every log in solver/logged_boards.py, by kind
    python tools/check_ai.py run13 --show     # one log, listing each miss

An enemy counts as covered when the AI claims to know its choice. Turns where a wave arrived are left out, since
new enemies change the board the choices were made on. Matching is by kind and cell after the turn.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solver"))

from check_predictions import to_action, turns_from_log  # noqa: E402
from logged_boards import LOGS, RUNS  # noqa: E402
from rules import state_from_log, step  # noqa: E402


def check(log, show):
    rows = [json.loads(line) for line in (LOGS / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
    seen, known, right = Counter(), Counter(), Counter()
    for action_name, before, tile_name, after, spawned in turns_from_log(rows):
        if before["room"] == "CampRoom" or spawned or after["turn"] != before["turn"] + 1:
            continue
        state = state_from_log(before)
        predicted, outcome = step(state, to_action(state, action_name, tile_name, after))
        if outcome.summons:  # A Summon's arrivals change the board, like a wave's.
            continue
        logged = {(e["kind"], e["cell"]): e for e in after["enemies"]}
        for enemy in predicted.enemies:
            actual = logged.get((enemy.kind, enemy.cell))
            if actual is None:
                continue
            seen[enemy.kind] += 1
            if not enemy.known:
                continue
            known[enemy.kind] += 1
            if enemy.action == actual["action"]:
                right[enemy.kind] += 1
            elif show:
                print(f"  {log} seq {before['seq']} turn {before['turn']} {action_name}: {enemy.kind}@{enemy.cell} "
                      f"predicted {enemy.action}, game {actual['action']}")
    return seen, known, right


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="*")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    seen, known, right = Counter(), Counter(), Counter()
    for log in args.logs or [log for log, _ in RUNS]:
        s, k, r = check(log, args.show)
        seen += s
        known += k
        right += r
    print(f"{'kind':<16}{'seen':>6}{'known':>7}{'right':>7}  accuracy")
    for kind, n in seen.most_common():
        acc = f"{right[kind] / known[kind]:.1%}" if known[kind] else "-"
        print(f"{kind:<16}{n:>6}{known[kind]:>7}{right[kind]:>7}  {acc}")
    total_known = sum(known.values())
    print(f"all: {sum(seen.values())} seen, {total_known} known ({total_known / sum(seen.values()):.1%}), "
          f"{sum(right.values())} right ({sum(right.values()) / max(1, total_known):.1%} of known)")


if __name__ == "__main__":
    main()
