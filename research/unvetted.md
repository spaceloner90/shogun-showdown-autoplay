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

## New in v1.15: Fumiko's dash

FumikoBoss.Move in the game's code is the Strider's: she runs to the last free cell. Her one move in fight 10 of
`logs/run7` is now exact, leaving only summons as misses in the whole log. No top choice changes on any logged board.

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| Fumiko runs to the last free cell | Rule | Turn 3 of fight 10, replayed | Stays exact |
| A curse on the hero doubles its next hit, then goes | Rule | Nothing: the hero was cursed once, and not hit before the fight ended | A hit on a cursed hero for double, and the next one normal |

## New in v1.14: no cost for an attack that hits nothing

It cost 5, but a fired tile already loses its readiness to its cooldown, and firing at nothing doesn't change the
board, so by the rule only board-changing events are summed along a line. On all 1,331 logged boards, one top choice
changes: the winning run's fight 13, turn 15 fires a free Swirl at nothing with the rest of the queue, rather than
sending it back. Hunts take as long as before.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| No cost for firing at nothing | Scoring | One harmless change | Tiles with a long cooldown fired at nothing |

## New in v1.12 and v1.13: setup value, and loaded Shockwave tiles

The player's read: a loaded hook is worth something beyond its damage when the kit has short-reach tiles to exploit
an enemy brought in, while its escape value is poor, since bringing enemies closer almost never helps. That's an
intrinsic value of the move, like its escape value, rather than F1 scoring the board a volley leaves, which would be
doing F2's job. Likewise, a Shockwave tile was only worth more when the stack could see a chain from here.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| **The hook's escape value is 1, not 3** | **Scoring** | **With setup value, it keeps the hook in hand when the Smoke Bomb alone gets the same kill (fight 0, turn 21 and fight 2, turn 24 of `logs/run7`), and loads the Spear over it (fight 0, turn 29)** | **The hook used to set up the Spear, not to spend a turn for 1 damage** |
| The hook's setup value: 1 per point of damage of the strongest tile reaching 2 cells or less, charged or not, with the escape modifiers | Scoring | A first guess. The crowding penalty still weighs against pulling enemies in | Whether hooking for setup pulls in enemies that then hit the hero |
| A loaded Shockwave tile is worth 0.5 more (v1.13) | Scoring | A tiebreak, as the player put it: the Shockwave version of a tile is loaded over an identical one, but never over a point more damage. v1.12 gave 3 for the loading itself, which v1.13 replaced with a value on the loaded tile, so it stays right at a deeper horizon | Shockwave tiles loaded first when nothing else separates them |

On all logged boards, v1.13 changes 7 top choices from v1.11, all on the Ronin, with no HP lost and hunts as long as
before. One holds the Spear on fight 0, turn 2 of `logs/run7` to load the Smoke Bomb, by under half a point: v1.5
played it that way, and killed both enemies the next turn.

## New in v1.11: the Strider's dash

Read from the game's code after fight 8 of `logs/run7`, where v1.10 walked Striders one cell and mispredicted 4 of
their moves. Replayed, all 4 are now exact, leaving only the two summons as misses in the whole log. One top choice
changes on every logged board: fight 8, turn 27 loads the Smoke Bomb instead of the Spear, since it now sees the left
Strider dash in beside the hero. As played, the hero ended up between two Katanas on turn 28, which only the
player's Rain of Mirrors potion avoided.

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| A Strider's move runs to the last free cell | Rule | All 4 of fight 8's Strider moves, replayed | Stays exact |
| Whoever first blocks it moves first, if going the same way | Rule | Nothing: not seen with a Strider | A Strider behind a walking enemy |

## New in v1.10: the Warden's explosion

Read from the game's code after fight 7 of `logs/run7`, where two explosions happened unsimulated. Simulating it makes
turn 7 of that fight exact, leaving only the two summons as misses. On every logged board, 2 top choices change,
both in fight 7 and both a different tile to load: turn 1 loads the Smoke Bomb to swap a Warden next to the Ashigaru.

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| 2 to its own cell and both beside it, as its own hit | Rule | Turns 7 and 24 of fight 7, replayed | The hero taking 2 when one dies beside it, and a shield blocking it |
| Each Warden it kills explodes in turn | Rule | Turn 24, though the Shockwave would have killed the second anyway | Two touching Wardens, the second killed only by the first |
| No explosion for one that dies before its first decision | Rule | Not seen. Every Warden on the board is assumed to have decided | A Warden summoned and killed the same turn |
| F1 not killing one beside itself | Scoring | Follows from the simulation, and tested on a made-up board | Whether it steps back first, or uses the blast on other enemies |

## New in v1.9: Sharp Turn and Sniper

Both read from the game's code. Confirmed by fight 7 of `logs/run7`, on v1.9:

- **Sharp Turn**, used 3 times and predicted exactly. It strikes both cells beside the hero after turning (its range
  is -1 and 1). On turn 6 it hit the BlightCharger behind the hero, and the hook fired after it the new way.
- **Sniper**, on turn 24: the Smoke Bomb hit for 2 from 4 cells away, measured after its trade of places.

| Item | Kind | What's already confirmed | What to look for |
|---|---|---|---|
| Sharp Turn as a free turn | Scoring | Nothing. Since v1.14 nothing is charged for a tile hitting nothing, so it's weighed by its cooldown | Whether F1 uses it as a free turn more than it should |
| A curse doubling Sniper's bonus | Rule | Nothing | A cursed enemy hit from 4 or more cells away |
| With Sniper, the hero may prefer standing 4 cells off | Scoring | Only when its tiles do the most damage from there | Backing off too far, or into walls |

Two Way Move with the shove was rechecked against the code for v1.9, and matches what v1.2 simulated. It's under v1.2.

## New in v1.8: sending a tile back costs nothing

Fight 5, turn 4 of `logs/run7` fired the hook and Lightning at a 2 HP Archer that Lightning alone would have killed,
putting the hook on cooldown for nothing. Sending a tile back to hand cost 4, because it has to be reloaded. But
attacking always empties the queue, so that cost only ever weighed firing a tile against sending it back, and a fired
tile has to be reloaded too, after its cooldown. So it always favored firing more. It's gone, and a tile kept ready
in hand is still worth more than one on cooldown. An extra check for tiles that change nothing was tried as well, and
made no difference on top.

On the winning run's 926 boards, 11 top choices change: each makes the same kills and damage with fewer tiles, or
attacks now rather than stepping forward, for 1 more kill and 12 more damage. On the 330 Ronin boards, 2 change, both
keeping the hook. No kills or HP are lost anywhere, and hunts take as long as before.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| **No cost for sending a tile back** | **Scoring** | **Fewer tiles fired for the same result** | **Tiles kept ready for the next turn, and no queue loaded then sent back over and over** |

## New in v1.7: every repositioning move is worth something kept

The player's read: every ability that repositions the hero or others should have some escape value, by how flexible it
is across situations, guessed now and tuned later. Before, only Swap and the Smoke Bomb had one, and spending the
shove cost just 3. The Smoke Bomb's rules now apply to every move: a tile in hand is worth 2/3 of one loaded, one
that acts on a target is worth 1/3 with nobody it can act on, and loaded tiles that would go off with a kill earn
nothing. Several escapes count as the best one plus half of each other. None of this has been played.

On the winning run's 926 boards, 11 top choices change and 7 of those load Shadow Dash instead of another tile,
by 0.5 to 1.3 points. On the 243 Ronin boards, 2 change: one fires for a kill instead of shoving (fight 3, turn 31 of
`logs/run7`). No kills or HP are lost anywhere, and hunts take as long as before.

| Item | Kind | What replays show | What to look for |
|---|---|---|---|
| **Kept values: Swap and Smoke Bomb 12, Shadow Dash 9, Shove and Dash 6, Dragon Punch and Charge 4, the hook 3** | **Scoring** | **First guesses. Few choices change** | **The shove and Dragon Punch kept for when they're needed, rather than spent for collision damage** |
| Each escape beyond the best counts for half | Scoring | A guess | Whether F1 hoards several at once |
| Shadow Dash loaded ahead of other tiles | Scoring | 7 Wanderer boards, by small margins, mostly far from enemies | Whether it closes the gap well, or delays damage |

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
