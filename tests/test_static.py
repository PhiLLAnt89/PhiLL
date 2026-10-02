"""Static invariants of the script: compiles, lint-clean, paste-safe for Unreal's Output Log."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "world_perf_audit.py")
src = open(SCRIPT, encoding="utf-8").read()

compile(src, SCRIPT, "exec")
# Pasting into the Output Log (Python mode): Unreal treats text containing the Python file extension as a file path.
assert ".py" not in src.lower(), "the script must never contain the Python file extension (breaks Output Log paste)"
assert all(ord(c) < 128 for c in src), "keep the script ASCII-only (escape unicode in strings) for safe pasting"
assert "from __future__" not in src, "no __future__ imports (pasted code may not start at the top of a file)"
m = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"', src, re.M)
assert m, "missing __version__"
try:
    out = subprocess.run([sys.executable, "-m", "pyflakes", SCRIPT], capture_output=True, text=True)
    if out.returncode not in (0, 1) or "No module named pyflakes" in out.stderr:
        print("pyflakes not installed - skipped")
    else:
        assert out.returncode == 0, "pyflakes:\n" + out.stdout + out.stderr
except FileNotFoundError:
    pass
print("STATIC OK (version %s)" % m.group(1))
