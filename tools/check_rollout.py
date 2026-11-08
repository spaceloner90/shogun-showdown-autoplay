"""How far ahead the simulation holds: from each logged board, the hero's actual next moves played through the
rules and the ported enemy AI, and the board it predicts after 1 to 4 turns compared with the one the game logged.

    python tools/check_rollout.py                 # every log in solver/logged_boards.py
    python tools/check_rollout.py run13 --show 4  # one log, listing what differed at 4 turns

This tests the world the F2+ search plans in, apart from the search's own choices: the moves are the ones really
played. A window where a wave arrives is left out, since what spawns is random. "Exact" means every field the
prediction checker compares matches; "fight" counts only the hero's HP and cell and each enemy's kind, cell and HP.
Windows are split by whether every enemy in them has its AI ported.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solver"))

from check_predictions import compare, to_action, turns_from_log  # noqa: E402
from enemy_ai import PORTED  # noqa: E402
from logged_boards import LOGS, RUNS  # noqa: E402
from rules import Action, state_from_log, step  # noqa: E402

HORIZON = 4


def fights(rows):
    """The logged turns in runs of consecutive turns within one fight."""
    runs, current = [], []
    for turn in turns_from_log(rows):
        action_name, before, tile, after, spawned = turn
        if current and (before["turn"] != current[-1][3]["turn"] or before["room"] == "CampRoom"):
            runs.append(current)
            current = []
        if before["room"] != "CampRoom" and after["turn"] == before["turn"] + 1:
            current.append(turn)
    if current:
        runs.append(current)
    return runs


def action_for(state, turn):
    """The move really made, as the solver's action. An attack fires what the logged queue held as it fired, which
    includes free edits made just before."""
    action_name, before, tile, after, _ = turn
    if action_name != "Attack":
        return to_action(state, action_name, tile, after)
    queued = [i for i, t in enumerate(before["tiles"]) if "AttackQueue" in t["where"]]
    names = [a["name"] for a in before["hero"]["queue"]]
    order = sorted(queued, key=lambda i: names.index(before["tiles"][i]["attack"]["name"])
                   if before["tiles"][i]["attack"]["name"] in names else 99)
    return Action("Attack", order=tuple(order)) if order else Action("Attack")


def fight_fields(predicted, row):
    hero = row["hero"]
    if (predicted.hero.hp, predicted.hero.cell) != (hero["hp"], hero["cell"]):
        return False
    mine = sorted((e.kind, e.cell, e.hp) for e in predicted.enemies if e.alive)
    theirs = sorted((e["kind"], e["cell"], e["hp"]) for e in row["enemies"])
    return mine == theirs


def check(log, show):
    rows = [json.loads(line) for line in (LOGS / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
    counts = Counter()
    for run in fights(rows):
        for start in range(len(run)):
            state = state_from_log(run[start][1])
            ported = all(e.kind in PORTED for e in state.enemies)
            for h in range(1, HORIZON + 1):
                if start + h > len(run) or run[start + h - 1][4]:
                    break
                turn = run[start + h - 1]
                state, _ = step(state, action_for(state, turn))
                after = turn[3]
                ported = ported and all(e["kind"] in PORTED for e in after["enemies"])
                problems = compare(state, after, False)
                group = "ported" if ported else "with unknowns"
                counts[(group, h, "n")] += 1
                counts[(group, h, "exact")] += not problems
                counts[(group, h, "fight")] += fight_fields(state, after)
                if show and h == show and problems and ported:
                    print(f"  {log} from seq {run[start][1]['seq']} turn {run[start][1]['turn']}, {h} turns: "
                          + "; ".join(f"{f} {e} vs {a}" for f, e, a in problems[:3]))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="*")
    parser.add_argument("--show", type=int, help="list what differed at this many turns, where all AI is ported")
    args = parser.parse_args()
    counts = Counter()
    for log in args.logs or [log for log, _ in RUNS]:
        counts += check(log, args.show)
    for group in ("ported", "with unknowns"):
        print(group)
        for h in range(1, HORIZON + 1):
            n = counts[(group, h, "n")]
            if n:
                print(f"  {h} turn{'s' if h > 1 else ' '}: {n:>5} windows, exact {counts[(group, h, 'exact')] / n:6.1%}, "
                      f"fight {counts[(group, h, 'fight')] / n:6.1%}")


if __name__ == "__main__":
    main()
