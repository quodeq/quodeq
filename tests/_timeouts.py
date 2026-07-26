"""One knob for every wall-clock budget in the suite.

CI's Windows runner has 4 vCPUs and the job runs pytest-xdist with ``-n auto``,
so four workers saturate the box. A literal ``wait(timeout=5)`` that is
generous on an idle laptop becomes a coin flip there: a worker thread can miss
its window purely because it never got scheduled. That is not hypothetical —
run 30148774491 on develop logged a daemon thread dying on
``assert cancel.wait(timeout=5)`` in ``test_assistant_routes.py`` while the
stop route it was waiting for had not been scheduled yet.

Wrap positive waits in ``budget()`` and set ``QUODEQ_TEST_TIMEOUT_SCALE`` on
the loaded runners instead of hand-tuning individual call sites. Local runs
stay fast because the default scale is 1.

Only wrap a wait that guards something that *should* happen. A wait that
proves a thing does *not* happen (``assert not done.wait(timeout=0.01)``)
already returns as late as it ever will; scaling it only burns wall time.
"""
from __future__ import annotations

import os

_ENV_VAR = "QUODEQ_TEST_TIMEOUT_SCALE"


def scale() -> float:
    """Return the configured budget multiplier, or 1.0 if unusable.

    Read at call time, not at import, so a fixture can change it mid-session.
    A missing, unparseable, or non-positive value falls back to 1.0 rather
    than raising: a broken knob must never take the suite down with it, and a
    zero multiplier would silently turn every wait into a no-op.
    """
    raw = os.environ.get(_ENV_VAR)
    if raw is None:
        return 1.0
    try:
        parsed = float(raw)
    except ValueError:
        return 1.0
    return parsed if parsed > 0 else 1.0


def budget(seconds: float) -> float:
    """Scale ``seconds`` up by the configured multiplier.

    Clamped so the result is never *below* the budget the caller asked for.
    The knob exists to buy headroom on contended runners; letting it shrink a
    timeout would make the suite flakier, which is the opposite of the point.
    """
    return max(float(seconds), float(seconds) * scale())
