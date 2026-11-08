"""Times F1 to F4 from solver/search.py on a spread of core boards.

    python tools/time_search.py [--every 12] [--count 60] [--depths 2 3 4] [--leaf full|lite] [--beam 4]
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "solver"))
import search  # noqa: E402
from logged_boards import logged_boards  # noqa: E402
from rules import state_from_log  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--every", type=int, default=12)
parser.add_argument("--count", type=int, default=60)
parser.add_argument("--depths", type=int, nargs="+", default=[2, 3, 4])
parser.add_argument("--beam", type=int, default=search.BEAM)
args = parser.parse_args()
boards = [state_from_log(r) for _, r in logged_boards(core=True)][::args.every][:args.count]
for depth in args.depths:
    times = []
    for state in boards:
        started = time.perf_counter()
        search.rank_lines(state, depth, beam=args.beam)
        times.append(time.perf_counter() - started)
    times.sort()
    print(f"F{depth}: mean {statistics.mean(times):.3f} median {times[len(times) // 2]:.3f} "
          f"p90 {times[int(len(times) * 0.9)]:.3f} max {times[-1]:.3f}")
