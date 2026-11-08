# Changelog

Every evaluator version, newest first: what it changed and why. Each is tagged `evaluator-<version>`, and its commit
message has the details and the replay numbers. `evaluator-v1` is the version that won day 1 with the Wanderer, and
`evaluator-v2.0` the one that finished day 2 with it, killing the Shogun. `evaluator-v2.5` won day 1 with the
Jujitsuka, a weaker hero to start, in `logs/run10`. Each item is unvetted until real play
confirms it, as [`research/unvetted.md`](research/unvetted.md) tracks.

Logs are named in [`research/logs/`](research/logs/). "Rule" means the simulation, read from the game's code;
"scoring" means a judgment in the evaluator.

## v2.15 — Mamushi Move (2026-11-08)
- **Rule:** with Mamushi Move, the special move poisons its target for the usual 3 turns, if it's still alive after
  Damaging Move's hit, and before a shove pushes it (`MamushiMoveSkill.SpecialMoveEffectOnTarget`,
  `PushSpecialMove.Perform`). Its longer cooldown shows in the log. In `logs/run13`, the Ronin's day 2, all 9 shoves
  after it was picked poisoned, unknown to F1; poison was already valued on the position, so now it counts.
- The prediction checker now compares poison and ice too; poison was why these misses went unseen.
- Replay: 24 of `run13`'s 897 choices change, 11 more kills and 36 more damage, no HP lost. None elsewhere.

## v2.14 — reach counts facing (2026-11-08)
- **Scoring:** a tile's reach only counts from where it points at the target, its range read from the way the hero
  faces, and a flip costs an action like a move. Before, ranges counted either way, so in `logs/run12` Back Strike
  counted as reaching Kowa standing in front. Still a credit, and more options only lower the actions needed, so
  the three rules hold. Decisions take about 0.056 s.
- Replay: 151 of 5,186 choices change, 2 more kills and 7 more damage, no HP lost. Back Strike loads on `run12`
  barely move (52 to 51): what drives them is the stack crediting flip-then-fire, at the same fraction as a step.

## v2.13 — Back Strike (2026-11-08)
- **Rule:** Back Strike hits the first agent on the cell behind the hero, a plain hit: 3 damage, cooldown 3
  (`BackStrikeAttack.ApplyEffect`). Tetsubo, the other choice on offer, was already simulated.
- No logged deck has it, so no choice changes in replays.

## v2.12 — the reload follows the loaded Crossbow's worth (2026-11-08)
- **Scoring fix:** a reload is worth a ready tile with its damage loaded, and v2.11 raised a loaded Crossbow's
  damage by its pierce without raising the reload. Both now read one function, so any change to either moves both:
  11 for a 3-damage Crossbow, from 8. The damage itself was already the tile's logged base damage.
- Replay: 2 `run12` choices now load the empty Crossbow to reload, over Scar Strike; no other change.

## v2.11 — piercing tiles' potential (2026-11-08)
- **Scoring:** a tile that can hit two in a line counts for more than its stated damage where its potential is
  valued, loaded damage and reach, as the player asked, like an effect: the Crossbow 1.5 times, since it hits any 2
  across its range, and the Spear 1.25 times, needing them on the 2 cells ahead. First guesses. What either does
  when fired counts as it happens.
- As the player expected, this makes keeping and loading them a little more attractive, the Crossbow included.
  Not using a big setup when a small one does the job needs a sense of waste that F1 can't see far enough for, so
  that's held off.
- Replay: no change on the Shadow's logs; 24 on the Wanderer's with the Spear, 2 fewer kills, both near-ties where
  keeping the Spear's reach beat killing now (`run5_full` 21:21 and 17:25).

## v2.10 — a reload isn't a wasted attack (2026-11-08)
- **Fix:** F1 drops any attack where a tile fires at nothing, and a Crossbow's reload hits nobody by design, so no
  attack that reloaded was ever offered. The stack still credited the reload, so in `logs/run12` F1 kept loading
  the empty Crossbow and sending it back to hand when it attacked.
- Replay: those 3 `run12` attacks now take the reload along; nothing else changes.

## v2.9 — the Crossbow, and reach by real movement (2026-11-08)
- **Rule:** the Crossbow alternates. Loaded, it hits the first 2 agents in range for its damage, 3 to start, and
  empties; empty, its next use reloads it to its base damage and hits nobody (`CrossbowAttack.ApplyEffect`,
  `Attack`, `Reload`). Its cooldown runs after either. Mod 0.16.0 logs each tile's base damage (`baseValue`); before
  it, an empty Crossbow is taken to reload to 3.
- **Scoring:** a reload is worth having its loaded tile ready, as the player put it: a ready tile (2) plus its damage
  loaded (2 a point), 8 for 3 damage. It counts when the reload fires, like damage, so loading one shows in the
  stack, and the shot it sets up counts for its own damage when that fires (rule 2).
- **Scoring:** reach counts the actions it takes to get in range, a quarter off each, rather than the cells. Plain
  moves are walked as the hero really moves, blocked by anyone in the way and dashing for the Shadow; for a walker in
  open space nothing changes. What the special move or a movement tile adds by one use on the way is a third use of
  it, beside escape and setup, and it counts the largest (rule 2). A tile in hand takes an action to load first.
- Replay: 45 of 4,463 choices change, no HP lost, total kills unchanged and 1 more damage. Decisions take about
  0.07 s, from 0.05.

## v2.8 — the Shadow dashes when it moves (2026-11-08)
- **Rule:** every move the Shadow makes is a dash to the last free cell that way, next to whoever stops it or at the
  wall (`ShadowHero.PerformMoveAction`, `Dash`: `Cell.LastFreeCellInDirection`). Into an occupied cell it's still the
  Phase. In the first two fights of `logs/run11`, v2.7 missed all 15 of its moves; now 75 of 75 turns match.
- **Evaluator:** the stack walks to where moves actually go, so for the Shadow one move reaches the cell next to the
  enemy, and stepping aside from a threat lands where the dash does.
- Replay: 10 of 77 `run11` choices change, 1 fewer kill and 2 less damage, no HP lost: closing in is one move now,
  so F1 dashes in for a bigger volley more often, once (fight 2, turn 22) over a kill now. None on older logs.

## v2.7 — the Shadow's Phase (2026-11-08)
- **Rule:** Phase (`PhaseSpecialMove`) takes the hero through the agent next to it, and any in a row behind it, to the
  first free cell past them; nobody moves. It needs someone adjacent, movable or not, and a free cell before the wall,
  and goes only the way the hero faces, unless Two Way Move (`PhaseSpecialMove.Allowed`, `PotentialPhaseCell`).
  Damaging Move hits the first one passed.
- **Scoring:** the same as the Swap: escape value 12, and a charged Phase counts as a way out.
- No logged board has the Shadow yet, so no choice changes in replays.

## v2.6 — Reactive Shield, and when Nobunaga's lights move (2026-11-08)
- **Rule:** with Reactive Shield, the hero gets a shield whenever it takes damage and lives without one
  (`ReactiveShieldSkill.UponHeroTookDamage`). Shield Retention and Fortress need nothing simulated, since their
  shields show in the logged state.
- **Rule fix:** Nobunaga's lights move at the very end of the turn, after poison ticks, and only when his HP has
  dropped (`Room.ProcessTurn` runs after `Agent.EndOfTurn`). v2.5 moved them at the start of the enemies' turn, so it
  had the tick at the end of the turn he was hurt blocked; in `logs/run10` it landed.
- **Scoring:** with Reactive Shield, going without a shield is worth half a shield, since the next damage brings one:
  hits alternate between blocked and taken either way. Without that, a 1-damage hit would score as free, its HP
  paid back by the shield it brings. Now a hit costs its HP less half a shield, and losing a shield costs half.
- `logs/run10`, a full Jujitsuka run that beat Nobunaga without losing HP to him (51 turns): 836 of 853 turns
  predicted exactly, the rest all enemies arriving. Replay: 6 of its 875 choices change, for 2 more kills and 4 more
  damage, no HP lost; none on older logs.

## v2.5 — Nobunaga's armor and spotlights (2026-11-08)
- **Rule:** Nobunaga can only be hurt on a spotlit cell; anywhere else his armor stops the whole hit, poison ticks
  included, though a tile's effect still lands (`NobunagaBoss.ReceiveAttack`, `Attack.HitTarget`). 3 cells are lit
  above two-thirds HP, 2 above a third, then 1. On his turn the lights move, at random, whenever his HP has changed
  since his last turn; the simulation then counts nothing as lit, since where they go is unknown.
- **Scoring:** while he's dark he isn't the ideal target, and tiles earn no reach credit against him. The stack
  still finds volleys that trade him onto a lit cell, such as a Smoke Bomb from a lit cell.
- **Mod 0.15.0** logs the lit cells (`litCells`) and his HP at his last turn (`nobunagaHpLastTurn`). Older logs have
  neither, so their boards replay unchanged: no choice changes on 3,511 boards.
- In `logs/run9` the Jujitsuka died to him at turn 146 with him on 3 HP, F1 having attacked him repeatedly in the
  dark, thinking it could kill.

## v2.4 — Sai (2026-11-08)
- **Rule:** Sai hits the first agent on the cell ahead for its damage, 2 to start, twice that on an enemy
  telegraphing an attack this turn: a counter (`SaiAttack.ApplyEffect`). Cooldown 5.
- No logged deck had it, so no choice changes in replays.

## v2.3 — a simpler wound value (2026-11-08)
- **Scoring:** with Scar Strike anywhere in the deck, each wounded enemy is worth half of its damage there, up to
  the enemy's HP, as the player asked: no discount while it cools down, since its cooldown is short, and no kill
  bonus, since a kill it would make shows in the stack.
- Replay: on `run9`, 7 of 114 choices change from v2.2. Fight 1, turn 7 flips to set up Dragon Punch and Scar
  Strike killing the 2 HP TwinTachi next turn, rather than chip the 3 HP Ashigaru now.

## v2.2 — wounds for Scar Strike, and Dragon Punch's flying bodies (2026-11-08)
- **Scoring:** with Scar Strike, each wounded enemy is worth half of what its hit on it would be, more where it would
  kill, discounted per turn until it's ready: so a 1-damage chip on an enemy at full health is worth half as much
  again, as the player asked. A value on the position, like the curse's, so it's gone once Scar Strike is spent.
  Scar Strike's reach credit from v2.1 is dropped, since where the hero stands doesn't matter to it.
- **Rule:** Dragon Punch pushes its target even when the hit kills it, so the body still hits whoever stops it, in
  `logs/run9` twice, once into the hero for 1. A collision no longer counts a kill twice when it kills a boss.
- Replay: no change on the older logs. On `run9`, 8 of 114 choices change, for 4 more damage and no kill or HP lost.

## v2.1 — winning, deaths alongside a boss, and the Jujitsuka (2026-11-08)
- **Scoring:** winning the fight this turn at no HP cost beats anything, as the player put it. A win that costs HP
  this turn earns nothing extra, since HP carries into the next fight and a safe win may be a turn away: a lone
  Warden beside the hero is still killed from range a turn later rather than take its blast. Rei
  (`logs/run6`, fight 3, turn 36), passed up since v1.27, is killed again.
- **Rule:** enemies that die alongside a boss count as kills, with their HP as damage, except tanks and anything
  inanimate, like a Barricade. A won fight is a dead boss, or a cleared last wave or room without waves.
- **Rule:** the Jujitsuka's Throw: the enemy behind the hero goes over it to the front, then is pushed on as far as
  it goes, hitting whoever stops it, like the shove. Only toward the hero's back without Two Way Move, and only
  onto a free cell in front. Kept, it's worth 6 as an escape, the shove's value, as a first guess.
- **Rule:** Scar Strike hits every enemy below full health, wherever it is, chosen as it begins, so earlier tiles
  in the volley can add targets. It earns reach credit on a wounded target from anywhere.
- Replay against v2.0: 4 of 2,710 choices change, Rei among them, with no kill or HP lost.

## v2.0 — day 2 won (2026-11-08)
- The same code as v1.28. With it the Wanderer finished day 2 and killed the Shogun: `run8` and `run8_part2`, the
  last four fights on v1.28 for 4 HP, 1 of it against the Shogun. The player credits much of it to Chilling Combo,
  and to freezing in general, which matters most in wave fights, more dangerous here than the bosses.
- What changed from v1 to here is everything from v1.1 to v1.28 below: the Ronin and positioning from the kit,
  Shockwave, curses and poison, traps, Sniper and Dynamic Boost, the day 2 bosses, elites, freezing, consumables,
  loading with a swap, and since v1.27 scoring rebuilt on three rules that outrank any term.

## v1.28 — attacking potions when every slot is full (2026-11-08)
- **Scoring:** D6 is the last resort against damage no other potion avoids, whenever it comes, as the player put
  it, rather than only under pressure.
- **Scoring:** Mass Poison, Mass Curse and Cool Up for a kill are used only with every potion slot full, when
  one held back would crowd out the next one found. They were used under pressure, below a best score set from the
  logs, but every scoring change moves scores: v1.27's reach credit had shrunk the worst 30% to about a fifth. The
  player dropped the cutoff rather than keep measuring it again. The hero holds 3 potions, and Big Pockets adds one.
- Combo Recharge marked known, not simulated, as the player asked.

## v1.27 — scoring rebuilt on three rules (2026-11-08)
The three rules, in `research/design.md`: having more never scores lower, a tile has one use at a time, and terms
that read the tiles only give credit. Every term was checked against them, and `solver/test_principles.py` checks
the first on every logged board: on v1.26 it failed 309 times, now none.
- **Scoring:** the stack scores a volley with the board it leaves, its tiles spent, against keeping them all, at
  its fraction. Every volley size is tried, here and when looking for an answer to a threat.
- **Scoring:** escape and setup no longer drop to nothing when the loaded tiles can kill. The stack weighs that
  now. A tile counts the larger of its escape and setup values, not both.
- **Scoring:** a curse is worth its best gain on any one tile.
- **Scoring:** distance and crowding are replaced by reach, credit for each tile that can hit the target from
  here, and a small cost per adjacent enemy.
- **Scoring:** breaking a shield is valued at the deck's weakest tile, not the weakest ready one.
- A decision takes about 0.11 s, from 0.02 s.

## v1.26 — loading with a swap, no tile fired at nothing, and freezing at half a kill (2026-11-07)
- **Rule:** with the queue full, loading can send a queued tile back to hand first, a free queue edit, as one action.
  F1 never saw this, which is what kept the stalemate in fight 11 of `logs/run8` going. **Mod 0.13.0** makes the edit
  before loading.
- **Scoring:** an attack that fires a tile at nothing is left out, since sending that tile back instead is free and
  leaves the same board with the tile still ready. Firing Shadow Kama at nothing had won by taking it out of the
  tiles the position terms read, and with it the penalty for standing closer than the Kama reaches.
- **Scoring:** a freshly frozen enemy is worth half of killing it, 60 plus 10 per HP, as the player asked, falling
  as its ice runs out. It was 5 per turn of ice per point of its strongest attack.

## v1.25 — potion pressure at 30%, and Cool Up to avoid damage (2026-11-07)
- **Scoring:** pressure is now the worst 30% of boards, a best score below 11.
- **Scoring:** Cool Up also counts as a damage-avoiding potion, since recharging the special move or an escape tile
  can avoid a hit. It's preferred first when it saves as much, being the most conditional.

## v1.24 — elites, and potion pressure at 20% (2026-11-07)
- **Rule:** Double Strike plays an attack twice, targeting afresh, for any agent; the Double Strike elite gives its
  attacks the effect. Reactive Shield elites gain a shield after a hit that hurts them while unshielded. Quick only
  changes enemy AI, so it needs nothing.
- **Scoring:** pressure for attacking potions and D6 is now the worst 20% of boards, a best score below -3.

## v1.23 — Shadow Kama for the hero (2026-11-07)
- **Rule:** Shadow Kama strikes only the first agent its range finds. With the statue's range of the cell 2 ahead,
  that's what the simulation already did; it matters only if a tile's range is wider.

## v1.22 — consumables (2026-11-07)
- **Rule:** each combat potion's effect, from the game's code. Using one is free and doesn't end the turn.
- **Scoring:** the player's rules. Edamame once the hero is missing 3 HP. Shield, Freeze Time and Rain of Mirrors
  only to lose less HP this turn, preferring the Shield. Under pressure, the worst 10% of boards by best score,
  Mass Poison, Mass Curse and Cool Up only to make a kill, and D6 against damage nothing else avoids. Each potion is
  checked by ranking every move again with it applied.
- **Mod 0.12.0:** a key press uses the potion instead of acting, and the next one plays the turn.

## v1.21 — freezing (2026-11-07)
- **Rule:** an Ice hit sets 4 turns of ice on an enemy that can be frozen, and cancels what it telegraphed this turn.
  While it has ice it does nothing, so it loses that turn and the next three. Its queue stays.
- **Scoring:** each turn of ice left is worth 5 per point of the enemy's strongest known attack, 2 if none is known,
  like poison's turns. The stack counts ice a volley would land, and a loaded Ice tile gets the 0.5 tiebreak.

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
