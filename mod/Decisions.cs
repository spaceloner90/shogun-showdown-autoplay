using CombatEnums;

// One move for the mod to play.
public sealed class Decision
{
    public readonly ActionEnum Action;

    // Which tile to play. Only used when Action is PlayTile.
    public readonly Tile Tile;

    // Why this action was chosen, in plain words. It goes straight into the log.
    public readonly string Reason;

    // For Attack: the tiles to fire in order, by position in the deck, which can include Free Play
    // tiles still in hand. Null fires the queue as it is.
    public readonly int[] AttackOrder;

    // For PlayTile with a full queue: the queued tile to send back to hand first, a free queue edit. Null if none.
    public readonly Tile ReplaceTile;

    public Decision(ActionEnum action, Tile tile, string reason, int[] attackOrder = null, Tile replaceTile = null)
    {
        Action = action;
        Tile = tile;
        Reason = reason;
        AttackOrder = attackOrder;
        ReplaceTile = replaceTile;
    }
}
