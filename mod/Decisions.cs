using CombatEnums;

// One move for the mod to play.
public sealed class Decision
{
    public readonly ActionEnum Action;

    // Which tile to play. Only used when Action is PlayTile.
    public readonly Tile Tile;

    // Why this action was chosen, in plain words. It goes straight into the log.
    public readonly string Reason;

    public Decision(ActionEnum action, Tile tile, string reason)
    {
        Action = action;
        Tile = tile;
        Reason = reason;
    }
}
