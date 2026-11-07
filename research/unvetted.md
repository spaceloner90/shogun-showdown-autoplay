# What real logs haven't confirmed

Changes to rules and scoring that real play hasn't shown working yet. `evaluator-v1` won day 1 with the Wanderer
(`logs/run5_full`, fights 9 to 30), and that stands: later versions aren't held to winning it again. Passing tests
and replaying old logs doesn't vet a change, because old logs can't show new behavior. An item leaves this list
when a real log shows it working.

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
| Shove at the wall isn't offered | Rule | No refusals in the first Ronin log, but no case tested it | F1 is never refused a shove |
| Shove counts as an answer to melee | Scoring | Nothing | It's used to dodge when stepping back isn't possible |
| No distance credit for the shove | Scoring | Nothing. In the first Ronin log, one shove spent the charge on collision damage (fight 2, turn 7) | Whether it shoves too much for collision damage, spending the charge a dodge needs |
| Damaging Move with a shove | Rule | Nothing. The hit comes first, then the shove | Only if you pick that skill |
| Two Way Move with a shove | Rule | Nothing | Only if you pick that skill |

Confirmed by the first Ronin log (`logs/run6`, 3 fights on v1.2): the shove (5 uses), Smoke Bomb played by the
hero (13) and Grappling Hook played by the hero (11). Predictions were exact on all but the 2 turns where new
enemies appeared, and the player confirmed the hook looks right.

## New in v1.6: the Smoke Bomb in hand, and Lightning

`logs/run7` showed F1 loading the Smoke Bomb aggressively: 6 times in one fight, once over the 3-damage Spear, and
carrying it loaded for 4 turns waiting for the Spear. The player's read: loaded, it is more available, but any attack
spends it, so even a loaded one doesn't give the full escape value unless it's being used right now, and it shouldn't
beat a high damage tile to the queue. Only a loaded one counted as a way out when flanked, which decided turn 29.

On the 155 boards of `logs/run6` and `logs/run7`, Smoke Bomb loads go from 22 to 12, and it's never loaded over the
Spear when both are in hand (3 times before). Damage dealt goes from 76 to 81 and kills from 35 to 36, with no extra
HP lost, and hunts take as long as before. The Wanderer's 926 winning-run boards don't change.

Played in fights 1 and 2 of `logs/run7`, the second against Baru, with no HP lost in either. The player judged the
Smoke Bomb much better used. Confirmed:

- **The Smoke Bomb in hand at 8 kept, against 12 loaded.** It was loaded 6 times, never while the Spear was ready in
  hand, and never fired alone without a kill.
- **One in hand counting as a way out when flanked.** The hero was flanked with the bomb only in hand on 7 boards, and
  took no damage on any.
- **Lightning.** It struck the farthest agent ahead every time, past a closer enemy (fight 1, turn 23) and past the
  Barricade to Baru (fight 2, turns 11 and 21). Predictions were exact on every turn of both fights, except one
  where Baru summoned, which is ignored on purpose.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| Tiles that can kill only cancel a loaded Smoke Bomb's value | Scoring | Loading a killing tile no longer costs an in-hand bomb's value | Kills get set up as before |
| Lightning passing over Thorns enemies | Rule | Read from the game's code. No Thorns enemy has come up | A Thorns enemy is skipped for the next farthest |

## New in v1.5: the same rules for every hero

v1.4 fenced the Swap hero off with the old "close in" rule. Now it goes through the same kit rules as anyone. None of
this has been played. On the winning run's 926 boards, 16 top choices change from v1.4: no kills are lost (267 against 266) and no HP, and every change
either holds a Swap or makes the same kill with a tile instead. The Ronin's 110 boards in `logs/run6` don't change.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| The Swap hero stands at its tiles' reach too | Scoring | Preferred distance is 1 on 894 of 926 boards, 2 on 10 and 3 on 22 | Standing off when only Arrow is ready, then being slow to close in |
| A charged Swap is a way out, needing nobody adjacent or swappable yet | Scoring | Requiring an adjacent enemy had F1 walk up to them and pass up a kill (fight 13, turn 3). Requiring a swappable one made killing the last one look bad (fight 22, turn 15) | Flanked or surrounded with Swap on cooldown now costs 2.5 times as much |
| **A charged Swap kept is worth 12, or 18 with Two Way Move** | **Scoring** | **Swaps for damage alone, by Swap damage: 14 to 12 at 1, 8 to 5 at 2 with Two Way Move, 23 to 20 at 3 with it. The 1-damage ones left all dodge, set up a stack or reposition** | **Swaps for 1 or 2 damage only with a reason. In that run Two Way Move always came with 2 or 3 damage, so the two weren't seen apart** |
| A loaded tile that can kill doesn't cancel it | Scoring | With that exemption, F1 loaded tiles that couldn't kill just to keep the Swap's value | Stays so |

## New in v1.4: positioning from the kit, and keeping the Smoke Bomb

Replays on `logs/run6` only change one choice at a time from boards v1.2 reached, so they can't show how a whole fight
would go. v1.4 left the Swap hero unchanged; v1.5 brings it under these rules.

Confirmed by `logs/run7`, 3 fights on v1.5 and v1.6 including the boss, with no HP lost, where the first Ronin run
took damage in a chapter that usually costs none:

- **Standing at the tiles' reach, with -3 per cell of crowding.** No backing into walls or fights dragging on: 45, 29
  and 24 turns.
- **Keeping the Smoke Bomb.** It was never fired alone without a kill, and holding it didn't let enemies walk in.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| Flanked and surrounded cost 2.5 times as much with no way out | Scoring | Barely changes single choices (28 flanked to 27), so only real fights can test it. `logs/run7` never had the hero flanked with no way out | Whether Smoke Bomb still lands the hero between enemies |
| It's fired when it dodges | Scoring | A replay of fight 3, turn 28 with the bomb held picks the dodge. `logs/run7` never needed a dodge | Whether it actually gets kept until needed |
| Immediate damage is lower | Trade-off | About 17% less damage across those boards (58 to 48) | Whether fights take longer, which brings more waves |

## New in v1.3: Shockwave

All confirmed by `logs/run7`: the damage of 1, the chain through touching enemies (two of them in fight 0, turn
41), and a killed target still setting it off (fight 0, turns 16, 24 and 41). In fight 2, turn 21, the Spear hit the
Barricade and Baru, each set off its own chain, and the Barricade survived the extra hit on itself: 5, then 2, then 1.

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
