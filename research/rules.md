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
  enemies. A removed tile goes back to the hand still charged, and playing it again uses a turn. So with the queue
  full, a tile can be sent back to make room and another loaded, for the one turn the loading takes.
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

The fight in `logs/run3_part2` showed:

- **Curse pays off within one stack.** On turn 7, Swirl with Curse hit for 3, then Shadow Dash's 1
  was doubled to 2 for the kill. Curse status was predicted correctly on all 28 turns.
- **Free Play works in one key press.** On turns 21 and 29, the mod played the tile from hand, edited
  the queue and attacked together.

The twins boss, later in the same log, showed:

- **A curse doubles exactly one tile.** On turn 8, Swirl hit for 3 and cursed, Arrow's 4 hit for 8, then
  Swirl's 2 hit for 2 with HP to spare.

The Shielder fight, later in the same log, showed:

- **Back Charge** runs away from the facing direction without turning, stops at the last free cell, and
  hits whatever is next. Its uses on turns 7, 27 and 32 were all predicted correctly. Running to the wall
  with nothing behind, and doing nothing when backed against one, still come from the code alone.
- **A shield blocks a whole hit and is used up,** for the hero (turn 33) and for enemies (turns 15, 25
  and 27). The next tile in a stack then hits normally.

- **Shield and Shield Allied** were predicted correctly throughout, once modeled. Shield Allied goes to
  the first shieldless ally ahead, passing the hero and already shielded allies.

The 15-wave fight, also in that log, showed:

- **Grappling Hook pulls even through a shield.** On turn 12, a shield blocked its 1 damage, the hero
  was still pulled next to the Grappler, and the Katana then hit for 2.

The 9-cell fight with mass ice, also in that log, showed:

- **The Curse attack goes through a shield.** On turn 25 it cursed a shielded Yari Master. Shadow Dash then
  broke the shield without using up the curse, and Swirl's 2 was doubled to 4 for the kill.
- **Two Free Play tiles work in one key press** (turns 25, 34 and 40).
- **Perfect Strike recharges its tile on an exact kill** (turns 34 and 53), counting a curse's doubling.
  Simulated as of v0.11.
- **Frozen enemies telegraph Wait and don't act.** Ice counted 4, 3, 2, 1 from a potion that says 3 turns.
- **A flip potion changes facing at once,** without using a turn.

Later bosses in that log, with the rules read from the game's code (simulated as of v0.11):

- **Corrupted Barrage** (final boss) hits the cells beside its user at once, then spreads one cell further
  each way per turn, from where it was fired, even if the user moves. On turn 37 it fired from cell 3, and on
  turn 39 it hit the hero on cell 0 for 3. The cells next in line show warnings in the game, and the mod
  logs them as `hazards`. It heals a boss standing on a struck cell, and a shield blocks it.
- **A boss dying kills everyone else in the room.** The final boss's first phase then turns into the next.
- **The Twins:** damage to the Side twin also comes off the Main twin, and the Main twin dying kills the
  Side twin. Damage to the Main twin doesn't reach the Side twin, whose own HP never matters.
- **Smoke Bomb** trades places with the first target in range, then hits it. It does nothing to an
  immovable target. Kowa's "teleport" is this tile.
- **Swap Toss** trades the contents of the cells on either side of its user. Both cells must exist, and
  neither occupant can be immovable.
- **Mirror** moves its user across the room's middle (the left of the two on an even room), trading places
  with anyone there. Both turn around.
- **Origin of Symmetry** moves its user to the centre, trading places with anyone there. Nobody turns.
- **Dragon Punch** hits, then pushes the target as far as it goes. If someone stops it, they each take 1.

Run 4, the first after beating the game, added new enemies (simulated as of v0.12):

- **Volley** (Sniper, Baru) locks onto the hero's cell as the turn it fires begins, which the game shows as
  a warning on that cell. It then lands there, on whoever is on the cell, passing over anyone in between.
  Its logged range looks like a shot along the row, but that isn't how it works. Stepping off dodges it,
  in either direction, as on turns 5 and 41 of fight 4. On turn 15 of fight 7, it hit the hero behind an
  Ashigaru and left the Ashigaru alone.

The run that confirmed v1 showed poison and the bomb, with more rules read from the code (simulated as of
v1.1, and listed in `unvetted.md` where a log doesn't confirm them):

- **Poison** sets 3 turns left, and each turn's end deals 1, starting on the turn it's applied. On turn 10
  of the final boss, it took 1 that turn, then had 2 left, then 1. A shield blocks a tick and is used up
  (turn 24). By the code, poisoning again resets the turns rather than adding them, and a tick can kill.
- **Bomb** goes on the cell in front of its user, if that cell exists. It waits, then blasts that cell and
  both neighbours: thrown on turn 21 of fight 28, it hit the hero on cell 6 for 3 on turn 23.
- **Copycat Mirror** does nothing itself, and the next turn its user's queue holds a copy of a hero tile.
  Kabukai copied Shuriken, Spear and Dragon Punch in fight 29.
- **Barricade** puts a 5 HP inanimate enemy on the cell in front of its user, if that cell is free.
- **Two Way Move** lets Swap work backward. By the code, a swap never turns the hero.

Shockwave, read from the code (simulated as of v1.3):

- After a tile's hit, it runs both ways from the target through touching agents, stopping at a gap, a wall or
  the hero, who isn't hit. Everyone it reaches is hit. So is the target, but only if it reached someone.
- The damage is stored in the game's assets. `logs/run7` shows 1, chaining through two touching enemies on turn
  41, and going off even when the tile killed its target.

Elites, read from the code (simulated as of v1.24):

- **Double Strike:** the elite's attacks carry the Double Strike effect, and any attack with it plays twice in a row,
  targeting afresh: the Archer on turn 10 of fight 7 in `logs/run8` hit for 2 twice.
- **Reactive Shield:** after a hit that hurts it while it has no shield, and that it survives, it gains one. Any hit
  counts, collisions too.
- **Heavy:** can't be pushed or pulled. **Quick:** only changes the enemy's AI, how soon it chooses to attack.

Potions, read from the code (simulated as of v1.22):

- **Using one** is free, doesn't end the turn, and is only allowed between turns (`Potion.CanBeUsed`).
- **Edamame** heals 3. **Shield** shields the hero. **Freeze Time** (MassIce) freezes every enemy that can be, as
  Ice does. **Rain of Mirrors** turns every movable enemy around and reverses its telegraphed move or flip. **Mass
  Poison** and **Mass Curse** poison and curse every enemy. **Cool Up** recharges every tile and the special move.
  **D6** gives each enemy that isn't frozen a different random action, so it isn't simulated.
- **When F1 uses one**, by the player's rules, one per key press: Edamame once the hero is missing at least 3 HP.
  Cool Up, Shield, Freeze Time or Rain of Mirrors when the best line with it loses less HP this turn, in that order
  of preference. Under pressure (best score below 11, the worst 30% of logged boards), Mass Poison, Mass Curse or Cool Up when the
  best line with it kills more, and D6 against damage nothing else avoids.

Freezing, read from the code (simulated as of v1.21):

- **Ice** from a tile sets 4 turns of ice (`GameParams.iceEffectTurnsDuration`), resetting rather than adding, on an
  enemy that isn't Unfreezable. It cancels the action the enemy telegraphed for this turn, and its queue stays. An
  enemy with any ice chooses to do nothing, and ice counts down at each turn's end, so it loses this turn and the
  next three. A frozen hero can't act either, but that isn't simulated.

Dynamic Boost and stacked traps (v1.20):

- **Dynamic Boost** adds its level to the hero's own hits after an attack that moved or turned it this turn: Charge,
  Dash, Shadow Dash, Smoke Bomb, Sharp Turn, and a few others. By the code, the game raises that event after the
  move attack's own hit, so only later hits are boosted, and it switches off at the end of the turn. A Flip or a
  step doesn't count, nor does the shove. Confirmed by six hits in `logs/run7_part3`.
- **Two traps on one cell both go off.** On the last turn of the Shogun fight in `logs/run7_part3`, a second trap
  placed on the first and the hook pulling the Shogun onto them took it from 10 to 0, 5 each.

Ieyasu, read from the code (simulated as of v1.18):

- **Blade of Patience** strikes the cell directly ahead, and hits 1 harder for each turn it waits in the queue,
  starting the turn after it lands: 0 when it shows, up to 9 by turn 45 of fight 5 in `logs/run7_part2`. The log
  shows its current damage. Ieyasu fires it after a Dash, so he runs up to the hero and strikes.
- **Boss-Swap**, his Swapper's, trades places with the boss wherever each is, and neither turns. It keeps putting
  Ieyasu in front of the Swapper or behind it. The Swapper has 30 HP, which the game doesn't show. As of v1.19
  it's a tank, like the Shogun's last statues: it dies with Ieyasu, so F1 focuses him.

Traps and Combo Curse, read from the code (v1.16):

- **Trap** puts a trap on the cell ahead, if the cell exists, whoever is standing there. Only an enemy moving onto
  it sets it off, once, for the tile's damage and effect, with no attacker. So the hero can stand on its own traps.
  The mod logs traps on the ground as of plugin 0.11.0.
- **Inferred, not stated in the code:** the trap is thrown to its cell and only armed when it lands, and the game
  sets it off when an enemy *enters* it. So one placed under an enemy most likely waits for an enemy to move onto
  it, and an enemy dashing through its cell most likely sets it off. The second isn't simulated.
- **Confirmed in play** (`logs/run7_part2`): traps at the cell ahead, set off once by an enemy walking or pulled
  onto them, a trap placed and a hook pulling onto it in the same volley, and the hero standing on its own. An
  enemy arriving on a trap's cell sets it off too, as one did at a new act in the Sato fight.
- **Combo Curse** curses a random enemy for every kill after the first in a turn, by anyone, except inanimate
  ones. The kill streak resets at the start of each turn. The target is random, so it isn't simulated.

The Strider, read from the code (simulated as of v1.11):

- **Dash:** its move runs it to the last free cell that way, rather than one cell. Whoever first blocks it moves
  first if they're going the same way, as with any enemy's move. Fight 8 of `logs/run7` had 4 Strider moves
  mispredicted on v1.10, and all are exact now.
- **Fumiko**, the boss, moves the same way (simulated as of v1.15). Her one move in fight 10 of `logs/run7` was
  mispredicted on v1.14, and is exact now.
- **A curse on the hero** doubles the next hit it takes, then goes, as on an enemy. Fumiko cursed the hero on turn
  18 of that fight and died on turn 20, before anything hit it.

The Warden, read from the code (simulated as of v1.10):

- **Explosive:** a dying Warden hits its own cell and both cells beside it for 2, as its own hit, so the hero
  takes it when adjacent and a shield blocks it. Each Warden it kills explodes in turn. By the code, one that
  dies before its first decision doesn't, but every Warden on the board when the hero acts has made one: one that
  arrived with wave 2 on turn 6 of fight 7 in `logs/run7` exploded on turn 7.

Sharp Turn and Sniper, read from the code (simulated as of v1.9):

- **Sharp Turn** is `TurnAround` in the code, a Free Play tile. Its user turns around first, then strikes what's in
  range in the new direction. Tiles fired after it in the same attack fire the new way too.
- **Sniper** adds its level to the hero's own hits on a target 4 or more cells away, measured as the hit lands, and
  before a curse doubles it. Shockwave and collision hits don't count, as they aren't the hero's.
- **Two Way Move with the shove** lets it go backward, pushing the target that way. It needs a cell behind the
  target either way, and the hero keeps facing the same way.

Lightning, read from the code (simulated as of v1.6):

- It strikes the farthest agent in range ahead. A Thorns enemy is passed over for the next farthest, and with only
  Thorns enemies in range it hits nothing. The game refuses to let enemies use it.

The Ronin, read from the code (simulated as of v1.2):

- **Shove** is the Ronin's special move, triggered like Swap by moving into an occupied cell. The hero stays
  put, and the target goes as far as it can, as with Dragon Punch. If someone stops it, they each take 1.
- It needs a movable target and a cell behind that target, which someone may be standing on. So a target
  against the wall can't be shoved.
- The other heroes' special moves (Phase, Swap Toss, Throw) aren't simulated. F1 won't use them, and the
  report warns.

## Not confirmed yet

See `unvetted.md` for everything since v1. Older items:

- **A Volley hitting an enemy on the locked cell** comes from the code alone, since it has only hit the hero
  in the logs. So does a shield blocking it.
- **The Corrupted Barrage warnings** are read from the game's task object. The rule above comes from the
  code and two logged hits, and no log has the new `hazards` field yet.
- **Mirror on an even room's last cell** would land off the board. The simulator treats that as doing nothing.
- **Unfriendly Fire** is assumed to add its level to enemy-on-enemy hits, except collisions.

- **Damaging Move** comes from the code alone. A swap makes a normal hit on the enemy passed through, for
  damage equal to the skill's level. A shield blocks it, a curse doubles it, and it can kill.
- **Quick Recovery** lowers Swap's cooldown by 1. It should show up in the logged cooldown.
- Heavy enemies are assumed to be immovable. Swap and hook check a movable flag in the code, but nothing
  shown links that flag to the Heavy trait.
- A curse tile re-applying its curse after a doubled hit comes from the code's order of events.
- That the Curse attack does nothing to a target already cursed, and goes on cooldown on a miss, comes
  from the code alone.
- Whether an enemy can refuse a swap isn't modeled. The game would refuse the move, and the mod would
  log that.
- The saved fight log never has Swirl hitting two agents at once. An earlier log did show it, but
  that one wasn't kept, so the prediction check doesn't currently cover it.
