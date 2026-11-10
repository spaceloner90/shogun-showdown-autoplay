# Shogun Showdown autoplay

An exercise in building an AI to play Shogun Showdown, one turn at a time, with a key press for each decision and a log of where it came from.

It has beaten everything in the game: `evaluator-v4.0` won day 7 and then the Corrupted Soul (`research/logs/run20`, `run21`). The first win was `evaluator-v1`, which played a whole run on unlocked content, 22 fights and 926 moves, with the player only using healing potions between fights. The log is in `research/logs/run5_full`, fights 9 to 30.

This is an unofficial fan project, not affiliated with the game's developers. No game files or game code are included.

## How it works

- **`mod/`** is a BepInEx plugin. It logs each game state, asks the solver on a key press, and plays the answer.
- **`solver/rules.py`** simulates a turn, and **`solver/enemy_ai.py`** is the enemies' and bosses' decision code, ported from the game's.
- **`solver/evaluator.py`** scores a position. The weights are hand-set.
- **`solver/search.py`** looks up to four turns ahead within a second.

## Versions

Each version that can change a choice is tagged `evaluator-<version>`, and the logs record which one made each decision. [`CHANGELOG.md`](CHANGELOG.md) lists what every version changed.

- **`evaluator-v1`** is vetted: it won the run above.
- **After that is unvetted** until a real run confirms it. [`research/unvetted.md`](research/unvetted.md) lists what hasn't been confirmed.

## Running it

It's set up for one machine: the solver's path is hard-coded in `mod/SolverBridge.cs`, and the game's in `tools/build_mod.ps1`. You'd need BepInEx 5 installed in the game, Python 3.11, and the .NET compiler that comes with Windows.

```bash
python solver/test_rules.py
```

```bash
python solver/test_positions.py
```

In the game, F1 plays one turn, or uses a potion when the solver says to, and F8 reports without playing. [`research/design.md`](research/design.md) explains how it decides and why, `research/rules.md` has the game's rules as worked out from its code and from play, and `research/evaluator_backlog.md` has what's still to do.
