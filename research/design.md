# Design

How the autoplay decides, and why it's built the way it is. The other documents cover the rest:
[`rules.md`](rules.md) has the game's rules as worked out from its code and from play,
[`unvetted.md`](unvetted.md) what real play hasn't confirmed yet, and
[`evaluator_backlog.md`](evaluator_backlog.md) what's still open.

## The goal

An AI that plays Shogun Showdown one turn at a time: each key press plays one turn, and the log says where the
decision came from. `evaluator-v1` won day 1 with the Wanderer. The aim now is to beat the full game, with other
heroes and kits, starting with the Ronin.

## Ground rules

- **Only what a player can see.** The live evaluator uses the board, the telegraphed enemy actions, the tiles and
  the skills. The enemy AI's code may be read and rebuilt for offline simulation and tuning, never to predict moves
  live.
- **One turn ahead.** F1 looks at each action available now and scores where it leads. Searching deeper (F2 and
  up) is paused. Everything a plan needs has to show up in how a position is scored.
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
   - **The stack:** what the loaded tiles would do if fired, from here or after a few moves or a flip, discounted
     for each action needed, with every firing order tried. A kill is worth far more than a wound, so a loaded
     volley that kills counts for a lot.
   - **Tiles:** charged ones, and damage loaded.
   - **What's kept:** charged moves that are worth more than their damage (escape and setup, below).
   - **Statuses:** poison still to come, curses on enemies, the hero's shield.
   - **Where the hero stands:** facing the right enemy, distance from where the kit wants to be, crowding, and
     being flanked or surrounded, which is much worse with no way out.
   - **Pressure:** enemy HP left in the room, more so as the next wave nears.
   - **Threats with no answer:** damage queued against the hero that nothing available could avoid.

## Principles

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

The hero prefers the farthest distance where the tiles it will have soon do the most damage, up to 3 cells, or 4
with Sniper's bonus. A melee kit comes out at 1, the Ronin's Spear at 2. Being closer than that costs a little, and
the cost stays small: larger penalties made fights stall.

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
cost of an attack that hits nothing, which only repeated what its cooldown already costs.

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

- **Replay real logs.** Run the top choice on every logged board before and after: the Wanderer's 926 winning-run
  boards, and every Ronin board since. Count what changes, kills, HP lost and damage dealt, and look at each changed
  choice that matters.
- **Run the stall check.** Hunt a still enemy from many starts, to catch fights that would drag on.
- **Look at the turns that prompted it,** and make sure each one now picks what it should, for the right reason.
- **Keep real positions as tests** (`test_positions.py`), so later changes can't quietly undo them.
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
