// Combat logger and turn-by-turn solver controls for the autoplay project.
//
// It records four kinds of line in BepInEx\autoplay\state.jsonl, and a readable version in the log:
//   state    - everything visible when the hero can act (grid, enemies, tiles, waves, skills, potions)
//   event    - what happened during a turn (decisions, actions, tiles played, attacks, hits, deaths...)
//   catalog  - name and description of each tile, skill, potion or enemy, the first time it is seen
//   analysis - the solver's scores for every move at every depth, with the evaluator's version
//
// The mod only acts when asked. F1-F4 have the Python solver score the current position and play the
// top move for that search depth, through the same calls the game's own input uses. F8 shows the
// scores without playing anything.
//
// The Harmony patches only observe method calls. They never change arguments, results or game state,
// and each one catches its own exceptions so a logging failure cannot affect the game.
//
// Written for the C# 5 compiler that ships with Windows, so no $"" strings or ?. operators.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using BepInEx;
using HarmonyLib;
using UnityEngine;

[BepInPlugin("local.shogunautoplay.statelogger", "Shogun State Logger", "0.6.0")]
public class StateLoggerPlugin : BaseUnityPlugin
{
    private const float PollIntervalSeconds = 0.1f;
    private const UnityEngine.InputSystem.Key AnalyzeKey = UnityEngine.InputSystem.Key.F8;
    private const BindingFlags AnyInstance = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;

    private static readonly FieldInfo TileToPlayField = typeof(Enemy).GetField("tileToPlay", AnyInstance);
    private static readonly PropertyInfo PatternIndexProperty = typeof(Enemy).GetProperty("PatternIndex", AnyInstance);
    private static readonly FieldInfo TurnsBeforeNextWaveField = typeof(WaveRoom).GetField("nTurnsBeforeNextWave", AnyInstance);
    private static readonly Regex RichTextTag = new Regex("<[^>]+>");

    // Each key plays the top move for the search depth of the same number.
    private static readonly UnityEngine.InputSystem.Key[] DepthKeys =
    {
        UnityEngine.InputSystem.Key.F1,
        UnityEngine.InputSystem.Key.F2,
        UnityEngine.InputSystem.Key.F3,
        UnityEngine.InputSystem.Key.F4,
    };

    private static StateLoggerPlugin instance;

    private readonly HashSet<string> catalogSeen = new HashSet<string>();
    private string statePath;
    private string lastCombatState;
    private string lastTileState;
    private string lastError;
    private int sequence;
    private int lastStateSequence;
    private int turn;
    private bool turnOpen;
    private float nextPollTime;
    private bool updateSeen;
    private readonly SolverBridge solver = new SolverBridge();
    private SolverResult analysis;
    // The depth to play once the running analysis finishes, or 0. A single value rather than a list,
    // so extra presses while waiting can't add up to extra moves.
    private int pendingDepth;
    private string pendingActionSource;
    private int pendingActionFrame;

    // A turn runs: state -> decision -> action -> results. Before the action fires, everything
    // belongs to the upcoming turn. From the action until the hero can act again, to the current one.
    private int DisplayTurn
    {
        get { return turnOpen ? turn : turn + 1; }
    }

    private void Awake()
    {
        instance = this;
        string dir = Path.Combine(Paths.BepInExRootPath, "autoplay");
        Directory.CreateDirectory(dir);
        statePath = Path.Combine(dir, "state.jsonl");
        File.WriteAllText(statePath, "");
        Logger.LogInfo("State logger loaded. Writing to " + statePath);
        Logger.LogInfo("In combat, press F1-F4 to play the top move for that depth, or " + AnalyzeKey + " to see the scores without playing.");
        ApplyPatches();
    }

    private void Update()
    {
        if (!updateSeen)
        {
            updateSeen = true;
            Logger.LogInfo("State logger Update loop is running.");
        }

        try
        {
            HandleSolverResult();
            HandleKeys();
        }
        catch (Exception ex)
        {
            ReportError(ex);
        }

        if (Time.unscaledTime < nextPollTime) return;
        nextPollTime = Time.unscaledTime + PollIntervalSeconds;

        try
        {
            Poll();
        }
        catch (Exception ex)
        {
            ReportError(ex);
        }
    }

    // Logs each distinct error once so a bad read can't flood the log every 0.1s.
    private void ReportError(Exception ex)
    {
        string message = ex.ToString();
        if (message == lastError) return;
        lastError = message;
        Logger.LogError(message);
    }

    // ---------------------------------------------------------------- solver controls

    // Every press is logged, including ones that do nothing, so the log always explains why the
    // game did or didn't respond.
    private void HandleKeys()
    {
        UnityEngine.InputSystem.Keyboard keyboard = UnityEngine.InputSystem.Keyboard.current;
        if (keyboard == null) return;

        if (keyboard[AnalyzeKey].wasPressedThisFrame) Analyze();
        for (int i = 0; i < DepthKeys.Length; i++)
        {
            if (keyboard[DepthKeys[i]].wasPressedThisFrame) PlayDepth(i + 1);
        }
    }

    private void IgnoreKey(string why)
    {
        LogEvent("step_ignored", "Key ignored: " + why, "\"why\":" + Str(why));
    }

    private void Analyze()
    {
        string blocked = WhyHeroCannotAct();
        if (blocked != null)
        {
            IgnoreKey(blocked);
            return;
        }
        if (solver.Busy)
        {
            IgnoreKey("the solver is still working");
            return;
        }
        StartAnalysis();
    }

    private void StartAnalysis()
    {
        // Log the latest state first, so the analysis can point at exactly what it was based on.
        Poll();
        analysis = null;
        solver.Start(
            "{\"seq\":" + lastStateSequence + ",\"turn\":" + DisplayTurn + "," + lastCombatState + "," + lastTileState + "}",
            lastStateSequence);
    }

    private void HandleSolverResult()
    {
        SolverResult result = solver.TakeResult();
        if (result == null) return;

        int depthToPlay = pendingDepth;
        pendingDepth = 0;

        if (result.Error != null)
        {
            LogEvent("solver_error", "Solver error: " + result.Error, "");
            return;
        }

        Poll();
        if (result.StateSequence != lastStateSequence)
        {
            IgnoreKey("the position changed while the solver was working, so press the key again");
            return;
        }

        analysis = result;
        // The solver's JSON is a whole object, and WriteLine supplies the outer braces.
        string json = result.AnalysisJson;
        WriteLine("analysis", json.Substring(1, json.Length - 2));
        Logger.LogInfo(result.Report);

        if (depthToPlay != 0) PlayDepth(depthToPlay);
    }

    private void PlayDepth(int depth)
    {
        string blocked = WhyHeroCannotAct();
        if (blocked != null)
        {
            IgnoreKey(blocked);
            return;
        }

        Poll();
        if (analysis == null || analysis.StateSequence != lastStateSequence)
        {
            // No scores for this position yet. Get them, and play when they arrive.
            pendingDepth = depth;
            if (!solver.Busy) StartAnalysis();
            return;
        }

        BestMove move;
        if (!analysis.Best.TryGetValue(depth, out move))
        {
            IgnoreKey("no analysis for depth " + depth);
            return;
        }

        CombatEnums.ActionEnum action = (CombatEnums.ActionEnum)Enum.Parse(typeof(CombatEnums.ActionEnum), move.Action);
        Tile tile = move.DeckIndex >= 0 ? GetTiles()[move.DeckIndex] : null;
        string reason = "score " + Num(move.Score) + ", plan: " + move.Line;
        string source = "Evaluator " + analysis.EvaluatorVersion + " depth " + depth;
        analysis = null;
        Execute(new Decision(action, tile, reason), source);
    }

    // Plays exactly one move through the game's own input calls, and logs where it came from.
    private void Execute(Decision decision, string source)
    {
        CombatManager combat = CombatManager.Instance;
        string tileName = TileName(decision.Tile);
        string actionText = decision.Tile != null ? decision.Action + " " + tileName : decision.Action.ToString();
        LogEvent("decision",
            "Decision: " + actionText + " | from: " + source + " | why: " + decision.Reason,
            "\"action\":" + Str(decision.Action.ToString()) +
            ",\"tile\":" + (decision.Tile != null ? Str(tileName) : "null") +
            ",\"deckIndex\":" + (decision.Tile != null ? GetTiles().IndexOf(decision.Tile).ToString() : "null") +
            ",\"source\":" + Str(source) +
            ",\"reason\":" + Str(decision.Reason) +
            ",\"basedOnStateSeq\":" + lastStateSequence);

        string refused = WhyActionRefused(combat, decision);
        if (refused != null)
        {
            LogEvent("step_refused", "Refused " + actionText + ": " + refused,
                "\"action\":" + Str(decision.Action.ToString()) + ",\"why\":" + Str(refused));
            return;
        }

        pendingActionSource = source;
        pendingActionFrame = Time.frameCount;

        if (decision.Action == CombatEnums.ActionEnum.PlayTile)
        {
            // The same call keyboard and gamepad use. It returns silently if it can't play the
            // tile, so confirm the tile really moved. The game then starts the turn by itself.
            decision.Tile.TileContainer.Submit();
            if (!(decision.Tile.TileContainer is AttackQueueTileContainer))
            {
                LogEvent("step_refused", "Refused " + actionText + ": the game didn't move the tile to the queue",
                    "\"action\":\"PlayTile\",\"why\":\"tile did not move\"");
            }
            return;
        }

        // Not "sticky": real key presses can queue during a turn, but one press must be one move.
        combat.PlayerInputsCombatAction(decision.Action, false);
    }

    // Who started the action happening now. The game starts a tile-play turn on a later update, so
    // the step's claim has to last a few frames, but no longer, or it could mislabel a later action.
    private string CurrentActionSource()
    {
        if (pendingActionSource != null && Time.frameCount <= pendingActionFrame + 2) return pendingActionSource;
        // The game itself plays the turn when the hero is frozen.
        if (Globals.Hero != null && Globals.Hero.AgentStats.ice > 0) return "game (frozen)";
        return "human";
    }

    private static string TileName(Tile tile)
    {
        return tile != null && tile.Attack != null ? tile.Attack.AttackEnum.ToString() : "?";
    }

    private static string WhyHeroCannotAct()
    {
        CombatManager combat = CombatManager.Instance;
        CombatSceneManager scene = CombatSceneManager.Instance;
        if (combat == null || scene == null || Globals.Hero == null || scene.Room == null) return "not in a run";
        if (!combat.CombatInProgress) return "no combat in progress";
        if (combat.TurnInProgress) return "the current turn is still resolving";
        if (!combat.AllowHeroAction) return "the game isn't accepting hero actions";
        if (!scene.IsCoreGameplay) return "in camp, on the map or between rooms";
        if (scene.CurrentMode != CombatSceneManager.Mode.combat) return "the game isn't in combat mode";
        if (Traverse.Create(scene).Field("pauseMenu").Field("gamePaused").GetValue<bool>()) return "the game is paused";
        foreach (Tile tile in GetTiles())
        {
            if (tile.TileContainer == null) return "a tile is being moved";
        }
        return null;
    }

    private static string WhyActionRefused(CombatManager combat, Decision decision)
    {
        bool allowed = Traverse.Create(combat).Method("HeroActionAllowed", new object[] { decision.Action }).GetValue<bool>();
        if (!allowed) return "the game says this action isn't allowed right now";
        if (decision.Action != CombatEnums.ActionEnum.PlayTile) return null;

        // These mirror the checks in the game's tile-play code, so a refusal gets a logged reason.
        Tile tile = decision.Tile;
        if (tile == null) return "the decision didn't name a tile";
        if (!(tile.TileContainer is HandTileContainer)) return "the tile isn't in the hand";
        if (!tile.TileIsEnabled) return "the tile isn't enabled";
        if (!TilesManager.Instance.CanInteractWithTiles) return "the game isn't allowing tile interaction";
        if (!Globals.Hero.AttackQueue.CanAddTile) return "the queue is full";
        return null;
    }

    // ---------------------------------------------------------------- state polling

    private void Poll()
    {
        CombatManager combat = CombatManager.Instance;
        if (combat == null || !combat.CombatInProgress || combat.TurnInProgress || !combat.AllowHeroAction) return;

        turnOpen = false;
        Hero hero = Globals.Hero;
        CombatSceneManager scene = CombatSceneManager.Instance;
        if (hero == null || scene == null || scene.Room == null || scene.Room.Grid == null) return;

        // A tile being dragged belongs to no container. Wait until it lands.
        List<Tile> tiles = GetTiles();
        foreach (Tile tile in tiles)
        {
            if (tile.TileContainer == null) return;
        }

        string combatState = BuildCombatJson(combat, hero, scene.Room);
        string tileState = BuildTilesJson(tiles);
        bool combatChanged = combatState != lastCombatState;
        if (!combatChanged && tileState == lastTileState) return;
        lastCombatState = combatState;
        lastTileState = tileState;

        WriteLine("state", combatState + "," + tileState);
        lastStateSequence = sequence;
        RecordCatalog(combat, hero, tiles);

        if (combatChanged) Logger.LogInfo(BuildTurnText(combat, hero, scene.Room, tiles));
        else Logger.LogInfo(BuildTilesText(hero, tiles));
    }

    private static List<Tile> GetTiles()
    {
        List<Tile> result = new List<Tile>();
        TilesManager manager = TilesManager.Instance;
        if (manager == null || manager.Deck == null) return result;
        foreach (Tile tile in manager.Deck)
        {
            if (tile != null) result.Add(tile);
        }
        return result;
    }

    private void WriteLine(string type, string body)
    {
        sequence++;
        File.AppendAllText(statePath,
            "{\"type\":" + Str(type) + ",\"seq\":" + sequence + ",\"turn\":" + DisplayTurn +
            ",\"time\":" + Num(Time.unscaledTime) + "," + body + "}\n");
    }

    // ---------------------------------------------------------------- JSON

    private static string BuildCombatJson(CombatManager combat, Hero hero, Room room)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append("\"room\":").Append(Str(room.GetType().Name));
        sb.Append(",\"inCamp\":").Append(Bool(Globals.InCamp));
        sb.Append(",\"cells\":").Append(room.Grid.NCells);
        sb.Append(",\"coins\":").Append(Globals.Coins);
        sb.Append(",\"wave\":");
        AppendWave(sb, room as WaveRoom);

        sb.Append(",\"hero\":");
        AppendAgent(sb, hero, hero.HeroEnum.ToString());
        sb.Append(",\"special\":");
        AppendSpecialMove(sb, hero);
        sb.Append("}");

        sb.Append(",\"enemies\":[");
        bool first = true;
        int attackOrder = 0;
        foreach (Enemy enemy in combat.Enemies)
        {
            if (enemy == null) continue;
            if (!first) sb.Append(",");
            first = false;
            AppendAgent(sb, enemy, enemy.EnemyEnum.ToString());
            sb.Append(",\"elite\":").Append(Str(enemy.EliteType.ToString()));
            sb.Append(",\"inanimate\":").Append(Bool(enemy.Inanimate));
            sb.Append(",\"traits\":[").Append(JoinEnums(Traits(enemy))).Append("]");
            sb.Append(",\"pattern\":").Append(PatternIndex(enemy));
            sb.Append(",\"tileToPlay\":").Append(Str(TileToPlay(enemy)));
            // The game numbers its attack-order badges this way in SetEnemiesAttackOrderUI.
            bool attacking = enemy.Action == CombatEnums.ActionEnum.Attack;
            sb.Append(",\"attackOrder\":").Append(attacking ? attackOrder.ToString() : "null");
            if (attacking) attackOrder++;
            sb.Append(",\"threatens\":[").Append(string.Join(",", ToStrings(ThreatenedCells(enemy, room.Grid)))).Append("]");
            sb.Append("}");
        }
        sb.Append("]");

        sb.Append(",\"skills\":[");
        first = true;
        foreach (Skill skill in GetSkills())
        {
            if (!first) sb.Append(",");
            first = false;
            sb.Append("{\"name\":").Append(Str(skill.SkillEnum.ToString()));
            sb.Append(",\"level\":").Append(skill.Level).Append("}");
        }
        sb.Append("]");

        sb.Append(",\"potions\":[");
        first = true;
        foreach (Potion potion in GetPotions())
        {
            if (!first) sb.Append(",");
            first = false;
            sb.Append(Str(potion.PotionEnum.ToString()));
        }
        sb.Append("]");
        return sb.ToString();
    }

    private static void AppendWave(StringBuilder sb, WaveRoom room)
    {
        if (room == null)
        {
            sb.Append("null");
            return;
        }
        sb.Append("{\"number\":").Append(room.WaveNumber + 1);
        sb.Append(",\"total\":").Append(room.NWaves);
        sb.Append(",\"isLast\":").Append(Bool(room.IsLastWave));
        sb.Append(",\"turnsUntilNext\":").Append(TurnsBeforeNextWave(room));
        sb.Append(",\"nextBlockedByCrowding\":").Append(Bool(NextWaveBlocked(room)));
        sb.Append("}");
    }

    private static void AppendSpecialMove(StringBuilder sb, Hero hero)
    {
        SpecialMove special = hero.SpecialMove;
        if (special == null)
        {
            sb.Append("null");
            return;
        }
        sb.Append("{\"name\":").Append(Str(special.GetType().Name));
        sb.Append(",\"enabled\":").Append(Bool(special.IsEnabled));
        if (special.Cooldown != null)
        {
            sb.Append(",\"charged\":").Append(Bool(special.Cooldown.IsCharged));
            sb.Append(",\"charge\":").Append(special.Cooldown.Charge);
            sb.Append(",\"cooldown\":").Append(special.Cooldown.Cooldown);
        }
        sb.Append("}");
    }

    // Leaves the JSON object open so callers can add their own fields.
    private static void AppendAgent(StringBuilder sb, Agent agent, string kind)
    {
        AgentStats stats = agent.AgentStats;
        sb.Append("{\"kind\":").Append(Str(kind));
        sb.Append(",\"cell\":").Append(CellIndex(agent));
        sb.Append(",\"facing\":").Append(Str(agent.FacingDir.ToString()));
        sb.Append(",\"action\":").Append(Str(agent.Action.ToString()));
        sb.Append(",\"alive\":").Append(Bool(agent.IsAlive));
        sb.Append(",\"hp\":").Append(stats.HP);
        sb.Append(",\"maxHp\":").Append(stats.maxHP);
        sb.Append(",\"shield\":").Append(Bool(stats.shield));
        sb.Append(",\"ice\":").Append(stats.ice);
        sb.Append(",\"poison\":").Append(stats.poison);
        sb.Append(",\"curse\":").Append(Bool(stats.curse));
        sb.Append(",\"queue\":[");
        bool first = true;
        foreach (Attack attack in QueueOf(agent))
        {
            if (!first) sb.Append(",");
            first = false;
            AppendAttack(sb, attack);
        }
        sb.Append("]");
    }

    private static string BuildTilesJson(List<Tile> tiles)
    {
        StringBuilder sb = new StringBuilder("\"tiles\":[");
        bool first = true;
        foreach (Tile tile in tiles)
        {
            if (!first) sb.Append(",");
            first = false;
            sb.Append("{\"where\":").Append(Str(tile.TileContainer.GetType().Name));
            sb.Append(",\"charged\":").Append(Bool(tile.FullyCharged));
            sb.Append(",\"turnsBeforeCharged\":").Append(tile.TurnsBeforeCharged);
            sb.Append(",\"interactable\":").Append(Bool(tile.Interactable));
            sb.Append(",\"attack\":");
            if (tile.Attack != null) AppendAttack(sb, tile.Attack);
            else sb.Append("null");
            sb.Append("}");
        }
        sb.Append("]");
        return sb.ToString();
    }

    private static void AppendAttack(StringBuilder sb, Attack attack)
    {
        sb.Append("{\"name\":").Append(Str(attack.AttackEnum.ToString()));
        sb.Append(",\"value\":").Append(attack.HasValue ? attack.Value.ToString() : "null");
        sb.Append(",\"cooldown\":").Append(attack.Cooldown);
        sb.Append(",\"level\":").Append(attack.Level);
        sb.Append(",\"maxLevel\":").Append(attack.MaxLevel);
        sb.Append(",\"effect\":").Append(Str(attack.AttackEffect.ToString()));
        sb.Append(",\"tileEffect\":").Append(Str(attack.TileEffect.ToString()));
        sb.Append(",\"closestTargetOnly\":").Append(Bool(Prop<bool>(attack, "ClosestTargetOnly")));
        sb.Append(",\"directional\":").Append(Bool(Prop<bool>(attack, "IsDirectional")));
        sb.Append(",\"nonLethal\":").Append(Bool(Prop<bool>(attack, "IsNonLethal")));
        sb.Append(",\"range\":[").Append(string.Join(",", ToStrings(attack.Range))).Append("]}");
    }

    // ---------------------------------------------------------------- readable text

    private string BuildTurnText(CombatManager combat, Hero hero, Room room, List<Tile> tiles)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append("\n==== Turn ").Append(DisplayTurn).Append(" | ").Append(room.GetType().Name);
        WaveRoom waveRoom = room as WaveRoom;
        if (waveRoom != null) sb.Append(" | ").Append(WaveText(waveRoom));
        sb.Append(" | ").Append(Globals.Coins).Append(" coins\n");

        sb.Append("  Grid: ").Append(BuildGridLine(room.Grid)).Append("\n");
        sb.Append("  Hero: cell ").Append(CellIndex(hero)).Append(", facing ").Append(hero.FacingDir);
        sb.Append(", HP ").Append(hero.AgentStats.HP).Append("/").Append(hero.AgentStats.maxHP);
        sb.Append(StatusText(hero)).Append(SpecialText(hero)).Append("\n");

        sb.Append("  Enemies (in acting order):\n");
        int attackOrder = 1;
        foreach (Enemy enemy in combat.Enemies)
        {
            if (enemy == null) continue;
            sb.Append("    ").Append(enemy.EnemyEnum);
            if (enemy.EliteType.ToString() != "None") sb.Append(" [elite ").Append(enemy.EliteType).Append("]");
            string traits = string.Join(", ", ToStrings(Traits(enemy)));
            if (traits.Length > 0) sb.Append(" [").Append(traits).Append("]");
            sb.Append(": cell ").Append(CellIndex(enemy)).Append(", facing ").Append(enemy.FacingDir);
            sb.Append(", HP ").Append(enemy.AgentStats.HP).Append("/").Append(enemy.AgentStats.maxHP);
            sb.Append(StatusText(enemy));
            sb.Append(", next: ").Append(enemy.Action);
            if (enemy.Action == CombatEnums.ActionEnum.PlayTile) sb.Append(" ").Append(TileToPlay(enemy));
            if (enemy.Action == CombatEnums.ActionEnum.Attack)
            {
                sb.Append(" #").Append(attackOrder);
                attackOrder++;
                sb.Append(" -> cells ").Append(string.Join(",", ToStrings(ThreatenedCells(enemy, room.Grid))));
            }
            string queue = QueueText(enemy);
            if (queue.Length > 0) sb.Append(", queue: ").Append(queue);
            sb.Append("\n");
        }

        sb.Append(BuildTilesText(hero, tiles));

        List<string> skills = new List<string>();
        foreach (Skill skill in GetSkills()) skills.Add(skill.SkillEnum + " L" + skill.Level);
        if (skills.Count > 0) sb.Append("\n  Skills: ").Append(string.Join(", ", skills.ToArray()));

        List<string> potions = new List<string>();
        foreach (Potion potion in GetPotions()) potions.Add(potion.PotionEnum.ToString());
        if (potions.Count > 0) sb.Append("\n  Potions: ").Append(string.Join(", ", potions.ToArray()));
        return sb.ToString();
    }

    private static string BuildTilesText(Hero hero, List<Tile> tiles)
    {
        StringBuilder sb = new StringBuilder();
        string queue = QueueText(hero);
        sb.Append("  Queue: ").Append(queue.Length > 0 ? queue : "(empty)").Append("\n");
        sb.Append("  Tiles:");
        foreach (Tile tile in tiles)
        {
            if (tile.Attack == null || tile.TileContainer.GetType().Name.Contains("AttackQueue")) continue;
            sb.Append("\n    ").Append(AttackText(tile.Attack));
            sb.Append(", cooldown ").Append(tile.Attack.Cooldown);
            sb.Append(tile.FullyCharged ? ", READY" : ", charging " + tile.TurnsBeforeCharged + " more turns");
        }
        return sb.ToString();
    }

    private static string AttackText(Attack attack)
    {
        StringBuilder sb = new StringBuilder(attack.AttackEnum.ToString());
        if (attack.Level > 0) sb.Append(" L").Append(attack.Level);
        if (attack.HasValue) sb.Append(" ").Append(attack.Value).Append(" dmg");
        sb.Append(", range ").Append(RangeText(attack.Range));
        if (attack.AttackEffect.ToString() != "None") sb.Append(", effect ").Append(attack.AttackEffect);
        if (attack.TileEffect.ToString() != "None") sb.Append(", tile effect ").Append(attack.TileEffect);
        return sb.ToString();
    }

    private static string QueueText(Agent agent)
    {
        List<string> parts = new List<string>();
        foreach (Attack attack in QueueOf(agent)) parts.Add(AttackText(attack));
        return string.Join(" | ", parts.ToArray());
    }

    // Offsets are relative to facing, with positive meaning in front.
    private static string RangeText(int[] range)
    {
        if (range == null || range.Length == 0) return "none";
        bool consecutive = range.Length > 2;
        for (int i = 1; i < range.Length && consecutive; i++)
        {
            consecutive = range[i] == range[i - 1] + 1;
        }
        if (consecutive) return range[0] + ".." + range[range.Length - 1];
        return string.Join(",", ToStrings(range));
    }

    private static string WaveText(WaveRoom room)
    {
        string text = "wave " + (room.WaveNumber + 1) + "/" + room.NWaves;
        if (room.IsLastWave) return text + " (final)";
        text += ", next in " + TurnsBeforeNextWave(room) + " turns";
        if (NextWaveBlocked(room)) text += " (blocked: room too crowded)";
        return text;
    }

    private static string StatusText(Agent agent)
    {
        AgentStats stats = agent.AgentStats;
        string text = "";
        if (stats.shield) text += ", shield";
        if (stats.ice > 0) text += ", ice " + stats.ice;
        if (stats.poison > 0) text += ", poison " + stats.poison;
        if (stats.curse) text += ", curse";
        return text;
    }

    private static string SpecialText(Hero hero)
    {
        SpecialMove special = hero.SpecialMove;
        if (special == null || special.Cooldown == null) return "";
        return ", special " + special.GetType().Name + " " +
               (special.Cooldown.IsCharged ? "READY" : special.Cooldown.Charge + "/" + special.Cooldown.Cooldown);
    }

    private static string BuildGridLine(CombatGrid grid)
    {
        StringBuilder sb = new StringBuilder();
        foreach (Cell cell in grid.Cells)
        {
            if (sb.Length > 0) sb.Append("  ");
            sb.Append(cell.IndexInGrid).Append(":");
            Agent agent = cell.Agent;
            if (agent == null)
            {
                sb.Append(".");
                continue;
            }
            Enemy enemy = agent as Enemy;
            string label = enemy != null ? enemy.EnemyEnum.ToString() : "HERO";
            bool facingLeft = agent.FacingDir == Utils.Dir.Left;
            sb.Append(facingLeft ? "<" : "").Append(label).Append(facingLeft ? "" : ">");
        }
        return sb.ToString();
    }

    // ---------------------------------------------------------------- catalog

    private void RecordCatalog(CombatManager combat, Hero hero, List<Tile> tiles)
    {
        foreach (Tile tile in tiles)
        {
            if (tile.Attack != null) RecordAttackCatalog(tile.Attack);
        }
        foreach (Enemy enemy in combat.Enemies)
        {
            if (enemy == null) continue;
            AddCatalog("enemy", enemy.EnemyEnum.ToString(), enemy.Name, enemy.Description);
            foreach (Attack attack in QueueOf(enemy)) RecordAttackCatalog(attack);
        }
        foreach (Skill skill in GetSkills())
        {
            AddCatalog("skill", skill.SkillEnum + " L" + skill.Level, skill.Name, skill.Description);
        }
        foreach (Potion potion in GetPotions())
        {
            AddCatalog("potion", potion.PotionEnum.ToString(), potion.Name, potion.Description);
        }
        AddCatalog("hero", hero.HeroEnum.ToString(), hero.SpecialAbilityName, hero.SpecialAbilityDescription);
    }

    private void RecordAttackCatalog(Attack attack)
    {
        string key = attack.AttackEnum + " L" + attack.Level + " " + attack.AttackEffect + " " + attack.TileEffect;
        AddCatalog("tile", key, attack.Name, attack.Description);
    }

    private void AddCatalog(string kind, string key, string name, string description)
    {
        if (!catalogSeen.Add(kind + ":" + key)) return;
        string cleanName = Clean(name);
        string cleanDescription = Clean(description);
        WriteLine("catalog", "\"kind\":" + Str(kind) + ",\"key\":" + Str(key) +
            ",\"name\":" + Str(cleanName) + ",\"description\":" + Str(cleanDescription));
        Logger.LogInfo("  [new " + kind + "] " + key + " = " + cleanName + ": " + cleanDescription);
    }

    private static string Clean(string text)
    {
        return text == null ? "" : RichTextTag.Replace(text, "").Replace("\r", " ").Replace("\n", " ").Trim();
    }

    // ---------------------------------------------------------------- game-state helpers

    private static List<Attack> QueueOf(Agent agent)
    {
        List<Attack> result = new List<Attack>();
        if (agent.AttackQueue == null) return result;
        foreach (Attack attack in agent.AttackQueue.Attacks)
        {
            if (attack != null) result.Add(attack);
        }
        return result;
    }

    private static List<Skill> GetSkills()
    {
        List<Skill> result = new List<Skill>();
        SkillsManager manager = SkillsManager.Instance;
        if (manager == null || manager.Skills == null) return result;
        foreach (Skill skill in manager.Skills)
        {
            if (skill != null) result.Add(skill);
        }
        return result;
    }

    private static List<Potion> GetPotions()
    {
        List<Potion> result = new List<Potion>();
        PotionsManager manager = PotionsManager.Instance;
        if (manager == null || manager.HeldPotions == null) return result;
        foreach (Potion potion in manager.HeldPotions)
        {
            if (potion != null) result.Add(potion);
        }
        return result;
    }

    // Cells an enemy's queued attacks reach, from each attack's range and the enemy's facing.
    // This ignores blocking and special targeting, so treat it as a close estimate.
    private static int[] ThreatenedCells(Enemy enemy, CombatGrid grid)
    {
        if (enemy.Action != CombatEnums.ActionEnum.Attack || enemy.Cell == null) return new int[0];
        int direction = enemy.FacingDir == Utils.Dir.Left ? -1 : 1;
        SortedDictionary<int, bool> cells = new SortedDictionary<int, bool>();
        foreach (Attack attack in QueueOf(enemy))
        {
            if (attack.Range == null) continue;
            foreach (int offset in attack.Range)
            {
                int cell = enemy.Cell.IndexInGrid + direction * offset;
                if (cell >= 0 && cell < grid.NCells) cells[cell] = true;
            }
        }
        int[] result = new int[cells.Count];
        cells.Keys.CopyTo(result, 0);
        return result;
    }

    // Reads a protected or private property that the compiler won't let us touch directly.
    private static T Prop<T>(object target, string name)
    {
        return Traverse.Create(target).Property(name).GetValue<T>();
    }

    private static AgentEnums.EnemyTraitsEnum[] Traits(Enemy enemy)
    {
        return Prop<AgentEnums.EnemyTraitsEnum[]>(enemy, "EnemyTraits");
    }

    private static bool NextWaveBlocked(WaveRoom room)
    {
        return Traverse.Create(room).Method("NextWaveWouldBeTooCrowded").GetValue<bool>();
    }

    private static int CellIndex(Agent agent)
    {
        return agent.Cell != null ? agent.Cell.IndexInGrid : -1;
    }

    private static string TileToPlay(Enemy enemy)
    {
        object value = TileToPlayField != null ? TileToPlayField.GetValue(enemy) : null;
        return value == null ? "" : value.ToString();
    }

    private static string PatternIndex(Enemy enemy)
    {
        object value = PatternIndexProperty != null ? PatternIndexProperty.GetValue(enemy, null) : null;
        return value == null ? "null" : value.ToString();
    }

    private static int TurnsBeforeNextWave(WaveRoom room)
    {
        return TurnsBeforeNextWaveField != null ? (int)TurnsBeforeNextWaveField.GetValue(room) : -1;
    }

    private static string AgentLabel(Agent agent)
    {
        if (agent == null) return "(no attacker)";
        Enemy enemy = agent as Enemy;
        string label = enemy != null ? enemy.EnemyEnum.ToString() : "HERO";
        return label + "@" + CellIndex(agent);
    }

    // ---------------------------------------------------------------- formatting helpers

    private static string JoinEnums<T>(T[] values)
    {
        if (values == null) return "";
        string[] parts = new string[values.Length];
        for (int i = 0; i < values.Length; i++) parts[i] = Str(values[i].ToString());
        return string.Join(",", parts);
    }

    private static string[] ToStrings<T>(T[] values)
    {
        if (values == null) return new string[0];
        string[] parts = new string[values.Length];
        for (int i = 0; i < values.Length; i++) parts[i] = values[i].ToString();
        return parts;
    }

    private static string Bool(bool value)
    {
        return value ? "true" : "false";
    }

    private static string Num(float value)
    {
        return value.ToString("0.00", CultureInfo.InvariantCulture);
    }

    private static string Str(string value)
    {
        if (value == null) return "null";
        return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r").Replace("\t", "\\t") + "\"";
    }

    // ---------------------------------------------------------------- events (Harmony patches)

    private void LogEvent(string name, string text, string extraJson)
    {
        string body = "\"event\":" + Str(name) + ",\"text\":" + Str(text);
        if (!string.IsNullOrEmpty(extraJson)) body += "," + extraJson;
        WriteLine("event", body);
        Logger.LogInfo("  > " + text);
    }

    private static void SafeEvent(Action action)
    {
        try
        {
            if (instance != null) action();
        }
        catch (Exception ex)
        {
            if (instance != null) instance.ReportError(ex);
        }
    }

    private void ApplyPatches()
    {
        Harmony harmony = new Harmony("local.shogunautoplay.statelogger");
        Patch(harmony, typeof(CombatManager), "BeginCombat", null, "OnBeginCombat");
        // A prefix, because TriggerTurn runs the start of the turn (including attacks) before returning.
        Patch(harmony, typeof(CombatManager), "TriggerTurn", "OnTriggerTurn", null);
        Patch(harmony, typeof(CombatManager), "HeroPlayedTile", null, "OnHeroPlayedTile");
        Patch(harmony, typeof(CombatSceneManager), "EndOfCombat", null, "OnEndOfCombat");
        Patch(harmony, typeof(Agent), "ReceiveAttack", "BeforeReceiveAttack", "AfterReceiveAttack");
        Patch(harmony, typeof(Agent), "Die", null, "OnDie");
        Patch(harmony, typeof(Hero), "AttackHasBeenPlayed", null, "OnAttackPlayed");
        Patch(harmony, typeof(Enemy), "AttackHasBeenPlayed", null, "OnAttackPlayed");
        Patch(harmony, typeof(Enemy), "PlayTileAction", null, "OnEnemyPlayTile");
        Patch(harmony, typeof(WaveRoom), "SpawnNextWave", null, "OnSpawnNextWave");
        Patch(harmony, typeof(SkillsManager), "OnSkillTriggered", null, "OnSkillTriggered");
    }

    // One failed patch shouldn't cost us the others, so each is applied separately.
    private void Patch(Harmony harmony, Type type, string method, string prefix, string postfix)
    {
        try
        {
            MethodInfo target = AccessTools.Method(type, method);
            if (target == null)
            {
                Logger.LogError("Could not find " + type.Name + "." + method);
                return;
            }
            harmony.Patch(target,
                prefix != null ? new HarmonyMethod(typeof(StateLoggerPlugin), prefix) : null,
                postfix != null ? new HarmonyMethod(typeof(StateLoggerPlugin), postfix) : null);
        }
        catch (Exception ex)
        {
            Logger.LogError("Could not patch " + type.Name + "." + method + ": " + ex);
        }
    }

    public static void OnBeginCombat(bool campMode)
    {
        SafeEvent(delegate
        {
            instance.turn = 0;
            instance.turnOpen = false;
            instance.LogEvent("combat_start", "Combat begins" + (campMode ? " (camp)" : ""), "");
        });
    }

    public static void OnEndOfCombat()
    {
        SafeEvent(delegate { instance.LogEvent("combat_end", "Combat ended", ""); });
    }

    public static void OnTriggerTurn(CombatEnums.ActionEnum heroAction)
    {
        SafeEvent(delegate
        {
            instance.turn++;
            instance.turnOpen = true;
            string source = instance.CurrentActionSource();
            instance.pendingActionSource = null;
            instance.LogEvent("hero_action", "Turn " + instance.turn + " action: HERO " + heroAction + " [from: " + source + "]",
                "\"action\":" + Str(heroAction.ToString()) + ",\"source\":" + Str(source));
        });
    }

    public static void OnHeroPlayedTile(Tile tile)
    {
        SafeEvent(delegate
        {
            string name = TileName(tile);
            string source = instance.CurrentActionSource();
            instance.LogEvent("hero_tile", "HERO queues tile " + name + " [from: " + source + "]",
                "\"tile\":" + Str(name) + ",\"source\":" + Str(source));
        });
    }

    public static void OnEnemyPlayTile(Enemy __instance)
    {
        SafeEvent(delegate
        {
            string name = TileToPlay(__instance);
            instance.LogEvent("enemy_tile", AgentLabel(__instance) + " queues tile " + name,
                "\"agent\":" + Str(__instance.EnemyEnum.ToString()) + ",\"tile\":" + Str(name));
        });
    }

    public static void OnAttackPlayed(Agent __instance, Attack attack)
    {
        SafeEvent(delegate
        {
            string name = attack != null ? attack.AttackEnum.ToString() : "?";
            instance.LogEvent("attack", AgentLabel(__instance) + " attacks with " + name,
                "\"agent\":" + Str(AgentLabel(__instance)) + ",\"attack\":" + Str(name));
        });
    }

    public static void BeforeReceiveAttack(Agent __instance, out int[] __state)
    {
        __state = null;
        try
        {
            __state = new[] { __instance.AgentStats.HP, __instance.AgentStats.shield ? 1 : 0 };
        }
        catch (Exception ex)
        {
            if (instance != null) instance.ReportError(ex);
        }
    }

    public static void AfterReceiveAttack(Agent __instance, Agent attacker, int[] __state)
    {
        if (__state == null) return;
        int hpBefore = __state[0];
        bool hadShield = __state[1] == 1;
        SafeEvent(delegate
        {
            int hpAfter = __instance.AgentStats.HP;
            int damage = hpBefore - hpAfter;
            string result = hadShield && damage == 0
                ? "shield blocked it"
                : damage + " damage, HP " + hpBefore + " -> " + hpAfter;
            instance.LogEvent("hit", AgentLabel(attacker) + " hits " + AgentLabel(__instance) + ": " + result,
                "\"from\":" + Str(AgentLabel(attacker)) + ",\"to\":" + Str(AgentLabel(__instance)) +
                ",\"damage\":" + damage + ",\"hpBefore\":" + hpBefore + ",\"hpAfter\":" + hpAfter +
                ",\"shieldBefore\":" + Bool(hadShield));
        });
    }

    public static void OnDie(Agent __instance)
    {
        SafeEvent(delegate
        {
            instance.LogEvent("death", AgentLabel(__instance) + " dies", "\"agent\":" + Str(AgentLabel(__instance)));
        });
    }

    public static void OnSpawnNextWave(WaveRoom __instance)
    {
        SafeEvent(delegate
        {
            int number = __instance.WaveNumber + 1;
            instance.LogEvent("wave_spawn", "Wave " + number + "/" + __instance.NWaves + " spawns",
                "\"number\":" + number + ",\"total\":" + __instance.NWaves);
        });
    }

    public static void OnSkillTriggered(SkillEnums.SkillEnum skillEnum)
    {
        SafeEvent(delegate
        {
            instance.LogEvent("skill", "Skill triggered: " + skillEnum, "\"skill\":" + Str(skillEnum.ToString()));
        });
    }
}
