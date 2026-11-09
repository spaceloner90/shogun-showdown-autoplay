# Changelog

Every evaluator version, newest first: what it changed and why. Each is tagged `evaluator-<version>`, and its commit
message has the details and the replay numbers. `evaluator-v1` is the version that won day 1 with the Wanderer, and
`evaluator-v2.0` the one that finished day 2 with it, killing the Shogun, and `evaluator-v3.0` the one that won
day 3 with the Shadow, searching four turns ahead. `evaluator-v2.5` won day 1 with the
Jujitsuka, a weaker hero to start, in `logs/run10`. Each item is unvetted until real play
confirms it, as [`research/unvetted.md`](research/unvetted.md) tracks.

Logs are named in [`research/logs/`](research/logs/). "Rule" means the simulation, read from the game's code;
"scoring" means a judgment in the evaluator.

## v3.8 — putting off the wave only when it's safe (2026-11-09)
- **Search: the kill that clears the room may be put off only along a guaranteed line**, as the player set: every
  turn until the wave lands fully known, no HP lost, the arrival exact (not held by a crowded room), and the landing
  within the line. Any other line goes below every line that clears the room now. Since v3.6 a line ends where its
  wave lands, scored on that board, so within the horizon the search picks when to bring the wave for the best
  setup (loaded tiles, ready tiles, traps), but a stall through guessed turns was only discounted, which halves a
  guessed hit as well as the setup's worth. `run16` turn 19 now flips and loads the Kunai before the kill.

## v3.7 — potions for hits the hero can't avoid (2026-11-09)
- **Potions: judged against the least HP any line loses without them**, not the best-scoring line's. In `run16`
  turn 29 the best line took 1 HP on its 4th turn for a kill while another lost none, and Mass Curse was drunk to
  save that HP.
- **Potions: Rain of Mirrors, Shield and Freeze Time only for damage this turn**, as the player set: they answer
  attacks already telegraphed, and one drunk for a hit turns ahead does nothing a later one couldn't. Rain of
  Mirrors does most once an enemy has an attack charged. In `run16` turn 28 it was drunk for a hit on the line's 4th
  turn. The combat potions (Cool Up, Mass Poison, Mass Curse) still look over the whole line.
- Both turns now keep their potions.

## v3.6 — lines end at the wave (2026-11-09)
- **Rule: a cleared room brings the next wave at once**, whatever the countdown, and a wave whose countdown runs out
  waits while the room is too crowded for it (`WaveRoom.ProcessTurn`). The countdown itself was already exact.
- **Search: a line ends where its wave arrives**, scored by the board it lands on, as the player chose, instead of
  playing on at 0.85 a turn. Who comes isn't simulated, so playing on scored a board missing them: in `run16` turn
  12, F4 spent the Mirror on a kill that cleared the room (it would be back by the line's end), and the wave came at
  once with the hero flanked. Now it keeps it. The rule alone, with the 0.85, made F4 put the kill off instead.
- Not yet checked on the 551-start fight simulation: stopped, since it starved the live solver of CPU. To run while
  the game isn't being played.

## v3.5 — Kunai (2026-11-09)
- **Rule: Kunai** throws as many knives as its value, each a hit of 1 with the tile's effect on the first agent
  ahead at any range (`KunaiAttack`). A shield stops one knife, a curse doubles one, and each gets the hero's bonuses.
  The game aims each 0.25 s apart; the simulation lets each land before the next is aimed.
- Replay: no past log has it, so no core choice changes.

## v3.4 — Daisuke's AI; Chikara Crush (2026-11-09)
- **Rule: Daisuke's AI is ported** (`DaisukeBoss.AIPickAction`): he turns to face the hero first, steps back after
  attacking, waits a turn after playing a tile unless corrupted, plays the Katana after a lone Charge, and attacks
  when threatening. Into an empty queue his tile is random, so it stays unknown. Corrupted, he has a trait, which is
  how the log tells. In `logs/run16` the search guessed he'd wait while facing away, so it never saw him turn round,
  and took 3 on turn 12; with him ported, F4 keeps full HP over its four turns from turns 8 and 9, and from turn 10
  takes 1 instead of 3. 60 of his logged choices, all predicted right.
- **Rule: Chikara Crush** adds its level to every push collision an enemy takes, whoever pushed it
  (`ChikaraCrushSkill.ProcessAttack`; only `Agent.Pushed` builds collision hits, not traps, bombs or shockwaves).
- Perfect Strike already counts any exact kill while its tile is in progress (`CombatManager.OnPreciseKill`), so a
  Hookblade's chain or a Meteor Hammer's ricochet recharges it; tests added.

## v3.3 — the Chain Master (2026-11-09)
- **Rule: Swap Toss**, the Chain Master's special move, is simulated: the agents on either side of the hero trade
  places, neither turning, and the special move's effect lands on each (`SwapTossSpecialMove`). Its escape value is
  tied to the Throw's, a first guess.
- **Rule: Meteor Hammer** strikes the first agent in range ahead and, only then, whoever is right behind its user.
- **Rule: Hookblade** steps into each enemy it kills and strikes the next one in front for 1 less, while each hit
  kills (`HookbladeAttack`). It counts as a move attack for Dynamic Boost when it moves the hero.
- Replay: no past log has these, so no core choice changes.

## v3.2 — random combo effects at their worst case (2026-11-09)
- **Scoring:** a Chilling Combo or Combo Curse effect with more than one enemy to pick from now counts what it's
  worth on the least valuable of them, as the player chose, rather than a flat 10: a certain one is never worth less
  than a random one, and the search won't plan around a lucky freeze. A freeze is worth 35 to 55 on a board, a curse
  0 to 35, by what it makes of the hero's next hit. The freeze's worth is the ice value's own formula, shared.
- Replay: 2 of 1,009 core choices change, no kills or HP lost.

## v3.1 — combo skills simulated; no full-bag potions (2026-11-09)
Tagged `evaluator-v2.28` first, then renamed when v2.27 became v3.0.
- **Rule: Combo Recharge** is simulated: each combo kill while one of the hero's tiles fires gives that tile 4 a
  level back once it's done, capped at full (`ComboRechargeSkill.OnComboKill`,
  `Tile.PostExecutionCooldownRechargeSequence`).
- **Rule: Chilling Combo and Combo Curse** are simulated when exactly one enemy can be picked (alive with at most 1
  ice; alive and not cursed), as the player suggested; otherwise their random effect keeps its small value.
- **Rule fix: the Phase's effect lands on every agent it passes**, not just the first (`PhaseSpecialMove.Perform`
  loops over them): `logs/run15` showed Mamushi Move poisoning two at once.
- **Potions:** F2+ no longer drinks one only for kills when the bag is full, as the player asked: a potion left on
  the ground pays a coin, and in `run15` a Freeze Time drunk that way in fight 9 was missing in fight 12.
- `logs/run15`, the Shadow's day 3: two hits in fights. Predictions now 859 of 879 turns exact (830 on v2.27), the
  rest almost all enemies arriving. Replay: 8 of 1,009 core choices change, kills even, no HP lost.

## v3.0 — won day 3 with the Shadow (2026-11-09)
`evaluator-v3.0` is v2.27, unchanged, renamed by the player: it won day 3 with the Shadow in `logs/run15` with two
hits taken in fights, the first full run on F4, the search ahead with the ported enemy AI (v2.16 to v2.27). Below
are the versions that made it.

## v2.27 — potions judged over four turns (2026-11-09)
- **Potions, as the player set:** with the solver server, each potion held gets its own F3 and F4 search of the
  board after drinking it, alongside the main ones, and is judged on HP lost and kills along the best line, at F4
  if everything finished in time, else F3. Any potion that cuts the HP lost is used, the one saving most; on a tie,
  combat potions first (Cool Up, Mass Poison, Mass Curse), then Rain of Mirrors, then Shield and Freeze Time. Cool
  Up is back in play, since recharged tiles pay off over later turns. With every slot full, one adding kills is
  used, as before. D6 stays the last resort against damage this turn; a potion takes the key press, so the next
  one looks again.
- **Edamame:** with Triple Combo Heal, used once 6 HP are missing, not 3.
- **The fight before the Shogun's:** Freeze Time first among potions that save HP, since he can't be frozen. Mod
  0.18.0 logs `progression` (day, island, room and room count, whether in the Shogun's castle) to tell it.
- Without the server, potions use the old one-turn rules. Potions don't appear in replays, which use F1.

## v2.26 — enemies' hidden AI memory; the Summoner and Swapper (2026-11-09)
- **Mod 0.17.0** logs what some enemies' AI remembers between turns (`memory`): the Shinobi's and Warden's last
  tile (`prevAttack`, `previousAttack`), the Summoners' countdown and full wait (`waitBeforeSummoning`,
  `TurnsToWaitBeforeSummoning`) and the Swapper's (`waitCountdown`). The solver reads them, and uses the game's
  own logged `tileToPlay` for a telegraphed PlayTile.
- **Rule:** the Summoner and Swapper are ported (`SummonerEnemy.AIPickAction`, `SwapperEnemy.AIPickAction`: the
  Swapper waits 3 between swaps). The Summoner can't be moved (`SummonerEnemy.get_Movable`). Both stay unknown on
  logs before 0.17.0.
- `logs/run14`, the Shadow's day 2, finished: no hits after v2.20 but a manual key press, and two blocked by a
  shield. 764 of 786 turns predicted exactly, the rest enemies arriving and the Sato boss.
- Replay: 1 of 921 core choices changes. `tools/condense.py --add` now also takes new boards from a log that grew.

## v2.25 — Monomancer; Big Pockets by level (2026-11-08)
- **Rule:** Monomancer adds its level to the hero's hits on an attack fired with one tile in the queue
  (`MonomancerSkill.OnHeroAttacks`, `ProcessAttack`). Not on collisions. Reach doesn't count it; the stack and the
  search do.
- **Fix:** Big Pockets adds a potion slot per level (`PickUp` and `LevelUp` each add one); only one was counted.
- **Checked:** every other level-scaled skill (Back Stabber, Close Combat, Damaging Move, Dynamic Boost, Sniper,
  Unfriendly Fire) adds its level, as the solver reads it. Combo Recharge's level isn't simulated; the rest don't
  change with level.
- No choice changes on the core.

## v2.24 — combos: Triple Combo Heal simulated, combo skills valued (2026-11-08)
- **Rule:** the turn's kill streak counts every enemy death, by anyone, poison and blasts included, inanimate things
  not (`CombatManager.OnEnemyDied`); from the second, each is a combo kill. Triple Combo Heal heals the hero 1 at
  once on each from the third, nothing past full HP (`TripleComboHealSkill.UponComboKill`).
- **Scoring:** HP healed is worth what HP lost costs, tied in code, so F2+ will set up a triple over several turns
  when it's worth it. Combo Curse and Chilling Combo, random, add 10 per combo kill each, a first guess, as the
  player asked: a little, for setting up combos at no other cost.
- `run9`'s one Triple Combo Heal is now predicted. No choice changes on the core.

## v2.23 — Back Stabber (2026-11-08)
- **Rule:** Back Stabber adds its level to the hero's directional hits (all but Lightning, Scar Strike and Smoke
  Bomb) on an enemy facing away from where the tile began, so not a dash's arrival behind it
  (`BackStabberSkill.ProcessAttack`). Not on collisions. The logs' `directional` flag is now read. Reach doesn't
  count it, since it depends on the enemy's facing; the stack and the search do.
- No logged run has it: no choice changes on the core.

## v2.22 — Close Combat (2026-11-08)
- **Rule:** Close Combat adds its level to the hero's hits on an adjacent enemy, unless the tile making the hit
  moved the hero: a Charge's or Smoke Bomb's own hit gets nothing, but the tile after it does, since the game
  records the hero's cell as each tile begins (`CloseCombatSkill.ProcessAttack`, `Agent.ExecuteTile`). Not on
  collisions, as with Sniper. Reach counts it for tiles that hit from beside the target.
- No logged run has it: no choice changes on the core.

## v2.21 — F2+ takes kills now, not later (2026-11-08)
- **Search fix:** with no discount on known turns, a kill now and the same kill a turn later score alike, and the
  search broke such ties on the board left after this turn, as F1 does, which favours keeping tiles loaded. In
  `run14` (fight 7, turns 20 to 21) F4 waited with a volley that killed three, and in the simulator a lone Twin
  Tachi was never attacked. Ties now go to the line whose events come sooner (each turn later counting 0.9 for that
  only); scores are unchanged.
- Simulator, 120 starts: F4 left 4 uncleared in 60 turns before the fix and none after, in 803 turns rather than
  1,052, losing 1 HP.

## v2.20 — unknown enemies are assumed to fire (2026-11-08)
- **Search:** an enemy whose AI isn't known (bosses mostly) is now assumed to attack with what it holds whenever
  that would hit the hero, and to wait otherwise. In the logs such enemies attacked on 165 of 207 turns they could
  hit the hero, most bosses every time, Rei on 19 of 28, and on 8% of turns they couldn't. Before, the search had
  them wait, and planned on that.
- **Search:** a turn with a guessed enemy action counts at 0.5, from F1's future discount of 0.85, which still
  applies to a wave about to arrive, as the player asked: new enemies do nothing the turn they come. In `run14`,
  the Shadow's turn 14 against Rei, F4 dashed away to attack a turn later, counting on Rei waiting; it now attacks
  now, by 9.2. The 2 HP lost there was unavoidable either way: Rei's loaded Charge reached the whole row.
- F1 is unchanged on the core boards.

## v2.19 — Twin Tessen, and F4 always answers (2026-11-08)
- **Rule:** Twin Tessen hits the agent on each side of the hero for its damage, 1 to start, cooldown 6, then
  pushes each movable one it hit away from the hero as far as it goes, dead or not, a collision hitting both
  (`TwinTessenAttack.ApplyEffect`, `PerformPushing`).
- **Scoring:** escape value 4, Dragon Punch's: it moves both neighbours but hits for less. A first guess.
- **Fix:** answered without the solver server (the first key press after the game starts, or after solver code
  changes), F2 to F4 now share 1 s on one core, a depth that runs out playing the next one down's choice. Before,
  that answer stopped at F3, and the mod analyzes a board only once, so the F4 key did nothing until the board
  changed, as the player found.
- No logged deck has Twin Tessen: no choice changes on the core.

## v2.18 — the hero's Mirror (2026-11-08)
- **Rule, checked:** the hero's Mirror is the Shogun's (`MirrorAttack`), already simulated: across the room's
  middle, the left one of two on an even room, trading places with whoever is there, both turning round; refused
  for an immovable occupant. It's always a Free Play tile (`MirrorAttack.Initialize`), cooldown 6, no damage.
- **Scoring:** Mirror gets an escape value, 9 like the Shadow Dash, which also lets its reach gain count.
- **Fix:** a Free Play movement tile in hand counted only two thirds of its escape value, as if it had to be loaded
  first; it joins any attack from hand, so it now counts in full.
- Replay: 1 of 833 core choices changes (`run9`), nothing lost.

## v2.17 — F2 to F4 search ahead with the enemy AI (2026-11-08)
- **New:** the F2, F3 and F4 keys search that many turns ahead (`solver/search.py`), playing the turns out with
  the ported enemy AI. A turn with every enemy action known counts in full, as the player asked; one with an unknown
  counts at F1's future discount. A win only scores as a win on the turn chosen, as in F1, or the search puts it off.
  F1 is unchanged.
- **Speed:** `State.clone` instead of deepcopy, cheaper reach, a narrow last turn, merged duplicate lines, and a
  solver server (`solver/server.py`) that keeps workers warm and runs every depth in parallel. F2 to F4 get 0.45 s;
  a depth that runs over plays the next depth down's choice.
- **The fight simulator** (`tools/simulate.py`): from all 551 logged fight and wave starts where every enemy is
  ported, F1 was hit on 43 turns for 82 HP, F2 on 28 for 57, F3 on 19 for 34, F4 on 12 for 20. Every policy
  cleared every start in time but F1 (1) and F2 (2). Waves to come aren't spawned there, and no potions are used.

## v2.16 — the regular enemies' AI (2026-11-08)
- **Rule:** the AI of 14 regular enemy kinds is ported from the game's code (`solver/enemy_ai.py`): Ashigaru, Yari
  Master, Guardian, Twin Tachi, Sniper, Archer, Charger, Strider, Grappler, Shinobi, Warden, Shadow Dasher, Blight
  Charger and Barricade. At each turn's end every enemy chooses its next telegraph from the board
  (`Enemy.DecideNextAction`); bosses, the Kabukai, Shielder, Summoner and Swapper, and choices resting on something
  the board doesn't show, stay unknown, as before. A tile an enemy plays is now the real one, not a placeholder.
- The player lifted the rule that kept the enemy AI out of the live solver, for F2+ with real lookahead.
- `tools/check_ai.py` checks the telegraphs against the logs: 99.8% of the 7,399 the AI claims to know are right,
  72.5% of all enemy-turns; most misses are Chilling Combo freezes, which aren't simulated.
- F1 replay: 14 of 833 core choices change, 3 fewer kills, all near-ties moved by enemies' tiles being known.

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
