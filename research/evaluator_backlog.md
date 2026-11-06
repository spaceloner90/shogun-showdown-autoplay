# Evaluator backlog

Open ideas, with F2+ frozen: these all have to work at depth 1 using only what a player can see.
Enemy AI code is for offline simulation and tuning only.

## Done in v0.3

- Kills are valued over wounds, and one volley doing the work of several is worth more.
- A stack counts for what it could do after a few moves or a flip, so Arrow is no longer fired eagerly.
- Closing in matters less with nothing to threaten enemies with.
- Sending a tile back to hand has a cost.
- "Can I respond?" is graded: an answer counts for the damage it removes, even when it can't remove it all.
- Threats are played out, so first-target attacks can be blocked and a dash brings its next attack into range.
- Charge, BackCharge, Dash, ShadowDash and BackShadowDash move their user. First-target attacks stop.
- Free Play tiles are only played as part of an attack (v0.5), and count toward a stack from the hand.
- The report warns about any attack, effect, skill or status the solver doesn't model.

`solver/test_positions.py` keeps these real positions from going backwards.

## Not modeled yet

- **Attacks that displace others:** KiPush, TwinTessen, Hookblade, Tanegashima. Each needs its rules
  read first, as they come up.
- **Bomb (Hideyoshi's tile, seen in run 5):** placed on the cell in front of its user, if there is one, and
  it explodes at the end of a later turn, hitting that cell and both neighbours. Thrown on turn 21 of fight
  28, it hit the hero for 3 on turn 23. The simulator treats it as an instant melee hit, then forgets it.
  It would fit the `hazards` format, with empty groups for the turns it waits. The mod needs to log each
  `Bomb` object's cell and `nTurnsLeft`, since a placed bomb isn't otherwise in the log.
- **Copycat Mirror (Kabukai):** not read yet. Each cast causes a queue-length miss in the predictions.
- **Two Way Move (skill):** lets Swap work backwards as well, but `can_swap` only allows the facing
  direction, so F1 passes up those swaps. It warns, and it should be a small change.
- **Dragon Punch's value:** the shove is simulated, and F1 will load it when a preview shows a collision kill
  (run 5, fight 30, turns 5 to 8). But a shove earns nothing for the distance it creates, so at 1 damage it's
  rarely worth loading: top choice on 4 of 97 turns it could load, with 2 of those 4 later sent back to hand.
- **Consumables:** in-battle potions aren't used by F1, and the player expects them to add a lot.
- **Poison:** still not simulated. It worked well on the final boss without F1 knowing, and shows up as
  boss HP misses in the predictions.
- **Barricade (Baru's tile):** spawns a 5 HP inanimate Barricade on the cell in front of its user, if that
  cell is empty. Its location is predictable, unlike a Summon's, so it could be simulated. For now it only
  causes a warning and an enemy-count miss, and F1 reads the Barricade correctly once it's on the board.
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
- **Frozen enemies with a loaded attack:** the threat check doesn't know a frozen enemy can't fire, so
  it would count that attack anyway. It hasn't come up: the enemies frozen so far had nothing loaded.
- **Status effects:** poison and ice, as tile effects or on agents. Curse is modeled as of v0.6, but
  being cursed has no direct cost in how the hero's position is scored yet, and the enemy Curse
  attack still isn't modeled.
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

## Ideas not yet tried

- **Cooldowns aren't valued.** Which tile to load depends on damage and reach. Changing a cooldown
  changed no choices on run 2's positions.
- **Tile order may have shifted the wrong way.** On run 2's 55 positions with a choice of tile, v0.2
  picked Arrow 27 times and Swirl 28, while v0.3 picks Arrow 20 and Swirl 35. The player's read is that
  Arrow, then Swirl, then Katana gives the most opportunities, so this needs watching in real fights.
- **Body-blocking:** first-target attacks stop at the first agent, so standing behind an enemy blocks
  them. F1 can see this one move ahead, but won't set it up.
- **Wave pressure** may need revisiting, since holding a stack delays kills.

## Baseline for comparing versions (`logs/run2_complete`)

Across the 310 positions of run 2, top choices only, not played fights:

| | v0.2 | v0.3 |
|---|---|---|
| Fires to wound | 26 | 7 |
| Fires to kill | 64 | 64 |
| Sends tiles back | 13 | 9 |
| Takes a hit | 11 | 10 |
