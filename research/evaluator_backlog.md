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

- **Attacks that displace others:** DragonPunch, KiPush, TwinTessen, Hookblade, SmokeBomb, Mirror,
  OriginOfSymmetry, Tanegashima. Each needs its rules read first.
- **Summons:** a Summon's arrival isn't predicted, and summons die with their boss. Both prediction
  misses in run 2 are Summons.
- **The Twins (to fix as a one-off):** this appears to always be boss 3, and it's a mechanic a player
  would understand. Damage to the Side twin also comes off the Main twin, and the Side twin dies with
  it. F1 sees a 35 HP boss and a separate 100 HP one, so it goes for the Main twin only because it's
  the lower HP, and hits on the Side twin count for no kill.
- **Swap Toss (to model):** swaps the contents of the cells directly ahead and behind, moving whoever
  is there. A standard movement ability, like the dashes. It moved the hero on turn 16 of that fight.
- **Grappling Hook (to model):** deals 1 and pulls the first target to the cell directly ahead of the
  user, if it survives and can be moved. The simulator counts the 1 but not the pull, so it badly
  understates a Grappler's Hook and Katana stack, like a dash before it was fixed: it sees 1 damage
  where the Katana should then land too, and stepping back doesn't escape it. No Grappler has fired
  one yet, because F1 killed each one first.
- **Heavy enemies:** the Statue boss has a Heavy trait, which may mean it can't be moved. Swap and the
  moving attacks don't check for that yet. If so, the game should refuse the swap and the mod logs it.
- **Other new attacks seen:** Smoke Bomb and Summon still trigger the warning.
- **Perfect Strike:** a tile with this effect recharges fully when its hit deals exactly the target's
  remaining HP, counting a curse's doubling. Not modeled, and cooldowns aren't valued anyway, so F1
  won't aim for it. A kill that triggers it just gets read correctly on the next turn.
- **Shield refinements:** a shield is worth a flat 1 HP (v0.7). It should be worth less near the end of
  a fight, since it usually expires then, and hitting an enemy's shield still scores nothing.
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

## Holding tiles in reserve

From play: Dash plus a free Swirl could work as a gap closer, one of the few ways to reach a far Archer
threatening a kill when Arrow is down. Today F1 spends these at the first opportunity. A stack is valued
for what it can do now or within a few moves, so nothing rewards saving a tile for a threat that
hasn't appeared yet. This likely needs a lot of tuning, which is what simulated fights would be for.

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
