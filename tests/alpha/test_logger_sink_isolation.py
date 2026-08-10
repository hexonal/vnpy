"""
Regression tests for ``vnpy.alpha`` taking the trading log file away.

``vnpy/alpha/logger.py`` opened with a bare ``logger.remove()``. Loguru's table
is global and process-wide, so that call removed whatever
``vnpy.trader.logger`` had installed a few imports earlier — a stdout sink and
``~/.vntrader/log/vt_<date>.log`` — and replaced both with one bare stdout
handler. Nothing raised. ``LogEngine`` kept forwarding every ``EVENT_LOG``, the
GUI panel kept scrolling, and the day's file stayed empty.

Neither production entry point that hits this imports ``vnpy.alpha`` by name:
``run.py`` and ``run_gui.py`` import ``vnpy_alphakit.rules`` shortly after
``MainEngine``, and ``vnpy_alphakit/__init__.py`` reaches ``vnpy.alpha`` through
``.bridge``. So the tests below reproduce the *order* rather than the symptom's
usual spelling.

**Everything here runs in a subprocess, and that is not incidental.** The bug
lives entirely in module-import side effects, and Python caches modules — a
second import inside one interpreter is a no-op, which would make every
assertion here trivially green. ``sys.executable`` with a fresh ``cwd`` is the
only way to observe the first import.

The ``cwd`` matters twice over: ``vnpy.trader.utility`` picks ``TRADER_DIR`` by
asking whether ``./.vntrader`` exists, so a ``tmp_path`` containing an empty
``.vntrader`` directory keeps these tests off the real ``~/.vntrader/log`` while
still exercising the genuine file sink rather than a stand-in.

The reverse order — ``vnpy.alpha`` first, ``MainEngine`` second — is pinned as
something that must keep working the way it already does: ``vnpy.trader.logger``
still sweeps the table, ours goes away, and the trader's two handlers are what
remains. That is the desired outcome (the trader's format carries level and
gateway name), and pinning it stops a later "make the trader narrow too" edit
from quietly introducing a doubled console.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subprocess harness
# ---------------------------------------------------------------------------

#: Printed as one JSON line so the parent can assert on structure rather than
#: grep the child's own log output, which is precisely what these tests move
#: around and therefore cannot be trusted as a channel.
REPORT: str = """
import json
from loguru import logger

def report(tag):
    rows = []
    for handler_id, handler in logger._core.handlers.items():
        rows.append({
            "id": handler_id,
            "sink": getattr(handler, "_name", repr(handler)),
            "level": handler._levelno,
            "colorize": handler._colorize,
        })
    print("REPORT " + json.dumps({"tag": tag, "handlers": rows}))
"""


def run_child(tmp_path: Path, body: str) -> list[dict]:
    """Run ``body`` in a fresh interpreter rooted at a throwaway ``.vntrader``."""
    (tmp_path / ".vntrader").mkdir(exist_ok=True)

    completed = subprocess.run(
        [sys.executable, "-c", REPORT + body],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr

    return [
        json.loads(line[len("REPORT ") :])
        for line in completed.stdout.splitlines()
        if line.startswith("REPORT ")
    ]


def file_sinks(report: dict) -> list[str]:
    """The handlers writing to a ``vt_*.log`` file, by sink name."""
    return [h["sink"] for h in report["handlers"] if "vt_" in h["sink"] and ".log" in h["sink"]]


# ---------------------------------------------------------------------------
# The trading log file survives the research import
# ---------------------------------------------------------------------------

def test_importing_alpha_after_the_trader_logger_keeps_the_file_sink(tmp_path: Path) -> None:
    reports = run_child(
        tmp_path,
        """
import vnpy.trader.logger
report("trader")
import vnpy.alpha
report("alpha")
""",
    )

    before, after = reports
    assert len(file_sinks(before)) == 1
    assert file_sinks(after) == file_sinks(before)


def test_importing_alpha_after_the_trader_logger_adds_no_second_stdout(tmp_path: Path) -> None:
    """A duplicated console is the failure mode of the naive fix.

    Deleting the ``remove()`` call and nothing else would leave the trader's
    stdout sink in place *and* add ours on top, so every line in the GUI process
    prints twice. The handler count is the whole assertion.
    """
    reports = run_child(
        tmp_path,
        """
import vnpy.trader.logger
report("trader")
import vnpy.alpha
report("alpha")
""",
    )

    before, after = reports
    assert len(after["handlers"]) == len(before["handlers"])
    assert [h["id"] for h in after["handlers"]] == [h["id"] for h in before["handlers"]]


def test_importing_alpha_after_the_trader_logger_preserves_level_and_colorize(
    tmp_path: Path,
) -> None:
    """Two settings went along with the file, and both are silent losses.

    Measured before the fix: the surviving handler's threshold dropped from 20
    (``SETTINGS["log.level"]``, INFO) to loguru's DEBUG default of 10, and
    ``colorize`` flipped from an auto-detected ``False`` to a forced ``True``
    that writes ANSI escapes into redirected output.
    """
    reports = run_child(
        tmp_path,
        """
import vnpy.trader.logger
report("trader")
import vnpy.alpha
report("alpha")
""",
    )

    before, after = reports
    assert {(h["level"], h["colorize"]) for h in after["handlers"]} == {
        (h["level"], h["colorize"]) for h in before["handlers"]
    }


def test_console_disabled_in_settings_is_not_re_enabled_by_alpha(tmp_path: Path) -> None:
    """The configuration came out exactly inverted, which is worse than lost.

    With ``"log.console": false`` the trader installs the file sink alone. The
    old sweep removed it and added a stdout sink — so an operator who asked for
    "file only" got "console only" instead, and the setting they wrote is the
    one that stopped being true.
    """
    (tmp_path / ".vntrader").mkdir(exist_ok=True)
    (tmp_path / ".vntrader" / "vt_setting.json").write_text(
        json.dumps({"log.console": False}), encoding="utf-8"
    )

    reports = run_child(
        tmp_path,
        """
import vnpy.trader.logger
report("trader")
import vnpy.alpha
report("alpha")
""",
    )

    before, after = reports
    assert len(before["handlers"]) == 1
    assert file_sinks(before)
    assert file_sinks(after) == file_sinks(before)
    assert not [h for h in after["handlers"] if h["sink"] == "<stdout>"]


# ---------------------------------------------------------------------------
# The path real entry points take
# ---------------------------------------------------------------------------

def test_importing_alphakit_rules_after_main_engine_keeps_the_file_sink(tmp_path: Path) -> None:
    """``run.py:35`` then ``run.py:40``; ``run_gui.py:48`` then ``run_gui.py:50``.

    Neither line mentions ``vnpy.alpha``. This is the spelling the bug actually
    shipped in, so it gets its own case even though the mechanism is the one
    above — a future ``vnpy_alphakit`` refactor that stops reaching
    ``vnpy.alpha`` would make this test stop testing anything, and it should
    then be reconsidered rather than deleted.
    """
    reports = run_child(
        tmp_path,
        """
import vnpy.trader.engine
report("main_engine")
import vnpy_alphakit.rules
report("alphakit_rules")
""",
    )

    before, after = reports
    assert len(file_sinks(before)) == 1
    assert file_sinks(after) == file_sinks(before)


def test_a_written_log_line_reaches_the_file_when_alpha_was_imported(tmp_path: Path) -> None:
    """The end-to-end fact, and the only one an operator would ever notice.

    A real ``MainEngine``, a real ``write_log``, and a look on disk. Before the
    fix this file was 0 bytes while the same line appeared on stdout, which is
    why the handler-table assertions above are necessary but not sufficient:
    they describe the mechanism, this describes the loss.
    """
    reports = run_child(
        tmp_path,
        """
import time
import vnpy.trader.engine
import vnpy_alphakit.rules
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine

main_engine = MainEngine(EventEngine())
main_engine.write_log("SINK-ISOLATION-MARKER", source="TEST")
time.sleep(1.0)
main_engine.close()
report("after_write")
""",
    )

    sinks = file_sinks(reports[0])
    assert len(sinks) == 1

    log_path = Path(sinks[0].strip("'"))
    assert "SINK-ISOLATION-MARKER" in log_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The orders that must keep behaving as they already do
# ---------------------------------------------------------------------------

def test_alpha_first_then_trader_still_ends_with_only_the_trader_handlers(
    tmp_path: Path,
) -> None:
    """``run_live_alpha.py:60`` then ``:64`` — unchanged, and deliberately so.

    ``vnpy.trader.logger`` keeps its wide ``logger.remove()``. Narrowing it too
    would leave our stdout sink alive alongside the trader's and double every
    console line, so this pins the sweep in place from the other side.
    """
    reports = run_child(
        tmp_path,
        """
import vnpy.alpha
report("alpha")
import vnpy.trader.logger
report("trader")
""",
    )

    alpha, trader = reports
    assert len(alpha["handlers"]) == 1
    assert not file_sinks(alpha)

    assert len(trader["handlers"]) == 2
    assert len(file_sinks(trader)) == 1
    assert not set(h["id"] for h in alpha["handlers"]) & set(h["id"] for h in trader["handlers"])


def test_alpha_alone_still_claims_a_stdout_sink(tmp_path: Path) -> None:
    """The standalone research case, which is why the sink exists at all.

    A notebook importing ``vnpy.alpha`` and nothing else must still get output,
    and must not get loguru's stderr default alongside it.
    """
    reports = run_child(
        tmp_path,
        """
import vnpy.alpha
report("alpha")
""",
    )

    (alpha,) = reports
    assert len(alpha["handlers"]) == 1
    assert alpha["handlers"][0]["sink"] == "<stdout>"


def test_importing_alpha_twice_does_not_stack_sinks(tmp_path: Path) -> None:
    """``logger.remove(0)`` raises the second time round; the module survives it.

    Re-importing is a no-op in one interpreter, so this calls the configuration
    helper directly — the point is that the ``ValueError`` path does not skip
    the occupancy check and leave a second handler behind.

    The module is fetched out of ``sys.modules`` rather than read off the
    package: ``vnpy/alpha/__init__.py`` does ``from .logger import logger``,
    which rebinds the attribute ``vnpy.alpha.logger`` from the submodule to the
    loguru object.
    """
    reports = run_child(
        tmp_path,
        """
import sys
import vnpy.alpha
report("first")
sys.modules["vnpy.alpha.logger"]._configure_default_sink()
report("second")
""",
    )

    first, second = reports
    assert len(first["handlers"]) == 1
    assert [h["id"] for h in second["handlers"]] == [h["id"] for h in first["handlers"]]
