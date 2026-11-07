"""Compares two replays from tools/replay.py: totals by log, and each board whose choice changed.

    python tools/compare.py v1.28 v2.1          # names of files in research/replays/
    python tools/compare.py v1.28 v2.1 --show   # also list every changed choice
"""
import argparse
import json
from pathlib import Path

REPLAYS = Path(__file__).resolve().parent.parent / "research" / "replays"


def load(name):
    path = Path(name) if name.endswith(".json") else REPLAYS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base")
    parser.add_argument("variant")
    parser.add_argument("--show", action="store_true", help="list every changed choice")
    args = parser.parse_args()
    base, var = load(args.base), load(args.variant)
    keys = [k for k in base if k in var]
    logs = sorted({k.split()[0] for k in keys}, key=lambda log: next(i for i, k in enumerate(keys) if k.startswith(log + " ")))
    for log in logs:
        in_log = [k for k in keys if k.split()[0] == log]

        def total(d, field):
            return sum(d[k][field] for k in in_log)

        changed = [k for k in in_log if base[k]["label"] != var[k]["label"]]
        print(f"  {log:<11} changed {len(changed):>3}/{len(in_log):<4} hp {total(base, 'hp')}->{total(var, 'hp')}"
              f"  kills {total(base, 'kills')}->{total(var, 'kills')}  dmg {total(base, 'dmg')}->{total(var, 'dmg')}"
              f"  wasted {total(base, 'wasted')}->{total(var, 'wasted')}"
              f"  fewer kills {sum(var[k]['kills'] < base[k]['kills'] for k in in_log)}"
              f"  more hp lost {sum(var[k]['hp'] > base[k]['hp'] for k in in_log)}")
        if args.show:
            for k in changed:
                b, v = base[k], var[k]
                print(f"      {k:<18} {b['label'][:44]:<44} -> {v['label'][:44]:<44}"
                      f" dmg {b['dmg']}->{v['dmg']} kills {b['kills']}->{v['kills']} hp {b['hp']}->{v['hp']}")
    missing = len(set(base) ^ set(var))
    if missing:
        print(f"  ({missing} boards are in only one of the two)")


if __name__ == "__main__":
    main()
