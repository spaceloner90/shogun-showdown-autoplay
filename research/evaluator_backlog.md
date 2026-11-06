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
- **Status effects:** poison, ice and curse, as tile effects or on agents. Set aside for now as too
  much to scope.
- **Skills:** 36 exist, by the game's code. See the survey below.

## Skill survey

Grouped by the names of their code hooks, not by reading each one, so treat these as rough:

| Group | Count | Skills | Likely work |
|---|---|---|---|
| Change attack damage | 9 | BackStabber, CentralDominion, ChikaraCrush, CloseCombat, DynamicBoost, IronSkin, Monomancer, Sniper, UnfriendlyFire | Small each, and they change decisions |
| Change the special move | 4 | CursingMove, DamagingMove, MamushiMove, TwoWayMove | TwoWayMove and DamagingMove look simple; the others need statuses |
| Trigger on combo kills | 8 | ComboBoon, ComboCoin, ComboCurse, ComboDeal, ComboRecharge, ChillingCombo, KobushiCombo, TripleComboHeal | Need "combo" understood first |
| Mostly passive | 15 | BigPockets, ChillingBlood, FenghuangFeather, Fortress, Healthy, Karma, Mindfulness, OddCurse, OverflowGuard, QuickRecovery, ReactiveShield, RogueRetail, SeiryuScale, ShieldRetention, TwoFacedDancer | Many may not affect combat choices at all |

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
