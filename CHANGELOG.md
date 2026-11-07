# Changelog

Every evaluator version, newest first: what it changed and why. Each is tagged `evaluator-<version>`, and its commit
message has the details and the replay numbers. `evaluator-v1` is the version that won day 1 with the Wanderer. Later
ones are unvetted until real play confirms them, as [`research/unvetted.md`](research/unvetted.md) tracks.

Logs are named in [`research/logs/`](research/logs/). "Rule" means the simulation, read from the game's code;
"scoring" means a judgment in the evaluator.

## v1.20 — Dynamic Boost, and loaded Curse tiles (2026-11-07)
- **Rule:** Dynamic Boost adds its level to the hero's hits after an attack that moved or turned it this turn, not
  to that attack's own hit. A Flip, a step or the shove doesn't count.
- **Scoring:** a loaded Curse tile is worth 0.5, like Shockwave's, since the stack doesn't count the curse it lands.
  The Shockwave weight becomes a table of loaded effects.
- Confirms two traps on one cell both go off: that killed the Shogun in `run7_part3`.

## v1.19 — the Swapper is a tank (2026-11-07)
- **Scoring:** Ieyasu's Swapper (30 HP, hidden in the game) counts as a tank while he lives, so F1 focuses him.
  Moves that act on it still count for what they do.

## v1.18 — Ieyasu's Blade of Patience and Boss-Swap (2026-11-07)
- **Rule:** Boss-Swap trades places with the boss, wherever each is. Not simulating it is what cost 10 HP: F1
  thought Ieyasu's Dash would be blocked by the Swapper.
- **Rule:** Blade of Patience grows 1 a turn while it waits, from the turn after it lands.

## v1.17 — no assumed threat from a mirror's copy (2026-11-07)
- **Scoring:** the Copycat Mirror copies from the hand wherever the hero stands, so the unknown copy counts as
  nothing until it shows. A tile an enemy plays is still assumed to be a short attack.

## v1.16 — traps (2026-11-07)
- **Rule:** a trap goes on the cell ahead and only an enemy moving onto it sets it off, once. The mod logs traps
  (plugin 0.11.0).
- **Scoring:** a planted trap is worth 0.4 of its damage's worth, and the stack counts traps a volley would plant.
- Combo Curse marked known, not simulated: its target is random.

## v1.15 — Fumiko's dash (2026-11-07)
- **Rule:** Fumiko moves like a Strider, to the last free cell.

## v1.14 — no cost for an attack that hits nothing (2026-11-07)
- **Scoring:** the 5-point cost is gone. Only board-changing events are summed along a line, and a fired tile's
  cooldown already shows its cost.

## v1.13 — a loaded Shockwave tile is a 0.5 tiebreak (2026-11-07)
- **Scoring:** v1.12's +3 for the act of loading moves onto the loaded tile, at 0.5: enough to prefer the Shockwave
  version of a tile, never a point of damage. As a value on the position, it holds at a deeper horizon.

## v1.12 — setup value, and loading Shockwave tiles (2026-11-07)
- **Scoring:** the hook's escape value drops from 3 to 1. A kept hook gets setup value: 1 per point of damage of the
  strongest tile reaching 2 cells or less.
- **Scoring:** loading a Shockwave tile worth 3 (replaced in v1.13).

## v1.11 — the Strider's dash (2026-11-07)
- **Rule:** a Strider's move runs to the last free cell. Walking it one cell put the hero between two Katanas.
- The Rain of Mirrors turn is saved in the backlog as a consumables scenario.

## v1.10 — the Warden's explosion (2026-11-07)
- **Rule:** a dying Warden hits its own cell and both beside it for 2, hero included. Wardens it kills explode too.

## v1.9 — Sharp Turn and Sniper (2026-11-07)
- **Rule:** Sharp Turn turns its user, then strikes both cells beside it. Tiles after it fire the new way.
- **Rule:** Sniper adds its level to the hero's hits from 4 or more cells away.
- **Scoring:** with Sniper, the preferred distance may be 4 cells.

## v1.8 — sending a tile back costs nothing (2026-11-07)
- **Scoring:** the 4-point cost for sending a tile back is gone. Attacking empties the queue anyway, so it only made
  firing look better than keeping, and the hook went on cooldown for nothing.

## v1.7 — every repositioning move is worth something kept (2026-11-07)
- **Scoring:** escape values for every move that repositions the hero or others: Swap and Smoke Bomb 12, Shadow Dash
  9, shove and Dash 6, Dragon Punch and Charge 4, the hook 3. Shared modifiers: 2/3 in hand, 1/3 with nobody to act
  on, nothing loaded when the loaded tiles can kill, and half for each beyond the best.

## v1.6 — Smoke Bomb in hand, and Lightning (2026-11-07)
- **Scoring:** a Smoke Bomb in hand is worth 8 kept against 12 loaded, so loading it no longer beats the Spear.
- **Rule:** Lightning strikes the farthest target ahead, passing over Thorns enemies.

## v1.5 — the same rules for every hero (2026-11-07)
- **Scoring:** the Swap hero goes through the kit rules too. A charged Swap is a way out, worth 12 kept, or 18 with
  Two Way Move.

## v1.4 — positioning from the kit, for the Ronin (2026-11-07)
- **Scoring:** without Swap, the hero prefers the farthest distance its tiles hit from, up to 3 cells. Being flanked
  costs 2.5 times as much with no way out. A kept Smoke Bomb has value.

## v1.3 — Shockwave (2026-11-07)
- **Rule:** after a hit, a Shockwave runs through touching enemies both ways, hitting each, and the target again.

## v1.2 — the Ronin (2026-11-07)
- **Rule:** the special move is read from the log. The shove pushes the target as far as it goes.

## v1.1 — Bomb, poison and the rest of v1's run (2026-11-06)
- **Rule:** Bomb (logged as a hazard, plugin 0.10.0), poison, Copycat Mirror, Barricade, Two Way Move's backward
  swaps, frozen enemies. `research/unvetted.md` starts.
- **Scoring:** poison valued like a curse, capped by the enemy's HP.

## v1 — the winning version (2026-11-06)
- The same code as v0.12. It won day 1 with the Wanderer: `run5_full`, fights 9 to 30.

## v0.12 — Volley (2026-11-06)
- **Rule:** a Volley locks onto the hero's cell as its turn begins, and lands there on whoever is on it.

## v0.11 — final boss, Twins and remaining moves (2026-11-06)
- **Rule:** Corrupted Barrage's rings (logged as hazards, plugin 0.9.0), Smoke Bomb, Swap Toss, Mirror, Origin of
  Symmetry, Dragon Punch, the Twins' shared HP, everyone dying with the boss, Perfect Strike, Unfriendly Fire.
- **Scoring:** the Shogun's last statues are tanks: little credit while a boss lives.

## v0.10 — Damaging Move (2026-11-06)
- **Rule:** a swap hits the enemy passed through for the skill's level.

## v0.9 — Grappling Hook, Shielders, enemy shields as extra HP (2026-11-06)
- **Rule:** Grappling Hook, Shield and Shield Allied, the Curse attack, Heavy enemies.
- **Scoring:** an enemy's shield counts as extra HP equal to the weakest available tile.

## v0.8 — an attack that moves the hero isn't wasted (2026-11-06)
- **Scoring:** a Back Charge into nothing still retreats, so it isn't a wasted attack.

## v0.7 — holding a shield (2026-11-06)
- **Scoring:** the hero's shield is worth about 1 HP.

## v0.6 — curse (2026-11-06)
- **Rule:** a curse doubles one hit.
- **Scoring:** worth a fraction of how much better it makes the next hit.

## v0.5 — Free Play tiles join attacks (2026-11-06)
- **Rule:** a Free Play tile joins any attack from hand, rather than being loaded (mod 0.8.0).

## v0.4 — Shadow Dash, duplicate tiles (2026-11-06)
- **Rule:** Shadow Dash lands behind its target. Tiles of the same name are told apart by damage.

## v0.3 — go for kills, moving attacks, Free Play (2026-11-06)
- **Rule:** first-target attacks stop at the first target. Charges and dashes move their user.
- **Scoring:** kills worth more, and a stack is scored by its best volley within a few moves or a flip.

## v0.2 — Swap, free queue edits, frontloading (2026-11-06)
- **Rule:** Swap is considered, and attacks fire any queued tiles in any order (mod 0.7.0).
- **Scoring:** loaded damage and a charged Swap have value.

## v0.1 — the evaluator gets a version (2026-11-06)
- F1 to F4 analyze automatically. Choices unchanged from the first win (mod 0.6.0).
