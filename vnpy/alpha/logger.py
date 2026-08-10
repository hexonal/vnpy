"""
Research-side logging sink for ``vnpy.alpha``
=============================================

* **Importing this module must never take a sink away from someone else.**
  Upstream opened with a bare ``logger.remove()``, which removes *every*
  handler in loguru's global table, not just loguru's own default. The comment
  above it said "Remove default output", so the intent was only ever handler
  ``0``; the call was simply wider than the intent. ``vnpy.trader.logger`` had
  already installed two handlers by then — a stdout sink and
  ``~/.vntrader/log/vt_<date>.log`` — and both died on the spot.

* **The two production entry points that hit this were ``run.py`` and
  ``run_gui.py``.** Neither imports ``vnpy.alpha`` by name; both import
  ``vnpy_alphakit.rules`` a few lines after ``MainEngine``, and
  ``vnpy_alphakit/__init__.py`` reaches ``vnpy.alpha`` through ``.bridge``.
  Measured on this machine, walking each entry point's import block one line at
  a time: ``run.py`` line 35 installs the file sink, line 40 takes it away;
  ``run_gui.py`` line 48 installs it, line 50 takes it away.
  ``run_live_alpha.py`` happens to survive only because it imports
  ``vnpy.alpha.lab`` *before* ``MainEngine`` — the fix does not rest on that
  accident holding.

* **The measured consequence is a silent one.** A real ``MainEngine`` built
  after that import order, then ``write_log`` of one marker line: the marker
  reaches stdout and the day's log file stays **0 bytes**. Nothing raises,
  ``LogEngine`` still forwards every ``EVENT_LOG``, and the GUI log panel keeps
  scrolling — the on-disk record of a trading session is just gone. Three more
  settings flipped along with it: the sink's level threshold went from
  ``SETTINGS["log.level"]`` (20, INFO) back to loguru's DEBUG default (10),
  ``colorize`` went from auto-detected ``False`` to a forced ``True`` that
  writes ANSI escapes into redirected output, and with
  ``"log.console": false`` in ``vt_setting.json`` the operator's configuration
  came out exactly inverted — console on, file off.

* **Why the fix is not simply deleting the ``remove()`` line.** Left alone,
  this module would then add a second stdout sink on top of the trader's, and
  every log line in the GUI process would print twice. The sink here is a
  convenience for standalone research use — a notebook that imports
  ``vnpy.alpha`` and nothing else — so it is claimed only when nobody else has
  configured loguru, and loguru's own default handler is dropped by id instead
  of by sweeping the table.

* **The reverse import order is deliberately left as it is.**
  ``vnpy.trader.logger`` still calls the wide ``logger.remove()``, so importing
  ``vnpy.alpha`` first and ``MainEngine`` second ends with the trader's two
  handlers and none of ours — which is the right outcome (the trader's format
  carries level and gateway, and its file sink is the one that matters) and
  also what that order already did. Narrowing the trader's call too would
  produce the double-printing described above.

* **The handler table is read through a private attribute.** loguru exposes no
  public way to ask "has anyone configured me", and ``logger.remove(0)`` cannot
  answer it either: a raised ``ValueError`` says the default is already gone,
  not whether anything replaced it. If the attribute ever disappears the
  fallback is to add the sink, i.e. upstream's behaviour minus the sweep.
"""

import sys

from loguru import logger


def _configure_default_sink() -> None:
    """Claim a stdout sink for standalone research use, and only then.

    Two things happen here, in this order, and both are narrower than what
    upstream did. Loguru's own default handler is id ``0`` and nothing else
    ever is, so removing it by id drops the pre-configured stderr output
    without touching a sink some other module installed. Then a stdout sink is
    added only if the table is empty afterwards — an already-configured logger
    (``vnpy.trader.logger`` being the one that matters) keeps its own
    formatting and its own file, and research log records flow into it rather
    than beside it.
    """
    try:
        logger.remove(0)
    except ValueError:
        # Handler 0 was already removed — by vnpy.trader.logger's sweep, by a
        # notebook, or by an earlier import of this module. Not an error, and
        # not evidence about what else is installed; the check below decides.
        pass

    try:
        occupied: bool = bool(logger._core.handlers)     # type: ignore[attr-defined]
    except AttributeError:
        # A loguru version that no longer keeps the table there. Fall back to
        # upstream's behaviour without the sweep: a possible duplicate console
        # line is a visible annoyance, a missing trading log file is not.
        occupied = False

    if occupied:
        return

    fmt: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>{message}</level>"
    logger.add(sys.stdout, colorize=True, format=fmt)


_configure_default_sink()
