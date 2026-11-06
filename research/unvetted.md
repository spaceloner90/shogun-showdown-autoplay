# What real logs haven't confirmed

`evaluator-v1` is the vetted version: it played the whole winning run in `logs/run5_full`, fights 9 to 30.
Anything here is newer than that, or never came up in it. Passing tests and replaying old logs doesn't vet
something, because old logs can't show new behavior. An item leaves this list when a real log shows it working.

## New in v1.1

"Rule" means it comes from the game's code. "Scoring" is a judgment about what something is worth, which
only real play can test.

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| Bomb warnings logged by the mod | Rule | Nothing: no log has them yet | `hazards` shows a bomb on the turn after it's thrown, with the right cells |
| Bomb timing and blast | Rule | One blast in fight 28 fits: thrown turn 21, hit turn 23 | Blast covers 3 cells, and F1 walks clear |
| Bomb hurting a boss | Rule | Nothing | A boss in its own blast loses HP |
| Poison ticks | Rule | Replays match all ticks and the shield block on the final boss | Stays exact in new fights |
| Poison refreshing, and a tick killing | Rule | Nothing | Poisoning twice doesn't add turns |
| Poison and curse together | Rule | Nothing. A tick is assumed to use up and be doubled by a curse | Hit size when both are on one enemy |
| **What poison is worth to F1** | **Scoring** | **Nothing. First guess, and the least settled part of v1.1** | **See below** |
| Copycat Mirror | Rule | Replays match its queue | The copy's threat is a guess: 2 damage at range 1 until it's visible |
| Barricade | Rule | Replays match its position and HP | Whether it's worth killing or walking around |
| Two Way Move | Rule | Nothing: F1 never swapped backward in a log, and on the winning run's positions it now would on 26 | A backward swap isn't refused, and the hero keeps facing the same way |
| Shove credit | Scoring | Nothing. First guess | Whether Dragon Punch gets used well, or just more often |
| Frozen enemies aren't a threat | Rule | Frozen enemies seen waiting, none with a loaded attack | One with a loaded attack doesn't fire, and when it thaws |

## New in v1.2: the Ronin

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| Shove: target pushed, hero stays | Rule | The push itself matches Dragon Punch on the final boss (fight 30, turn 8). The Ronin's move has no log yet | The hero really doesn't move, and the charge resets |
| Shove needs a cell behind the target | Rule | Nothing | F1 is never refused a shove at the wall, and it isn't offered there |
| Shove counts as an answer to melee | Scoring | Nothing | It's used to dodge when stepping back isn't possible |
| No distance credit for the shove | Scoring | Nothing. Tried on winning-run boards with a Ronin deck: 51 shoves on 121 chances, 37 for collision damage and 14 saving a hit | Whether it shoves too much for collision damage, spending the charge a dodge needs |
| Smoke Bomb played by the hero | Rule | Only enemies have used it in a log | Both trade places, and neither turns |
| Grappling Hook played by the hero | Rule | Only enemies have used it in a log, where the pull matched | The target lands beside the hero, and hook-then-melee kills as predicted |
| Damaging Move with a shove | Rule | Nothing. The hit comes first, then the shove | Only if you pick that skill |
| Two Way Move with a shove | Rule | Nothing | Only if you pick that skill |

## New in v1.3: Shockwave

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| **Damage of 1** | **Assumed** | **Nothing. It's stored in the game's assets, not its code** | **The first "(no attacker) hits" line after a Shockwave tile fires at touching enemies** |
| Chain through touching enemies, stopping at a gap, wall or hero | Rule | Nothing | Who gets hit |
| The target is hit again if the chain reaches anyone | Rule | Nothing | Its HP drops by the tile's damage plus 1 |
| No extra hit on an isolated target | Rule | 4 firings on an isolated target in the live run showed no extra hit | Stays true |
| Each target of a multi-target tile sets off its own | Rule | Nothing. Read from where the game calls it | A Spear hitting two touching enemies: each should lose 4 |
| A killed target still sets it off | Rule | Nothing. Assumes a dead agent keeps its cell | Neighbours of a killed target are hit |

## Poison's value

The simulation follows the game. The scoring follows the curse rules: poison is worth what it adds, capped by
the enemy's remaining HP, and nothing on an enemy that dies. Each turn left counts for `poison_turn`, currently
8, against 10 for damage dealt now. Set it to 0 to keep the rules but stop F1 seeking poison out.

Questions it doesn't answer yet:

- Is poison worth more on a long fight? It counts the same on any enemy with HP to spare.
- It lands 3 damage over 3 turns regardless of who else is around, so should it favor targets out of reach?
- Re-poisoning before it runs out wastes turns. F1 sees that, but doesn't plan around it.

## Carried over from before v1

- Poison and ice as statuses on the hero: poison is simulated but hasn't come up on the hero, and ice is not modeled.
- Everything under "Not confirmed yet" in `rules.md`.
- Unfriendly Fire's extra damage: the winning run didn't have the skill.
