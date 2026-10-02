"""Fake clock for the async profiler polling (it waits 0.25 s between polls and 1 s of stable file size)."""
import types


class Clock(object):
    t = 1000.0


def install(W):
    W.time = types.SimpleNamespace(time=lambda: Clock.t)


def run_ticks(U, n=20, step=0.3):
    for _ in range(n):
        Clock.t += step
        for fn in list(U.TICKS):
            if fn:
                fn(0.016)
