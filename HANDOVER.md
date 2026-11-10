# Handover: what the Shogun Showdown project learned

Written 2026-11-10 for a new session starting a Pokémon battle AI. It is a summary for someone who has not seen this
project. The details are in [`research/design.md`](research/design.md), [`CHANGELOG.md`](CHANGELOG.md) and
[`research/unvetted.md`](research/unvetted.md).

## What was built, and how it ended

An AI that plays Shogun Showdown, a turn-based single-player game on a one-row board, one key press per decision.

- **A mod** (`mod/`, C#, BepInEx) logs the full game state every turn as a line of JSON, asks the solver on a key
  press, and plays the answer.
- **A simulator** (`solver/rules.py`) plays one turn forward. It was written from the game's decompiled code.
- **The enemy AI** (`solver/enemy_ai.py`) is a port of every enemy's and boss's decision code.
- **An evaluator** (`solver/evaluator.py`) scores a position with hand-set weights.
- **A search** (`solver/search.py`) looks up to four turns ahead within 1 second, on one core.

`evaluator-v4.0` has beaten everything in the game: day 7, the hardest setting, and the Corrupted Soul after it,
with the weakest-HP hero (5 max HP). On the day 7 run it predicted 1005 of 1035 turns exactly, and 1785 of 1789
enemy choices. There are 687 tests.

## What made it work

1. **Log everything from the first day, and never throw a log away.** Every run is in `research/logs/`. Each later
   question ("why did it take that hit?") was answered by replaying a log, not by guessing.
2. **Check the simulator against reality on every logged turn.** `solver/check_predictions.py` steps each logged
   state with the action actually taken and compares it with the next logged state. `tools/check_ai.py` does the
   same for enemy choices. Rules read from code were wrong or incomplete many times, and only real turns showed it.
   The last boss, written from code alone, was off by one turn and missed a trap rule; one fight fixed both.
3. **A simple baseline first, then depth.** Version 1 looked one turn ahead with made-up weights and won the game's
   first setting. Search came later, and only paid once the enemy's choices were known.
4. **Uncertainty is priced, not modeled.** A future turn whose outcome is known counts in full. A guessed turn
   counts half. This one rule replaced several proposals for exact probability models, and the user preferred it
   every time.
5. **Principles outrank terms.** Three rules sit above every weight: having more never scores lower; one resource,
   one use (its uses are alternatives, never summed); terms that read the hand only give credit. When a term broke
   one, the term was wrong. A test checks the first on every logged board.
6. **Values that are defined by other values are computed from them in code.** Copies drift.
7. **Estimates of future value live on the position, never on the action.** A bonus on an action is counted again
   at every depth of search.
8. **One version per change that can alter a choice.** Bump, changelog entry, tag, commit. The log records which
   version made each decision, so a bad choice can be traced to the change that caused it.
9. **Keep a list of what real play has not confirmed.** `research/unvetted.md`. Passing tests and replays of old
   logs don't confirm a change, because old logs can't show new behavior. A win doesn't confirm it either.
10. **Speed work is ordinary engineering.** A solver process that stays running, cheap copies of the state, merging
    lines that reach the same position, a cache keyed on everything the result depends on.

## What went wrong, so it isn't repeated

- **Shared objects in copied states.** A cheap copy shared tile objects, and a previewed effect changed the real
  hand. Scores then depended on what had been searched before. Check that the same position always scores the same.
- **Cache keys missing a field.** The result was right until a bonus that wasn't in the key changed.
- **Stalls.** Twice the solver found that never finishing a fight scored best. Every scoring system here needed a
  cost for time passing.
- **Waiting when a free action was available.** It came back twice before a general fix.
- **Building something new without saying so.** A value was once moved onto an action without flagging it, and it
  double counted at depth. The user wants to be warned before any new kind of mechanism is built.

## How the user works

- Plays the runs themself, one key press a turn, and reports what looked wrong in plain words. Expects the log to
  be checked before any explanation is offered.
- Prefers the simplest rule that fits their understanding of the game over a more exact one that takes more work.
  Often proposes the rule; check it against the principles and the logs, and say so when it doesn't hold.
- Accepts "that behavior is justified, leave it" as an answer.
- Sees most weights as made-up numbers and doesn't want them tuned for near ties.
- Limited tokens and local compute. No heavy background jobs while they are playing.
- Commits are local until they ask for a push.

## What carries over to Pokémon, and what doesn't

Carries over: the log-and-replay loop, the prediction checks, versioning, the unvetted list, pricing uncertainty,
the principles habit, a simple baseline before anything clever.

Doesn't carry over:

- **There is no enemy code to port.** Here the opponent's next move could be known 99.9% of the time. A human or
  bot opponent chooses freely, at the same moment, with a hidden team. What replaces the port is a belief over the
  opponent's possible sets and a way to choose against a range of replies.
- **One run proves little.** Here a single logged run settled most questions. With chance and an opponent, a change
  has to be measured over many games.
- **No mod and no decompiling.** The rules engine exists and is open.

From a short survey on 2026-11-10 (web pages read once, not checked further):

- Pokémon Showdown's simulator is a Node.js package that runs locally, with no server. Its repository has Champions
  rule sets.
- One public bot targets Champions doubles and has not shown a rating. The public bot benchmark ladder has no
  Champions format.
- For older formats, a search bot (Foul Play, on a fast Rust engine) has matched bots trained on millions of
  replays. Whether that engine covers Champions was not checked.
- Showdown's policy on bots playing its public ladder was unsettled in October 2026. Ask the staff before playing
  humans. Local play needs no permission.

A first step that fits this project's habits: install the simulator locally, measure how many turns per second it
simulates, and log full battles between two trivial bots before writing any evaluation.

## Where things are

| Thing | Where |
|---|---|
| Design, principles, how a change is checked | `research/design.md` |
| The game's rules as worked out | `research/rules.md` |
| Every version and why | `CHANGELOG.md` |
| What real play hasn't confirmed | `research/unvetted.md` |
| All run logs | `research/logs/` |
| Checks against logs | `solver/check_predictions.py`, `tools/check_ai.py` |

Not in the repository, by design: the decompiled game code (`research/il.txt`, `research/signatures.txt`, remade by
`tools/dump_il.ps1` with the game installed), save backups, and the built mod.
