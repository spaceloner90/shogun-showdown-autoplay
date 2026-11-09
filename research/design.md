# Design

How the autoplay decides, and why it's built the way it is. The other documents cover the rest:
[`rules.md`](rules.md) has the game's rules as worked out from its code and from play,
[`unvetted.md`](unvetted.md) what real play hasn't confirmed yet, and
[`evaluator_backlog.md`](evaluator_backlog.md) what's still open.

## The goal

An AI that plays Shogun Showdown one turn at a time: each key press plays one turn, and the log says where the
decision came from. `evaluator-v1` won day 1 with the Wanderer, and `evaluator-v2.0` day 2, killing the Shogun. The
aim now is to beat the full game, with other heroes and kits.

## Ground rules

- **The enemy AI is fair game.** Since v2.16 the regular enemies' AI is ported from the game's code
  (`solver/enemy_ai.py`) and runs live: the player dropped the earlier rule against it, to see how much better real
  lookahead plays. What's hard to simulate (bosses, random choices, spawns) stays unknown for now.
- **F1 looks one turn ahead; F2 to F4 search.** F1 scores each action available now by where it leads, so
  everything a plan needs has to show up in how a position is scored. F2 and deeper (`solver/search.py`, see "The
  search") play the next turns out with the enemy AI.
- **Fuzzy, not exact.** Values are judgments with round numbers, guessed first and tuned against real play. Being
  roughly right everywhere beats being exact in the cases tested.
- **Explainable.** A score is a sum of named terms, and the report and logs show them, with the version that made
  each decision.

## How an action is scored

`rules.py` simulates the turn: the hero acts, then enemies do what they telegraphed, then end-of-turn effects
such as poison and hazards. Its rules come from the game's code, and it's checked against what logs show actually
happened. Where a summon lands is random, so a player can't plan around it either: summons aren't simulated.

`evaluator.py` then adds up two kinds of terms:

1. **What the turn did.** Damage dealt (10 per HP), kills (60 each), HP lost (-100 per HP), damage enemies did to
   each other, and so on. Only events that change the board belong here, summed turn by turn along a line and
   discounted for each turn ahead. An action that only prepares something, like loading a tile, isn't one: what
   it's worth shows in the final position, or in what the line does with it. Nor is an attack that hits nothing:
   its cost is already in the tile going on cooldown, which the position shows.
2. **How good the position it leaves is.** This is where everything beyond the next turn lives:
   - **The stack:** what firing the loaded tiles adds beyond keeping them, from here or after a few moves or a
     flip, discounted for each action needed, with every firing order and size tried. A volley is scored with the
     board it leaves, its tiles spent, against this board with them all kept (rule 2). A kill is worth far more
     than a wound, so a loaded volley that kills counts for a lot.
   - **Tiles:** charged ones, and damage loaded.
   - **What's kept:** charged moves that are worth more than their damage (escape and setup, below).
   - **Statuses:** poison still to come, curses on enemies, the hero's shield.
   - **Where the hero stands:** facing the right enemy, how much of the kit can reach the target from here, a
     small cost for each enemy adjacent, and being flanked or surrounded, which is much worse with no way out.
   - **Pressure:** enemy HP left in the room, more so as the next wave nears.
   - **Threats with no answer:** damage queued against the hero that nothing available could avoid.

## Principles

### Three rules every score keeps

These come first. The rest of the evaluator was built up piece by piece, and where a piece breaks one of these, the
piece is wrong, however sensible it looked alone.

1. **Having more never scores lower.** A ready tile never scores below the same tile on cooldown, and a loaded tile
   never below the same tile in hand. In the game the hero can always leave a tile unused, and sending one back is
   free, so a tile can't make the position worse. A score that says otherwise gives F1 a reason to throw the tile
   away: Shadow Kama was fired at nothing to shed a positioning penalty.
2. **One tile, one use.** A tile's uses (fire it, keep it to escape or set up, keep it ready) are alternatives. A
   position counts the best way to use its tiles, never several uses of one tile at once. Adding them up made
   waiting with a killing volley loaded look as good as killing, and the patch for that broke rule 1.
3. **Terms that read the tiles only give credit** for what they can do, and never penalize what they aren't doing.
   A penalty that grows with the tiles makes having them a burden.

Where the game itself punishes holding something, like the Copycat Mirror copying a tile from the hand, that's the
simulation's to play out, not a score's. Every rule, old or proposed, is checked against these three in theory
before it's built, and `test_principles.py` checks rule 1 on every logged board.

### Every term against the three rules

As of v1.27, checked in theory:

| Term | Rule 1 | Rule 2 | Rule 3 | What changed in v1.27 |
|---|---|---|---|---|
| Stack | Broke: only full-size volleys were tried, so a tile that hurt a volley's last place could lower it | Broke: credited firing tiles that the kept terms also credited keeping | Keeps | The position is the better of keeping everything, and the volley (at its fraction) plus what it leaves kept. Every volley size is tried |
| Escape, setup | Broke: a loaded tile earned nothing when the loaded tiles could kill, but 2/3 in hand | Broke: the hook earned escape and setup at once; and see the stack | Keeps | The zeroing is gone, the stack handles it. A tile's kept worth is the larger of its escape and setup values |
| Ready tiles, loaded damage | Keeps | See the stack | Keeps | Read after the volley, in the stack's case |
| Loaded effects tiebreak | Keeps | Keeps: an effect once fired shows in the volley | Keeps | |
| Curse | Broke: zero whenever something was loaded; and a tile that kills anyway made the curse look worthless | See the stack | Keeps | The curse's best gain on any one tile, counting every tile |
| Distance, crowding | Broke: both grew with the tiles ready soon | Keeps | Broke | Replaced by reach and stand-off |
| Reach (new) | Keeps: each tile only adds, more charge adds more | Read after the volley, in the stack's case | Keeps | Credit per tile for reaching the target from here, falling off per cell, discounted per turn until ready |
| Stand-off (new) | Keeps: doesn't read the tiles | Keeps | Keeps | A small cost per adjacent enemy |
| Flanked, surrounded | Keeps: a way out only lowers it | Keeps | Keeps: it's a credit for a way out | |
| Facing, pressure, poison, ice, traps, shield, special charged | Keep: they don't read the tiles | Keep | Keep | |
| Shields broken, shield as HP | Broke: valued at the weakest ready tile, so a weak tile ready lowered it | Keeps | Keeps | Valued at the weakest tile in the deck |
| Threat with no answer | Broke: only full-size volleys were tried as answers | Keeps: a risk check, not a credit | Keeps | Every volley size is tried |
| Damage, kills, HP lost along the line | Keep: events | Keep | Keep | |

### Extend the existing patterns

A new consideration goes into the patterns already here when it can: a value on a move or tile, with the shared
modifiers, a term in the position's score, or a rule in the simulation. A new kind of mechanism is a last resort,
and is raised with the player before it's built, not after. The one time this was skipped, the Shockwave value
went in as a bonus for the act of loading, which double counts at a deeper horizon and had to be redone.

### An estimate disappears when what it stands for happens

Anything valuing what's likely to come, like a kept escape, poison still to tick or a loaded Shockwave tile's
chains, is read from the position a line ends in. That way it's gone once the line has played out what it stood
for, and the result is only counted once. A value added for taking an action stays in the line's total even after
a later turn in that line has scored what it was meant to stand for. At depth 1 the two are the same, but with
deeper search the action version double counts.

### General rules, not special cases

Every hero goes through the same rules. When the Ronin came along, the first version kept the Wanderer on its old
"close in and face" rule, since that's what had won. The player preferred going forward with one general solver,
and developing it further wherever going back to an old log shows it worse. Since v1.5 nothing is fenced off by
hero.

### Where to stand comes from the kit

Each tile earns credit for being able to hit the target from where the hero stands, by its damage up to the target's
HP, less a share for each cell the hero would have to move, and discounted for each turn until it's ready. Each
enemy adjacent costs a little, whatever the tiles. So a melee kit closes in, since its credit only comes adjacent,
and a kit that hits as hard from further away stands off. Until v1.27 this was a preferred distance with penalties
for being closer or further, which broke rule 1: a tile on cooldown dropped out of it, so firing Shadow Kama at
nothing removed a penalty.

### Effects beyond damage are values on the move

Some moves are worth more than their damage, and F1 can't play out the turns where that pays off. So each gets an
intrinsic value, guessed from how flexible it is across situations and scaled by the kit where that makes sense:

- **Escape:** any move that repositions the hero or an enemy is a way out of trouble later. Swap and Smoke Bomb
  get the hero past an enemy and are worth the most. A shove or a Dash moves someone away. The hook brings enemies
  in, which almost never helps, so it's worth the least.
- **Setup:** a move that brings an enemy in is worth more when the kit has a short-reach tile to exploit it, in
  proportion to that tile's damage.
- **A loaded tile with an effect the stack doesn't score:** worth a little more. Shockwave, for chains it may find
  once enemies bunch up, and Curse, whose worth depends on who it lands on. Only a tiebreak: it prefers the version
  of a tile with the effect over an identical plain one, never over a tile doing a point more damage.

They all share the same modifiers. A tile in hand is worth 2/3 of one loaded, so loading it adds only a little. A
move that acts on a target is worth 1/3 with nobody it can act on. A loaded tile that would go off with a kill
earns nothing, since it's about to be spent. Several escapes count as the best one, plus half of each other.

What F1 doesn't do is score the position a loaded volley would leave behind. That's lookahead, which is F2's job.
These intrinsic values still hold if F2 returns: see Known limits.

### Size a value for the decision it's for

Every value on a tile is also given up when the tile is spent, so it has to be sized for the choice it's meant to
settle. The Shockwave value is only meant to pick the Shockwave version of a tile over an identical one, so it's
0.5, against 6 to 8 for a point of loaded damage. At 3 it held tiles back from kills.

Keeping something should only be worth more when it really is more available. A loaded Smoke Bomb can dodge this
turn and one in hand can't, but any attack spends it, so it isn't really held in reserve. Valued much higher
loaded, it beat a 4-damage Spear to the queue, so loading it now adds only a little.

### No lopsided costs

A cost applied to one option but not to the equivalent one tilts every choice. Sending a tile back to hand cost a
turn of reloading, but a fired tile has to be reloaded too, after its cooldown. Since attacking empties the queue
anyway, that cost only ever said "fire more", and F1 put the hook on cooldown for nothing. It's gone. So is the
cost of an attack that hits nothing, which only repeated what its cooldown already costs. Such an attack isn't
considered at all instead: sending the tile back is free and leaves the same board with the tile still ready, so it
is never the better choice. Without that, a weaker kit could score better: a tile on cooldown drops out of where the
hero wants to stand, so firing Shadow Kama at nothing removed the penalty for standing closer than it reaches.

### Tanks are decided one by one

An enemy that dies with its boss and isn't worth fighting while the boss lives is a tank: damage to it counts a
quarter as much, and its death nothing. That's decided with the player for each enemy, not by a rule like hidden HP:
so far the Shogun's last two statues and Ieyasu's Swapper. Moves that act on a tank, like trading places with it,
are still valued for what they do.

### Kills, and the clock

A kill is worth more than the same damage as a wound, and one volley doing the work of several saves turns. The
next wave arrives on a timer, so leaving HP in the room costs more as it nears.

### Weights are guesses, measured

Every weight is a first guess, kept in one place. Whenever one is tuned, what it trades against gets measured too,
and a value that breaks something is recorded: crowding at -10 stalls fights, and a kept Smoke Bomb above 16 does
too.

## The search

F2 to F4 play the hero's next turns out against the enemy AI (`solver/search.py`):

- **What a line scores:** each turn's events, as F1 counts them, plus the position it ends in, scored as F1 scores
  one, with the stack and the threat no answer removes. A turn whose enemy actions are all known counts in full, as
  the player asked, and one with a guessed enemy action (a boss, an enemy whose choice the board doesn't show, an
  unidentified tile) at 0.5, from there on.
- **Waves end a line** (v3.6): where the next wave arrives, the line stops and is scored by the board it lands on.
  Who comes isn't simulated, so playing on scored a board missing them, where a tile spent would be back before the
  line's end and look free: in `run16` F4 spent the Mirror on a kill that cleared the room, and the wave came at
  once. The game brings it when its countdown runs out, unless the room is too crowded for it, and at once when the
  room is cleared. This replaced counting turns after a wave at 0.85.
  An enemy whose AI isn't known is guessed to attack whenever what it holds would hit the hero, as such enemies
  did on 80% of those turns in the logs.
- **Ties:** of two lines that score the same, the one whose events come sooner wins (events counted 0.9 per turn
  later, for the tie only). Breaking ties on the position after this turn, as F1 does, kept tiles loaded and put
  kills off indefinitely, since known turns aren't discounted.
- **The win:** ending the fight at no HP cost beats anything only on the turn being chosen, as in F1. Counting it
  later in a line too made every line ending in a win tie, and the search kept putting the win off.
- **Speed:** every action this turn is searched, but deeper turns follow only the 4 best by a cheap score (the
  turn's events and the position without its stack), the full position score is only taken for the 2 best on the
  last turn, and a board reached by two orders is searched once. Boards are copied by `State.clone`, not deepcopy.
- **The solver server** (`solver/server.py`) keeps worker processes warm and runs every depth at once, one job per
  distinct action now (actions that leave the same board with the same events are searched once). The mod still
  runs `analyze.py` on each key press, which hands the request to the server, starting one if none runs and
  answering that press itself, F2 to F4 sharing 1 s on one core. The server restarts itself when solver code changes, and quits after 3 idle
  hours. Killing it by hand leaves its workers behind; let it quit, or stop them too.
- **Potions** are judged on the deepest search: each potion held gets its own search of the board after drinking
  it, in parallel, and any that cuts the HP lost along the best line is used, combat potions first on a tie, Freeze
  Time first in the fight before the Shogun's (`search.potion_choice`).
- **The budget:** F2 to F4 get 0.45 s from the start of an answer. A depth that runs over plays the choice of the
  deepest that didn't, and the report says so; F1 always finishes. On this laptop (a 14900HX, with slower efficiency
  cores and throttling) F4 finished in time on about half of paced presses measured in a loaded state, F3 nearly
  always, and whole key presses took 0.25 to 0.5 s.
- **The fight simulator** (`tools/simulate.py`) plays whole fights offline from every logged fight and wave start
  where all enemies are ported, with a chosen policy, and counts HP lost and the turns the hero was hit. Unlike a
  replay, it shows how a whole fight goes. `tools/check_ai.py` checks the AI's telegraphs against the logs,
  `tools/check_rollout.py` how far ahead the whole simulation holds (the moves really played, run 1 to 4 turns
  through the rules and the AI, against what the game logged), and `tools/time_search.py` times the search. With
  every enemy ported, the board 4 turns on was exact 83% of the time (89% where every enemy's choice was known
  throughout; 24% where a Shinobi's or Warden's hidden last tile mattered), and with a boss in, 10%.

## Adding a mechanic

1. **Read the game's code first** (`tools/il_show.py`), rather than guessing from what's on screen. Note the exact
   rule, including when it applies: whose hit counts for a skill, the order damage resolves in (skills, then a
   curse, then a shield), and what happens with nobody in range.
2. **Simulate it in `rules.py`** and write tests from the code's behavior, including edge cases.
3. **Check it against the logs:** every turn's prediction against what the game did next (`check_predictions.py`).
   The only misses expected are summons.
4. **Record it** in `rules.md`, and in `unvetted.md` until a real log shows it working. Mark each item as a rule
   (from the code), scoring (a judgment), or an assumption (like a value stored in the game's assets).

## Checking a change

- **The core boards.** Everyday checks run on a core of the logged boards, about a seventh of them, that
  `tools/condense.py` picks by meaning: every board a position test names, every board whose choice changed between
  two versions' full replays, enough boards to cover each hero, tile, effect, skill, potion, enemy, elite, status,
  hazard and trap, and the closest calls, at most 4 a fight beyond the first two kinds. It's kept in
  `research/boards/core.json`, with every board's margin in `margins.json`. Raw logs are never trimmed, and `--full`
  runs every board. When a log is added to `solver/logged_boards.py`, run `condense.py --add`, which adds its boards
  against what the core already covers and takes in boards newly changed between versions, leaving the rest alone so
  replays stay comparable. `--rebuild` starts over, for when the criteria change. Checked against past versions
  before the changed boards were added, the core held 103 of their 265 changes (39%) in a seventh of the boards, but
  missed two small fixes entirely and caught only 1 of v2.15's 24, which is why boards that changed are kept.
- **Replay real logs.** `tools/replay.py` runs the top choice on every core board, in parallel, in about 13 s, and
  saves it to `research/replays/<version>.core.json`; `--full` runs every board, in about 75 s, into
  `<version>.json`, and `--tag` replays a tagged version from git. `tools/compare.py` then counts what changes,
  kills, HP lost and damage dealt, on the core unless `--full`, and `--show` lists each changed choice to look at.
  `tools/choices.py` shows one board's top choices with every term, and `tools/potions.py` which potion F1 would use
  on every board holding one.
- **Use the full set for releases:** before pushing, run `replay.py --full`, compare with `--full`, then
  `condense.py --add` so any newly changed boards join the core, and `SHOGUN_FULL=1` for the principle test.
- **Run the principle test,** `test_principles.py`: rule 1 on the core boards, in about 5 s.
- **Run the stall check.** Hunt a still enemy from many starts, to catch fights that would drag on.
- **Look at the turns that prompted it,** and make sure each one now picks what it should, for the right reason.
- **Keep real positions as tests** (`test_positions.py`), so later changes can't quietly undo them, but only for a
  board that shows something no test covers yet: a new mechanic, a mistake that got fixed, or a judgment the player
  made. Tests aren't added for every change, so the suite stays fast. Each one is pinned in the core.
- **Know what replays can't show.** A replay changes one choice from a board the old version reached, so it can't
  show how a whole fight would go. Only real fights vet a change.

## Versions and vetting

- Any change that can alter a choice bumps `VERSION`, gets committed, and is tagged `evaluator-<version>`. The logs
  record which version made each decision.
- Each version gets an entry in [`CHANGELOG.md`](../CHANGELOG.md), the one place listing what every version changed,
  marked as rule or scoring.
- `unvetted.md` lists changes to rules and scoring that real play hasn't shown working. An item leaves when a log
  shows it working. A past win stands: later versions aren't held to winning it again.

## Working with the player

The player plays the fights and reports what looked wrong, and most changes start there: a hit that should have
been dodged, a tile wasted, a move that seems inefficient. Each report gets checked against the log before anything
changes, and sometimes the log shows a different cause. The damage the potion avoided in fight 8 came from a
Strider's move being mispredicted, not from the shove spent earlier. The game overwrites its log at launch, so each
log gets saved into `logs/` first.

## Known limits

- **One turn ahead can't anticipate.** An attack only counts once it's telegraphed. A better player loads a Smoke
  Bomb ahead of an Archer's shot, and F1 can't see the need until it's too late. That needs knowing what enemies do,
  and lookahead.
- **Consumables** are used by fixed rules rather than valued in the score, one potion per key press: see `rules.md`.
- **Which enemy to kill first** is simply lowest HP, then closest.
- **Why a deeper line sums its turns at all.** With perfect prediction, summing each turn's events would add
  nothing over the final position: an enemy killed sooner would simply show as HP not lost later. It's done, with
  each turn discounted, because prediction gets worse with each turn. Past the first, enemies are treated as
  standing still, and spawns and summons can't be predicted at all, which keeps early kills worth more even with a
  perfect model of the enemies. So the right discount depends on how good the prediction is. A deeper search built
  on the enemies' real behavior would want a gentler one.
- **If F2 returns,** the position terms carry over as they are. A line adds up what each of its turns did, and
  only adds position terms at its end, so those only ever estimate what's beyond the horizon. Poison that ticks
  within an F4 line counts as damage dealt, and only what's left at the end is estimated. A value added for an
  action rather than read from the final position would count even when the line already plays out what it stands
  for, so values on moves and tiles stay on the position.

## Tied values

A value defined in terms of another is computed from it in code, never copied, so changing one changes both, as the
player asked: the reload from what its loaded Crossbow holds, the Phase's and Throw's escape values from the Swap's
and the shove's, each Back tile's from its forward one, the Edamame threshold from what it heals, the reach
lookahead from its falloff, and Reactive Shield's unshielded worth from the shield's. `test_tied_values_stay_tied`
checks the table ones.
