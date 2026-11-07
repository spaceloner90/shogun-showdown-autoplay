# Evaluator backlog

Open ideas, with F2+ frozen: these all have to work at depth 1 using only what a player can see.
Enemy AI code is for offline simulation and tuning only.

## Done in v0.3

- Kills are valued over wounds, and one volley doing the work of several is worth more.
- A stack counts for what it could do after a few moves or a flip, so Arrow is no longer fired eagerly.
- Closing in matters less with nothing to threaten enemies with.
- Sending a tile back to hand has a cost. Removed in v1.8: attacking empties the queue anyway, so it only made
  firing a tile look better than keeping it, even when firing it changed nothing.
- "Can I respond?" is graded: an answer counts for the damage it removes, even when it can't remove it all.
- Threats are played out, so first-target attacks can be blocked and a dash brings its next attack into range.
- Charge, BackCharge, Dash, ShadowDash and BackShadowDash move their user. First-target attacks stop.
- Free Play tiles are only played as part of an attack (v0.5), and count toward a stack from the hand.
- The report warns about any attack, effect, skill or status the solver doesn't model.

`solver/test_positions.py` keeps these real positions from going backwards.

## Not modeled yet

- **Attacks that displace others:** KiPush, TwinTessen, Hookblade, Tanegashima. Each needs its rules
  read first, as they come up.
- **Consumables (first version in v1.22).** F1 uses potions by the player's rules, ranking every move again with
  each held potion applied, since a potion can make a move good that F1 ranked low without it. Still open: whether
  the rules use them too much or too little, and Cool Up and D6 beyond their narrow rules. Scenarios saved for it:
  - **Rain of Mirrors ("Flip all enemies"), `logs/run7` fight 8, turn 28.** The hero on cell 6 is between two
    Striders on 5 and 7, each facing it with a Katana loaded, so every line takes at least 2. The player used the
    potion: both turned away, the right one's Katana killed the TwinTachi on 8 instead, and Spear with Sharp Turn
    then took no damage. The log has the board both before (seq 2126) and after (seq 2127) the potion. v1.11 would
    likely have avoided this a turn earlier, as it now sees the left Strider dash in next to the hero.
- **Key presses are slow because Python starts each time.** A press takes about 0.5 s in game, of which the search
  is about 0.02 s: the rest is starting a new Python process. A solver process that stays running, reloading when its
  code changes, would cut most of it. That's a new mechanism, to raise with the player before building.
- **Sato's acts (ignored on purpose for F1).** Sato's Maku ends the act and sets up a new battlefield: the hero
  is moved and new enemies arrive (`logs/run7_part2`, fight 3, turns 9, 16, 24 and 30). F1 only looks at the turn
  in front of it, so it doesn't matter there. A deeper search would have to stop at an act change, or know the
  layouts.
- **Sharp Turn used just to face a better way (left on purpose).** F1 sometimes adds a free Sharp Turn to the end
  of a volley only to face better (`logs/run7_part2`, fight 2, turns 3 and 20), when keeping it to aim a later
  attack is usually worth more. Scoring facing as free while one is ready was considered and dropped: facing
  matters beyond attacks, for a shove without Two Way Move for one, so turning early is sometimes right, and a rule
  shaped around how one Free Play tile gets used wouldn't carry over to anything else.
- **What a point of damage is worth.** Every point counts 10, but taking an enemy from 2 HP to 1 is worth little
  when almost nothing that would kill it later does only 1. Damage should be worth what it saves later: the hits
  or turns it takes off the kill, given the kit. This came up comparing a 2-damage shove against loading a Trap
  (`logs/run7_part2`, fight 1, turns 5 and 17). It needs a much more involved assessment, so it waits.
- **What a planted trap is worth depends on the fight.** 0.4 of its damage looks too conservative from play. It
  should be worth more early in a fight, and with more spawns or movement to come, since more enemies will cross
  its cell, and less near the end.
- **The Copycat Mirror (ignored on purpose for now).** By the code, it copies a pseudorandom tile from the hero's
  hand, avoiding the last one it copied, wherever the hero stands, so it can't be dodged, and loaded tiles can't
  be copied. As of v1.17 no threat is assumed for the copy until it shows, since it could be anything: before
  that it counted as a 2-damage, 1-cell attack, which kept F1 clear of the copier for no reason. Once it shows,
  it's dodged like any attack. In `logs/run7_part2` the copy was a Smoke Bomb from the end of the row, which
  nothing could avoid by then. Keeping strong tiles loaded while a mirror is queued would deny them, but the
  player's call is that reacting to what it copies is fine for now.
- **Combo skills:** Triple Combo Heal, Combo Curse, Combo Coin and others. The player has the first three, all
  marked known so they raise no warning, and none simulated. "Combo" is now understood from the code: every
  kill after the first in a turn, by anyone, except inanimate enemies, with the streak reset at the start of each
  turn. None are valued yet. Combos may be worth something in general, and Combo Curse in particular: each combo
  kill curses a random enemy, which is a fraction of a doubled hit later, worth estimating even though the target
  can't be predicted. With F2+, it may pay to line up kills that are coming anyway into the same turn, to combo
  them.
- **Other corruption patterns:** the game can also send corruption left to right, right to left, or even
  and odd cells in turn. The mod logs all of them as `hazards`, and only the attack that starts them
  needs adding, but none has been seen yet.
- **Heavy enemies:** as of v0.9, the solver assumes the Heavy trait means an enemy can't be swapped or
  pulled. The code shows swap and hook need a movable target, but the link to Heavy is an inference.
- **Summon (ignoring on purpose):** where a summon appears is random, so a player can't react to it
  either. It will keep causing a prediction miss each time, which is expected.
- **Perfect Strike:** simulated as of v0.11, but cooldowns aren't valued, so F1 won't aim for it.
- **Shield refinements:** a shield is worth a flat 1 HP (v0.7). It should be worth less near the end of
  a fight, since it usually expires then, and hitting an enemy's shield still scores nothing.
- **Status effects:** ice, as a tile effect or on the hero. Being cursed has no direct cost in how the
  hero's position is scored yet. Poison is simulated as of v1.1, and what it's worth is a first guess:
  see `unvetted.md`.
- **Skills:** 36 exist, by the game's code. See the survey below.

## Skill survey

Grouped by the names of their code hooks, not by reading each one, so treat these as rough:

| Group | Count | Skills | Likely work |
|---|---|---|---|
| Change attack damage | 9 | BackStabber, CentralDominion, ChikaraCrush, CloseCombat, DynamicBoost, IronSkin, Monomancer, Sniper, UnfriendlyFire | Small each, and they change decisions |
| Change the special move | 4 | CursingMove, DamagingMove, MamushiMove, TwoWayMove | TwoWayMove and DamagingMove look simple; the others need statuses |
| Trigger on combo kills | 8 | ComboBoon, ComboCoin, ComboCurse, ComboDeal, ComboRecharge, ChillingCombo, KobushiCombo, TripleComboHeal | Need "combo" understood first |
| Mostly passive | 15 | BigPockets, ChillingBlood, FenghuangFeather, Fortress, Healthy, Karma, Mindfulness, OddCurse, OverflowGuard, QuickRecovery, ReactiveShield, RogueRetail, SeiryuScale, ShieldRetention, TwoFacedDancer | Many may not affect combat choices at all |

## Prioritizing dangerous enemies

From play: Archers, and to a lesser extent Chargers, need killing at range, or they deal damage that
can't be avoided. Across runs 2 and 3, played on v0.2 to v0.6:

| Enemy | Appeared | HP lost to it | Hits unavoidable by that turn |
|---|---|---|---|
| Charger | 27 | 9 | 8 of 9 |
| Yari Master | 27 | 7 | 3 of 4 |
| Archer | 11 | 6 | 3 of 3 |
| Everything else, including both bosses | 61 | 0 | - |

Today's target choice is simply the lowest HP, then the closest. An enemy's danger only registers once
its attack is queued, which is often too late to do anything. Options, all from what a player knows:

- Value killing an enemy more when its attack can't be stepped away from.
- Learn what each enemy type plays from past logs, so an Archer counts as a threat before it loads.
- Weigh the turn left before it can fire, so Arrow goes on the enemy that's about to be a problem.

## Enemy shields

As of v0.9, Shield and Shield Allied are modeled, and an enemy's shield counts as extra HP equal to the
weakest tile available. Still open: counting a shield queued on a Shielder as a fraction of that, so
killing it before it fires is worth more. That belongs with enemy priority.

## Holding tiles in reserve

From play: Dash plus a free Swirl could work as a gap closer, one of the few ways to reach a far Archer
threatening a kill when Arrow is down. Today F1 spends these at the first opportunity. A stack is valued
for what it can do now or within a few moves, so nothing rewards saving a tile for a threat that
hasn't appeared yet. This likely needs a lot of tuning, which is what simulated fights would be for.

## Firing a free Swirl alone (decision postponed)

From play: once the free Swirl reached 0 cooldown, F1 looked too eager to spend a turn on its 2 damage,
three turns in a row at one point (fight 13 of run 3, turns 41 to 43). Unresolved, and left as it was in v0.11.

Measured with enemies standing still, on the final deck and the positions of `logs/run3_part2`:

- From beside a single enemy, F1 already matches the fastest kill an exhaustive search finds: 2, 6 and 10
  turns for 12, 25 and 40 HP. The 40 HP kill includes lone tiles, so firing one isn't wrong by itself.
- Of 27 positions where F1 fires a free tile alone, it clears as fast as possible in 13, is 1 or 2 turns
  slower in 8, and the search ran out of time on 6, including turns 41 to 43 above. This doesn't yet
  show whether the Swirl lost that time or F1's later moves did.
- Raising the stack values shortens some hunts: 40 HP from any start averaged 13.9 turns, against 12.5 at
  a share of 0.7. But it also puts off kills: of the choices that killed at 0.6, 9 no longer do at 0.7,
  21 at 0.8 and 30 at 0.9.

Next idea to test: raise what a stack's damage is worth while holding what its kills are worth.

## The Ronin without Swap

From the first Ronin run (`logs/run6`), which took damage in a chapter that usually costs none. The player's read:
firing Smoke Bomb for the damage while ignoring position is very bad here, and without Swap everything is less
forgiving. The player's further read: "close in and face enemies" suited melee with Swap, and where to stand should
depend on the kit. A hero with reach and a hook wants to stay back and only grab the enemies it wants to deal
with, and being surrounded should cost more. v1.4 does a first version of both, and values a kept Smoke Bomb. Still open:

- **The hook drags enemies in.** Fight 2, turn 30: it pulled a TwinTachi adjacent for 1 damage, winning by 5 points,
  and the hero took 2 from a Swirl two turns later. v1.4's crowding penalty only stops this at -6, which is close to
  stalling fights, so it still happens at -3. Choosing who to grab belongs with enemy priority.
- **Backing into walls.** Standing off could get the hero pinned, as on fight 2, turn 10. Nothing scores being
  near a wall yet.
- **Kits other than these.** As of v1.5 every hero uses the same rules, as the player asked: general rules going
  forward, developed further wherever going back shows them worse. Preferred distance has been looked at on the
  Ronin's deck and the Wanderer's winning-run decks, where it comes out at 1 on 894 of 926 boards.
- **A loaded Smoke Bomb discourages setting up kills.** A loaded Smoke Bomb earns nothing kept when the loaded
  tiles can kill from here, so loading a tile that makes a kill possible behind it costs its 12. That's fair, since
  firing them spends it, but depth 1 may make too much of it. As of v1.6 a bomb in hand isn't affected.
- **Loading the Smoke Bomb ahead of an Archer (out of scope for now).** Fight 3 of `logs/run7` lost 4 HP to two
  Archer shots (turns 17 and 21). A better player would have loaded the bomb ahead of time to step out of them.
  F1 only sees an attack once it's queued, so valuing the bomb loaded in that case needs knowing what each enemy
  will do, and lookahead. Belongs with enemy priority and F2.
- **What a move is worth beyond its damage.** The convention for F1: intrinsic values per move or effect (escape,
  setup, a Shockwave tile's loading), not scoring the board a volley leaves, which is lookahead and belongs to F2.
  Position terms still hold at a deeper horizon: they're only added at the end of a line, and the turns before it
  are played out, so they only estimate what's beyond it. Values on moves and tiles stay position terms for that
  reason, rather than being added for the action.
- **The per-turn discount stands in for poor prediction (not acting on it now).** Summing a line's turns, each
  discounted, only makes sense because predictions get worse with each turn: enemies are treated as standing still
  after the first, and spawns can't be predicted. A deeper search built on the enemies' real behavior should
  discount less, though spawns will always make early kills worth more. See `design.md`.
- **Escape values are guesses.** As of v1.7 every repositioning move is worth something kept, from how flexible it
  is, and they're first guesses to tune in play. Only Swap and the Smoke Bomb count as a way out when flanked.
- **The shove for collision damage.** Fight 2, turn 7 spent it for 2 damage, and it was down for 4 turns.
- **Facing.** Fight 2, turn 32: Spear killed one TwinTachi while the one behind the hero hit. The answer was to
  flip a turn earlier, which depth 1 only partly sees.
- **Weak starting decks.** A still enemy with 25 HP takes about 50 turns with the Ronin's starting tiles, against
  about 10 for the Wanderer's final deck, so fights last longer and each mistake costs more.

## Ideas not yet tried

- **Cooldowns aren't valued.** Which tile to load depends on damage and reach. Changing a cooldown
  changed no choices on run 2's positions.
- **Tile order may have shifted the wrong way.** On run 2's 55 positions with a choice of tile, v0.2
  picked Arrow 27 times and Swirl 28, while v0.3 picks Arrow 20 and Swirl 35. The player's read is that
  Arrow, then Swirl, then Katana gives the most opportunities, so this needs watching in real fights.
- **Body-blocking:** first-target attacks stop at the first agent, so standing behind an enemy blocks
  them. F1 can see this one move ahead, but won't set it up.
- **Wave pressure** may need revisiting, since holding a stack delays kills.

## The run that confirmed v1 (`logs/run5_full`)

This log holds two runs. Fights 1 to 7 are an earlier run on v0.11, the same fights as `logs/run4`. The
winning run starts from the camp at fight 8: fights 9 to 30, all on v0.12, with 926 moves by F1. Fight
numbers in these notes are the log's own.

## Baseline for comparing versions (`logs/run2_complete`)

Across the 310 positions of run 2, top choices only, not played fights:

| | v0.2 | v0.3 |
|---|---|---|
| Fires to wound | 26 | 7 |
| Fires to kill | 64 | 64 |
| Sends tiles back | 13 | 9 |
| Takes a hit | 11 | 10 |
