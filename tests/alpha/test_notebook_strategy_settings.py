"""随包发布的 notebook 里的 setting 字面量，必须真能构造出策略。

为什么需要这一条：`examples/alpha_research/research_workflow_*.ipynb` 四份都写着
`setting = {"top_k": 30, "n_drop": 3, "hold_thresh": 3}`，而 `EquityDemoStrategy`
的参数名从上游起就叫 `min_days` —— 四份 notebook 里这一行【从来没有生效过】。

它能活这么久是两件事叠在一起：`AlphaStrategy.__init__` 上游写的是
`if hasattr(self, k): setattr(...)`，未知键静默丢弃；而 `min_days` 的类默认恰好
也是 3。想设的值与默认值撞在一起，于是「配置没生效」和「配置生效了」跑出来的结果
逐位相同 —— 没有任何观测能把两者分开。

本 fork 把那个循环改成未知键直接 raise 之后，四份 notebook 会在
`engine.add_strategy(...)` 那一格停下，报
`ValueError: 策略 EquityDemoStrategy 没有名为 'hold_thresh' 的参数`。
这条用例守的不是「参数名是不是 min_days」，而是**随包发布的示例与随包发布的代码
之间没有断裂** —— 下一次谁改了策略的参数名而忘了改 notebook，这里先红。

做法上刻意不 import nbformat（共享 venv 里没有，也不值得为一条用例装）：
ipynb 就是 JSON，抠出那一格的 `setting = {...}` 字面量，用 `ast.literal_eval`
求值（不 exec，示例文件是数据不是可信代码），再拿去真造一次策略。
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from vnpy.alpha.strategy.strategies.equity_demo_strategy import EquityDemoStrategy

# ---------------------------------------------------------------------------
# Notebook discovery
# ---------------------------------------------------------------------------

NOTEBOOK_DIR: Path = Path(__file__).resolve().parents[2] / "examples" / "alpha_research"

#: 只匹配整行的赋值。notebook 里这一格还有注释和 add_strategy 调用，
#: 不锚定行首会把注释里提到的字典也抓进来。
SETTING_PATTERN: re.Pattern[str] = re.compile(r"^setting = (\{.*\})$", re.MULTILINE)


class StubEngine:
    """回测引擎替身：构造期只被存进 `self.strategy_engine`，一次都不会被调用。"""

    short_rates: dict[str, float] = {}


def collect_settings(path: Path) -> list[dict]:
    """抠出一份 notebook 里所有 `setting = {...}` 的字面量。"""
    notebook: dict = json.loads(path.read_text(encoding="UTF-8"))

    settings: list[dict] = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue

        source: str = "".join(cell["source"])
        for match in SETTING_PATTERN.finditer(source):
            settings.append(ast.literal_eval(match.group(1)))

    return settings


def workflow_notebooks() -> list[Path]:
    return sorted(NOTEBOOK_DIR.glob("research_workflow_*.ipynb"))


# ---------------------------------------------------------------------------
# The notebooks themselves
# ---------------------------------------------------------------------------


def test_the_shipped_notebooks_are_actually_present() -> None:
    """先钉住样本量本身——glob 空了会让下面每一条都变成 0 次断言的绿灯。"""
    notebooks: list[Path] = workflow_notebooks()
    assert len(notebooks) >= 4, f"只找到 {[p.name for p in notebooks]}"


def test_every_notebook_setting_constructs_the_strategy_it_is_written_for() -> None:
    """四份 notebook 的 setting 字面量逐个真造一次策略。"""
    for path in workflow_notebooks():
        for setting in collect_settings(path):
            EquityDemoStrategy(StubEngine(), "notebook", ["700.SEHK"], setting)


def test_no_notebook_still_passes_the_qlib_style_hold_thresh_key() -> None:
    """点名钉住那个具体的键——上面那条会红，但不会说出红在哪个名字上。"""
    for path in workflow_notebooks():
        for setting in collect_settings(path):
            assert "hold_thresh" not in setting, (
                f"{path.name} 仍在传 hold_thresh；EquityDemoStrategy 的参数名是 min_days"
            )


def test_notebook_settings_only_use_names_the_strategy_declares() -> None:
    """键名必须是类上真实存在的属性，不能靠 __init__ 顺手 setattr 出来。"""
    for path in workflow_notebooks():
        for setting in collect_settings(path):
            for name in setting:
                assert hasattr(EquityDemoStrategy, name), (
                    f"{path.name} 的 {name!r} 不是 EquityDemoStrategy 的类属性"
                )


# ---------------------------------------------------------------------------
# The guard the notebooks depend on
# ---------------------------------------------------------------------------


def test_an_unknown_setting_key_is_refused_rather_than_dropped() -> None:
    """上游那条 `if hasattr` 的反面：未知键必须响，否则本文件全部失去意义。"""
    with pytest.raises(ValueError, match="hold_thresh"):
        EquityDemoStrategy(
            StubEngine(), "notebook", ["700.SEHK"], {"top_k": 30, "hold_thresh": 3}
        )


def test_the_coincidence_that_hid_this_for_so_long_is_recorded_as_a_number() -> None:
    """`min_days` 的类默认就是 3，而四份 notebook 想设的也是 3。

    这条不测行为，测的是那个巧合本身。哪天默认值改了，这里先红，提醒后来者
    「历史上这个缺陷之所以无法被观测，是因为这两个数相等」这句话已经过期。
    """
    assert EquityDemoStrategy.min_days == 3

    for path in workflow_notebooks():
        for setting in collect_settings(path):
            assert setting.get("min_days") == 3
