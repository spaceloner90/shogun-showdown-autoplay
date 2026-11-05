"""Print selected types or method bodies from research/il.txt.

Usage: python tools/il_show.py Type            -> signatures of a type (no IL)
       python tools/il_show.py Type.Method     -> IL of every overload of that method
"""
import re
import sys
from pathlib import Path

IL_PATH = Path(__file__).resolve().parent.parent / "research" / "il.txt"


def parse_types():
    types = {}
    current = None
    for line in IL_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("TYPE "):
            current = line.split(" : ")[0][5:]
            types[current] = [line]
        elif current:
            types[current].append(line)
    return types


def show_type(lines):
    for line in lines:
        if not line.startswith("      IL_"):
            print(line)


def show_method(lines, method):
    pattern = re.compile(r"^  M \S* ?" + re.escape(method) + r"\(")
    printing = False
    found = False
    for line in lines:
        if line.startswith("  "):
            if not line.startswith("      "):
                printing = bool(pattern.match(line))
                found = found or printing
            if printing:
                print(line)
    return found


def main():
    types = parse_types()
    for query in sys.argv[1:]:
        print(f"\n##### {query}")
        if query in types:
            show_type(types[query])
            continue
        type_name, _, method = query.rpartition(".")
        if type_name not in types:
            print("  (not found)")
        elif not show_method(types[type_name], method):
            print("  (method not found)")


if __name__ == "__main__":
    main()
