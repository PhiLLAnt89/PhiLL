"""Fake clock for the async jobs (the profiler polls every 0.25 s and waits for 1 s of stable file size)."""
import types


class Clock(object):
    t = 1000.0


def install(W):
    W.time = types.SimpleNamespace(time=lambda: Clock.t)


def run_ticks(U, n=20, step=0.3):
    for _ in range(n):
        Clock.t += step
        U.flush_screenshots()
        for fn in list(U.TICKS):
            if fn:
                fn(0.016)


def run_until_idle(U, W, limit=2000, step=0.3):
    """Tick until the running job finishes (fails the test if it never does)."""
    for _ in range(limit):
        if not W._PROFILE["busy"]:
            return
        run_ticks(U, 1, step)
    raise AssertionError("job still running after %d ticks" % limit)
