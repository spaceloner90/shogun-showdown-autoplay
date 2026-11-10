"""Answers the mod's analysis request: reads a state as JSON on stdin and reports the best move per depth.

The mod runs this as a new process for every request. It hands the request to the solver server (server.py),
which keeps worker processes warm for the deeper searches, starting one if none is running, and answers this
request itself meanwhile. The server restarts when solver code changes, so changes apply on the next key press
without restarting the game.

Output is line based:
    VERSION <evaluator version>
    BEST <depth> <game action> <deck index or -1> <score> <label>
    ORDER <depth> <deck indexes to fire, in order>  (only when firing needs queue edits first)
    REPLACE <depth> <deck index>  (only when loading needs a queued tile sent back to hand first)
    POTION <potion> <why>  (only when a potion should be used first: the key press uses it instead of acting)
    ANALYSIS <one line of JSON for the log>
    REPORT
    <the readable report, through to the end>
"""
import json
import sys
import time

import server

# The solver itself is only imported when this process answers a request, not when it hands one to the server:
# importing it takes longer than the server's whole answer.

# F1 is the evaluator alone; F2 and deeper search ahead with the enemy AI (search.py).
DEPTHS = (1, 2, 3, 4)
# Answered here, without the server's workers, F2 to F4 get this long between them, on one core; one that runs out
# plays the depth below's choice, so every key still answers. The mod analyzes each board only once.
FALLBACK_BUDGET = 1.0
# F2 to F4 get this long from the start of the answer. F4 usually finishes within it, but this laptop's slower cores
# and throttling make it run over now and then; the F4 key then plays F3's choice, as the player asked, and so on
# down. F1 always finishes.
BUDGET = 1.0
MAX_TABLE_ROWS = 8


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


def build_report(row, state, by_depth, potion=None, potion_reason=None):
    from evaluator import VERSION
    from review import board
    from rules import unmodeled_content
    depths = tuple(by_depth)
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
        f"==== Analysis ({VERSION}): turn {row['turn']} | HP {state.hero.hp}/{state.hero.max_hp}{wave_text}",
        "  " + board(row),
        f"  Tiles: {', '.join(tiles)} | Special move {state.swap_charge}/{state.swap_cooldown}",
    ]

    unknown = unmodeled_content(row)
    if unknown:
        lines.append(f"  WARNING: the solver doesn't model: {', '.join(unknown)}")

    # One row per move, ordered by depth 1, with a * on each depth's choice. Each depth's choice is
    # always shown, but there can be many ways to fire a full queue, so the rest are cut off.
    ranked_labels = [line.labels[0] for line in by_depth[depths[0]]]
    picks = {by_depth[depth][0].labels[0] for depth in depths}
    labels = [l for i, l in enumerate(ranked_labels) if i < MAX_TABLE_ROWS or l in picks]
    width = max(len(label) for label in labels)
    lines.append("  " + "Move".ljust(width) + "".join(f"{'D' + str(d):>10}" for d in depths))
    hidden = len(ranked_labels) - len(labels)
    for label in labels:
        row_text = "  " + label.ljust(width)
        for depth in depths:
            ranked = by_depth[depth]
            line = next(l for l in ranked if l.labels[0] == label)
            mark = "*" if line is ranked[0] else " "
            row_text += f"{line.score:>9.1f}{mark}"
        lines.append(row_text)
    if hidden:
        lines.append(f"  ...and {hidden} lower-scoring moves")

    if state.potions:
        lines.append(f"  Potions: {', '.join(state.potions)}")
    if potion:
        lines.append(f"  USE POTION {potion} first, on this key press: {potion_reason}")
    for depth in depths:
        best = by_depth[depth][0]
        lines.append(f"  F{depth} {' -> '.join(best.labels)}")
        lines.append(f"     {why_best(by_depth[depth])}")
    return "\n".join(lines)


def answer(row, pool=None, depths=DEPTHS):
    """The whole answer to one request, as text. With a pool of worker processes, the deeper searches split this
    turn's actions between them."""
    from evaluator import VERSION, potion_plan, rank_actions
    from rules import state_from_log
    from rules import apply_potion
    from search import POTION_PREFERENCE, potion_choice, rank_lines, submit_lines
    out = []
    print = out.append  # noqa: A001 - each line of the answer, in order
    state = state_from_log(row)
    started = time.perf_counter()
    late = []
    potion_jobs = {}
    if pool is not None:
        # Every depth past F1 shares the budget; one that runs over plays the choice of the deepest that didn't.
        deadline = time.time() + BUDGET
        collect = submit_lines(state, depths, pool, deadlines={d: deadline for d in depths if d > 1})
        # Each potion held gets its own search of the board after drinking it, at F3 and F4, alongside.
        potion_jobs = {name: submit_lines(apply_potion(state, name), (3, 4), pool, deadlines={3: deadline, 4: deadline})
                       for name in sorted(set(state.potions)) if name in POTION_PREFERENCE}
        by_depth = collect()
        late = [d for d in depths if d not in by_depth]
        for depth in sorted(late):
            by_depth[depth] = by_depth[depth - 1]
    else:
        deadline = time.time() + FALLBACK_BUDGET
        by_depth = {}
        for depth in depths:
            lines = rank_actions(state, depth=1) if depth == 1 else rank_lines(state, depth, deadline=deadline)
            if lines is None:
                late.append(depth)
                lines = by_depth[depth - 1]
            by_depth[depth] = lines
    if pool is not None and potion_jobs:
        # Each potion judged at the deepest depth that finished in time for it and for the board without it.
        found = {name: collect() for name, collect in potion_jobs.items()}
        depth = 4 if 4 not in late and all(4 in f for f in found.values()) else 3
        after = {name: f.get(depth) for name, f in found.items()}
        potion, potion_reason = potion_choice(state, by_depth[depth], after, depth)
    else:
        potion, potion_reason, _ = potion_plan(state, by_depth[depths[0]])
    elapsed = time.perf_counter() - started

    print(f"VERSION {VERSION}")
    for depth in depths:
        best = by_depth[depth][0]
        action = best.actions[0]
        deck_index = action.tile if action.tile is not None else -1
        print(f"BEST {depth} {game_action(state, action)} {deck_index} {best.score:.1f} {' -> '.join(best.labels)}")
        if action.order is not None:
            print(f"ORDER {depth} {','.join(str(i) for i in action.order)}")
        if action.replace is not None:
            print(f"REPLACE {depth} {action.replace}")
    if potion:
        print(f"POTION {potion} {potion_reason}")

    analysis = {
        "evaluatorVersion": VERSION,
        "basedOnStateSeq": row.get("seq"),
        "seconds": round(elapsed, 3),
        "outOfTime": late,
        "potion": {"name": potion, "why": potion_reason} if potion else None,
        "depths": {
            str(depth): [
                {"line": l.labels, "score": round(l.score, 2), "terms": {k: round(v, 2) for k, v in l.terms.items() if v}}
                for l in by_depth[depth]
            ]
            for depth in depths
        },
    }
    print("ANALYSIS " + json.dumps(analysis, separators=(",", ":")))
    print("REPORT")
    print(build_report(row, state, by_depth, potion, potion_reason))
    for depth in late:
        print(f"  F{depth} ran out of time, so it plays the next depth down's choice.")
    return "\n".join(out)


def main():
    row_text = sys.stdin.read()
    text = server.ask(row_text)
    if text is None:
        text = answer(json.loads(row_text))
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
