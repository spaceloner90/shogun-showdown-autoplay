"""Answers the mod's F8 request: reads a state as JSON on stdin and reports the best move per depth.

The mod runs this as a new process for every request, so evaluator changes apply on the next F8
without restarting the game.

Output is line based:
    BEST <depth> <game action> <deck index or -1> <score> <label>
    ANALYSIS <one line of JSON for the log>
    REPORT
    <the readable report, through to the end>
"""
import json
import sys
import time

from evaluator import rank_actions
from review import board
from rules import MODELED, state_from_log

DEPTHS = (1, 2, 3, 4)


def game_action(state, action):
    """The game's name for a solver action. A flip's name depends on which way the hero faces."""
    if action.kind == "Flip":
        return "FlipLeft" if state.hero.facing > 0 else "FlipRight"
    return action.kind


def why_best(ranked):
    """The largest score differences between the top two moves, as a short phrase."""
    if len(ranked) < 2:
        return "the only option"
    best, second = ranked[0], ranked[1]
    margin = best.score - second.score
    if margin < 0.01:
        return f"tied with {second.labels[0]}, but its position improves sooner"
    names = set(best.terms) | set(second.terms)
    differences = {n: best.terms.get(n, 0.0) - second.terms.get(n, 0.0) for n in names}
    parts = sorted(differences.items(), key=lambda kv: abs(kv[1]), reverse=True)
    text = ", ".join(f"{name} {value:+.1f}" for name, value in parts[:3] if abs(value) >= 0.05)
    return f"beats {second.labels[0]} by {margin:.1f}: {text}"


def build_report(row, state, by_depth):
    wave = row.get("wave")
    wave_text = ""
    if wave:
        wave_text = f" | wave {wave['number']}/{wave['total']}"
        wave_text += " (final)" if wave["isLast"] else f", next in {wave['turnsUntilNext']}"
    tiles = []
    for tile in state.tiles:
        turns = tile.cooldown - tile.charge
        status = "queued" if tile.in_queue else "ready" if tile.ready else f"ready in {turns}"
        tiles.append(f"{tile.attack.name} ({status})")

    lines = [
        "",
        f"==== Analysis: turn {row['turn']} | HP {state.hero.hp}/{state.hero.max_hp}{wave_text}",
        "  " + board(row),
        f"  Tiles: {', '.join(tiles)} | Swap {state.swap_charge}/{state.swap_cooldown} (not used by the solver yet)",
    ]

    unknown = sorted({a.name for e in state.enemies for a in e.queue} - MODELED)
    if unknown:
        lines.append(f"  WARNING: attacks the rules don't model: {', '.join(unknown)}")

    # One row per move, ordered by the deepest search, with a * on each depth's choice.
    labels = [line.labels[0] for line in by_depth[DEPTHS[-1]]]
    width = max(len(label) for label in labels)
    lines.append("  " + "Move".ljust(width) + "".join(f"{'D' + str(d):>10}" for d in DEPTHS))
    for label in labels:
        row_text = "  " + label.ljust(width)
        for depth in DEPTHS:
            ranked = by_depth[depth]
            line = next(l for l in ranked if l.labels[0] == label)
            mark = "*" if line is ranked[0] else " "
            row_text += f"{line.score:>9.1f}{mark}"
        lines.append(row_text)

    for depth in DEPTHS:
        best = by_depth[depth][0]
        lines.append(f"  F{depth} {' -> '.join(best.labels)}")
        lines.append(f"     {why_best(by_depth[depth])}")
    return "\n".join(lines)


def main():
    row = json.loads(sys.stdin.read())
    state = state_from_log(row)
    started = time.perf_counter()
    by_depth = {depth: rank_actions(state, depth=depth) for depth in DEPTHS}
    elapsed = time.perf_counter() - started

    for depth in DEPTHS:
        best = by_depth[depth][0]
        action = best.actions[0]
        deck_index = action.tile if action.tile is not None else -1
        print(f"BEST {depth} {game_action(state, action)} {deck_index} {best.score:.1f} {' -> '.join(best.labels)}")

    analysis = {
        "basedOnStateSeq": row.get("seq"),
        "seconds": round(elapsed, 3),
        "depths": {
            str(depth): [
                {"line": l.labels, "score": round(l.score, 2), "terms": {k: round(v, 2) for k, v in l.terms.items() if v}}
                for l in by_depth[depth]
            ]
            for depth in DEPTHS
        },
    }
    print("ANALYSIS " + json.dumps(analysis, separators=(",", ":")))
    print("REPORT")
    print(build_report(row, state, by_depth))


if __name__ == "__main__":
    main()
