# First battle rules

How combat works in the first battle with the starting hero. These come from reading the game's
code and checking its logged behaviour.

Deliberately not covered: how enemies choose their actions, what future waves contain, and where
new enemies spawn. A player can't know those, so the solver doesn't use them.

## Setup

| Item | Value |
|---|---|
| Grid | 5 cells in a line |
| Hero | 10 HP, Wanderer |
| Queue | Holds up to 3 tiles |
| Waves | 4 |
| Enemies in the room | At most (cells + 1) / 2 = 3 |

## Abilities

Damage is a fixed value. Range offsets are relative to facing: positive is ahead, negative is behind.

| Ability | Damage | Cooldown | Range | Hits |
|---|---|---|---|---|
| Swirl | 2 | 3 | -1 and +1 | Everyone on both cells, friend or foe |
| Arrow | 2 | 5 | +1 to +10 | First agent ahead, at any distance |
| Katana (enemies) | 2 | none | +1 | The agent directly ahead |
| Swap (hero) | none | 4 | +1 | See below |

**Swap** happens when the hero moves in the facing direction into an occupied cell while Swap is
charged and the occupant can be moved. The two trade cells and both keep their facing, so an enemy
that was facing the hero now faces away. Swap counts as the hero's move for the turn.

## What the hero can do

Exactly one action per turn:

| Action | Rule |
|---|---|
| Wait | Always allowed |
| Move | The neighbouring cell must be empty, or Swap must apply |
| Flip | Turns to face the other way |
| Play tile | The tile must be charged and the queue must have room |
| Attack | The queue must have at least one tile, and fires all of it |

Queue details:
- Tiles fire front to back, which is the order they were played.
- **A tile that hits nothing still goes on cooldown.** Attacks aren't skipped when no target is in range.
- Targets are worked out when each attack fires, so a push or kill from an earlier tile changes
  what later tiles hit.
- The queue can be rearranged without using a turn. The solver doesn't use this yet.

## Order of a turn

1. The hero's action resolves completely.
2. Each enemy flips or moves as telegraphed, left to right.
3. Each living enemy telegraphing Attack fires its whole queue, left to right.
4. Each enemy telegraphing Play Tile adds a tile to its queue.
5. Status effects tick.
6. Wave timer: see below.
7. Enemies are sorted by cell, left to right, and each decides and telegraphs its next action.
8. Every tile and the Swap charge recover by one (see Cooldowns).

What this means in play:
- **Enemy attacks land where the hero ends up.** Stepping out of range, or swapping past an enemy
  with a one-direction attack, avoids the hit.
- **Killing an enemy cancels whatever it telegraphed.**
- **Enemies move before attacking, as separate steps.** An enemy telegraphs one action per turn, so
  it won't move and attack in the same turn.
- **A telegraph stays as shown** unless the enemy dies. In this battle nothing else interrupts it.
- **An enemy that plays a tile can't fire it in the same turn.**
- **A blocked move does nothing.** A move fails if the cell is occupied, unless the occupant is
  about to move away in the same direction.

## Damage

- Shield absorbs a whole hit and is then removed.
- Curse doubles the next hit and is then removed. Neither shield nor curse appears in this battle so far.
- Enemy attacks hit other enemies too. Swirl has hit and killed allies in the logs.

## Cooldowns

A tile's charge counts up to its cooldown, and it's playable when they're equal.

- Firing a tile sets its charge to 0, and it doesn't recover at the end of that turn.
- Each later turn adds 1. So a tile fired on turn T can be played again on turn T + cooldown + 1.
- Tiles recover whether or not you do anything. Swirl is ready every 4 turns and Arrow every 6.
- Swap works the same way, with a cooldown of 4 and no recovery on the turn it's used.

## Waves

At the end of each turn:
1. If exactly one enemy is alive, the countdown is capped at 6.
2. The countdown drops by 1.
3. On the last wave, clearing the room ends the battle.
4. Otherwise the next wave spawns if the room is clear, or if the countdown has reached 0 and the
   new wave wouldn't push the room over its enemy limit.

So clearing the room brings the next wave immediately, and `turnsUntilNext = 1` means the wave
arrives during the coming turn. Newly spawned enemies can't act until the next turn.

## Confirmed from play

The fight in `logs/first_f1_win` matched the simulator's predicted next state on all 29 turns it
could check, including 11 hero moves and 4 hero flips. A hero flip uses a turn, and this hero doesn't
have the free version the code allows (`TurnAroundIsFree`).

The fight in `logs/battle2_swap_queue` showed:

- **Queue edits are free.** Reordering or removing queued tiles doesn't use the turn or change the
  enemies. A removed tile goes back to the hand still charged, and playing it again uses a turn.
- **The queue fires in the order it's listed.** Only two fights have shown a stack firing.
- **Swap costs one turn.** Two simulated turns across it matched the log on all 10 values compared,
  including the charge restarting and the swapped enemy's attack missing. A complete swap in
  `logs/run2_complete` (turn 20 of battle 2) was then predicted exactly.
- **Charge moves its user.** It runs to the last free cell and hits whatever is next, allies included.

The second boss in `logs/run3_v03` showed:

- **Shadow Dash lands behind its target.** It reaches a target at any distance, passes it, and stops at
  the first free cell behind it, hitting everyone it passed. With no free cell behind, it does nothing
  and still goes on cooldown. A stack fires from wherever the dash lands.

Fight 7 of the same log showed:

- **Free Play tiles load without using the turn.** They can also be sent back for free, so the solver
  only ever plays one as part of an attack.

## Not confirmed yet

- Mod 0.8.0 plays Free Play tiles from hand in the same key press as the attack. That hasn't run yet.
- Whether an enemy can refuse a swap isn't modeled. The game would refuse the move, and the mod would
  log that.
- The saved fight log never has Swirl hitting two agents at once. An earlier log did show it, but
  that one wasn't kept, so the prediction check doesn't currently cover it.
