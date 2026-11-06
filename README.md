# Shogun Showdown autoplay

An exercise in building an AI to play Shogun Showdown, one turn at a time, with a key press for each decision and a log of where it came from.

It has beaten the game: `evaluator-v1` played a whole run on unlocked content, 22 fights and 926 moves, with the player only using healing potions between fights. The log is in `research/logs/run5_full`, fights 9 to 30.

This is an unofficial fan project, not affiliated with the game's developers. No game files or game code are included.

## How it works

- **`mod/`** is a BepInEx plugin. It logs each game state, asks the solver on a key press, and plays the answer.
- **`solver/rules.py`** simulates a turn. Enemies do what they've telegraphed, and after that they're treated as waiting.
- **`solver/evaluator.py`** looks one turn ahead and scores where each action leads. The weights are hand-set.

The live evaluator only uses what a player can see, so it doesn't run the enemy AI to predict moves.

## Versions

Each version that can change a choice is tagged `evaluator-<version>`, and the logs record which one made each decision.

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

In the game, F1 plays one turn and F8 reports without playing. `research/rules.md` has the game's rules as worked out from play, and `research/evaluator_backlog.md` has what's still to do.
