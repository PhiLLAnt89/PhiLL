"""Run the test suite: every test_*.py in its own process, against tests/mock/unreal (a fake of the Unreal Python API).

    python tests/run_all.py            (needs: pip install "PySide6-Essentials>=6.5,<6.12" pyflakes)

Qt renders offscreen. Screenshots of the UI land in tests/_out/.
"""
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([os.path.join(HERE, "mock"), HERE, ROOT, env.get("PYTHONPATH", "")])
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    failed = []
    for path in tests:
        name = os.path.basename(path)
        t0 = time.time()
        proc = subprocess.run([sys.executable, path], cwd=HERE, env=env, capture_output=True, text=True, timeout=600)
        ok = proc.returncode == 0
        print("%-28s %s  (%.1fs)" % (name, "PASS" if ok else "FAIL", time.time() - t0))
        if not ok:
            failed.append(name)
            print("\n".join(("    " + l) for l in (proc.stdout + proc.stderr).strip().splitlines()[-25:]))
    print("\n%d/%d passed" % (len(tests) - len(failed), len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
