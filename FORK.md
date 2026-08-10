# Fork 说明

这是 [vnpy/vnpy](https://github.com/vnpy/vnpy) 的 fork（MIT），origin 为
`hexonal/vnpy`。整个工作区的 12 个仓都依赖它 —— 它定义 EventEngine /
BaseGateway / BaseDatabase / 全部数据对象，并内置 `vnpy.alpha` 多因子投研子系统。

## 为什么需要这份台账

配 `upstream` 远端的仓只有两个（另一个是 `Kronos`，在依赖图外），而在这份文件
之前，**只有 `vnpy_ctastrategy` 有改动清单**。vnpy 领先上游 13 个提交（本轮改动
之外），而改动全部散落在 commit message 里 —— 下次同步上游时没人知道哪些差异是
我们的、为什么。
`CHANGELOG.md` 是上游的发版记录，不是 fork 台账。

## 本仓的分线：修 bug 原地改，加能力放独立文件

`vnpy_ctastrategy/FORK.md` 的原则原文是「改动尽量克制、集中、可解释……**新增
能力**优先放进独立文件，而不是散落着改上游函数体」。**它的限定语是【新增能力】**，
这一点必须说清楚，否则后来者会以为所有改动都该躲进新文件：

* **修上游的 bug → 原地改函数体 + 一段说明失效机理的长散文。** 这是本仓既有的
  做法（前 13 个提交里，`vnpy/` 包内新增文件数为 **0**），也是
  `vnpy_ctastrategy` 自己第 4、5 条的做法（它直接改了上游的 `backtesting.py`
  与 `engine.py`，并写明「仅 4 处最小接入」）。理由不是偷懒：本轮三处缺陷的
  计算全部发生在函数体内部的局部变量上（`close_0` 是 per-symbol 循环里的局部
  标量，函数一返回它和原始 vwap 都不存在了），外部包装能检查输出、改不了计算。
  工作区唯一的包装先例 `vnpy_alphakit/bridge.py` 的 `load_bar_df_strict` 恰好画
  出了这个模式的天花板 —— 它做的是拿返回的 vt_symbol 集合比对请求列表、把
  fail-open 关掉。
* **新增上游没有的能力 → 独立文件 + 最少的接入点。** 本轮的
  `vnpy/alpha/semantics.py` + `lab.py` 4 处接入就是这个形态。

**本轮不加开关。** 三处都是纯粹算错，不存在值得保留的旧行为。工作区已经有一条
现成教训：`VNPY_BAR_LABEL_NORMALIZE` 默认关闭的实际效果是「两种口径长期并存、
DEDUP 键发现不了」。一个默认关闭的正确性开关，只会给产物血统再加一个没人记录的
维度。

语义 v2 那一轮又用同一条理由否掉了一次「先做成开关、等真有停牌数据再开」的提案，
并补上两点：开关会让**戳不再决定语义**（你得把开关状态也记进产物，那就是又一个
维度），而且它把**已知算错的算术留在默认路径上** —— 第一个建港股小票面板的人
默认拿到错的答案，而开关的存在正好变成「这可以接受」的借口。

## 与上游的关系

- 远端：`origin` = `https://github.com/hexonal/vnpy.git`，
  `upstream` = `https://github.com/vnpy/vnpy.git`。
- **同步基点**：`1b784949`（2026-05-17「[Add] vnpy.alpha related document」，
  上游 v4.4.0 之后的文档提交）。
- 同步方式：`git fetch upstream && git merge upstream/master`。
- 落后 `upstream/master` **1** 个提交：`fa5206fe`（2026-08-06「[Mod] update
  README.md」，`git diff --name-status` 只有 `M README.md`，零代码）。
- 本地 `upstream/*` 远程跟踪引用在 2026-08-06 的审计里被 fetch 快进过
  （`upstream/master` 1b784949 → fa5206fe、`upstream/alpha` d79c270e → e8d44b95、
  `upstream/dev` 4240fee6 → 0fdc8c7f，全部 fast-forward）。所以复算「落后几个」
  会与更早的记载不同 —— 那不是记载错了，是引用更新了。

验证命令：

```bash
cd vnpy
git rev-list --left-right --count upstream/master...master     # 落后 1 / 领先 13 + 本轮
git merge-base master upstream/master                          # 1b784949...
```

## 既有 13 个提交（本轮之前）

`git diff --name-status upstream/master..master` 共 20 条路径，其中 **A（新增）
只有 1 条**：`tests/test_array_manager.py`；`vnpy/` 包内 A 的条数是 **0**。改过
上游函数体的几处：

| 提交 | 改了什么 | 上游文件 |
|---|---|---|
| `c95490b0` 2026-07-23 | quant-correctness 审计，一次改 11 个文件（+299/−73）：`ta_rsi`/`ta_atr` 跨 symbol 边界污染、`lab.py` 停牌检测重写、`template.py` 对齐 guard、`ts_function.py` 三处 `maintain_order="left"`、`lasso_model.py` 的 fit 取数、`utility.py` 的 BarGenerator | `alpha/dataset/{math_function,processor,ta_function,template,ts_function}.py`、`alpha/lab.py`、`alpha/model/models/lasso_model.py`、`alpha/strategy/{backtesting,template}.py`、`alpha/strategy/strategies/equity_demo_strategy.py`、`trader/utility.py` |
| `c674c164` / `a4466dcf` / `8de7b7b0` 2026-07-23~24 | 图表：抗锯齿、跌用绿色（对齐港股/内地券商 App）、光标图例中文化 | `chart/base.py`、`chart/item.py` |
| `71acc69d` 2026-07-24 | ArrayManager 新增 `linearreg` / `tsf` / `linearreg_slope`；**fork 唯一新增的文件** `tests/test_array_manager.py` | `trader/utility.py` |
| `7b650cac` / `ab572456` 2026-07-24 | mypy `python_version` 提到 3.13 并清理类型错误；恢复 `exposedRect` 的 type-ignore（CI 的 Windows PySide6 stubs 需要） | `pyproject.toml`、`chart/item.py` |
| `c24f6313` 2026-07-25 | `default_setting` 可能装 list —— ConnectDialog 一直把它渲染成下拉框 | `trader/gateway.py` |
| `cdf2bc7b` 2026-07-26 | 已终态的委托不再被加回 `active_orderids` | `trader/engine.py` |
| `4f157e7c` / `542953b5` / `07673e60` 2026-07-27 | `get_default_setting` 返回类型对齐 `BaseGateway`；同步 alpha101 测试表达式并让 CI 真的跑测试；action 升 node24 | `trader/engine.py`、`tests/test_alpha101.py`、`.github/workflows/pythonapp.yml` |
| `cc7fb359` 2026-08-02 | `.gitignore` 忽略 `.mcp.json`（那份文件里存着明文 Bearer token） | `.gitignore` |

## 本轮（第 14 个提交起）：特征语义 v1

六条改动，语义版本从 v0 推进到 **v1**。前两条是修上游的算错，后四条是让这次算错
的修复**无法被静默忽略**（闸、版本号、可复现的训练循环、以及一条对得上代码的依赖
声明）。

### 1. `lab.py` — vwap 与价格列同除一个 `close_0`

**改哪里**：`load_bar_df` 的归一化 `with_columns`（`vnpy/alpha/lab.py:256`），
在 open/high/low/close 之后补第五列 `(pl.col("vwap") / close_0).alias("vwap")`。

**上游原行为**：`vwap = turnover / volume` 在 `:222-224` 按**原始价格单位**算出，
`:251-257` 的归一化只点名四个价格列，vwap 留在原尺度。于是 Alpha158 的

    vwap_0 = vwap / close = (raw_vwap / raw_close) × close_0

是一个**每票常数**乘上一个贴着 1.0 的比值 —— 它是股票 ID，不是因子。

**为什么不走独立文件**：`close_0` 是 per-symbol 循环内的局部标量，函数返回时它
和原始 vwap 都已不存在，外部包装反推不出来。也不修在 `alpha_158.py`：那句
`vwap / close` 表达式本身对称无误，而 `alpha_101.py` 有 43 行引用 vwap，
`lab.py` 是唯一的收口点。

**位置是硬约束**：必须在 `:232` 取到 `close_0` 之后、`:262` 的停牌 NaN 掩码之前。
`close_0` 读的是**未归一化的** close，提前一行归一它就变成 1.0；晚于掩码则 vwap
已被写成 NaN。`numeric_columns = df.columns[1:]` 已含 vwap，掩码那步不用动。

**哪些数会变**：Alpha158 的 `vwap_0` 一列（其余 157 列逐位不动），Alpha101 的
30 条 vwap 特征里 22 条。审计实测：十只港股修前各票值域互不重叠
（1810.SEHK [10.62, 11.91]、388.SEHK [257.74, 295.30]、700.SEHK [303.71, 330.59]），
修后塌进同一个带 [0.963244, 1.418407]，票间/票内 std 比从 26.81 降到 1.12，
rankIC 从 −0.0397 翻成 **+0.0454** —— 它修完是一个真因子，**不该被 drop**。

**为什么不加运行时数据断言**：调研建议过「vwap 必须落在 low..high 之间」。实测
它会 fail-closed 在合法数据上 —— 港股 turnover 与 QFQ 复权后的 OHLC 不同口径，
`hk_bluechip_10` 上 **5014 / 7350 = 68.22%** 的合法行会触发。一个在 2/3 合法行上
报警的闸，一周内一定会被关掉。可见性交给下面第 3、4 条。

**一条连带后果，刻意不修**：`volume` / `turnover` 留在原始单位，所以返回的 frame 里
`vwap * volume` 不再等于 `turnover` —— 实测差**恰好 1/close_0**。这不是新引入的
不一致：`close` 自上游起就是归一化的，因此**早就**对着原始 turnover 差同一个因子
（同一份 frame 上实测 `close*volume/turnover = 1/(0.996*close_0)`，**修前修后同值**）。
vwap 是价格，它现在跟着价格走，也就继承价格本来的处境。把 turnover 一起归一能让
恒等式回来，但 turnover 是金额不是价格 —— 上游有意把量的一族留在原始单位、让
Alpha158 用自归一的比值去消化它（`vma_w = ts_mean(volume,w)/volume`），而且
**Alpha158 与 Alpha101 没有一条表达式读 turnover**（已 grep 确认）。多改一次语义，
换不到任何东西。

**验证**：

```bash
cd vnpy && ../vnpy/.venv/bin/python -m pytest tests/alpha/test_load_bar_df_vwap.py -q   # 4 passed
```

变异验证：摘掉那第五列 → **3 例转红**（同一根 bar 用两个查询起点得到
772.896 与 812.736）。

### 2. `ts_function.py` — 五个有损滚动算子的入参转 Float64

**改哪里**：`ts_rank`(:104)、`ts_mean`(:125)、`ts_std`(:136)、`ts_quantile`(:175)、
`ts_decay_linear`(:359) 在 `rolling_map` 前加 `.cast(pl.Float64)`。
`ts_argmax` / `ts_argmin` / `ts_product` **不动**（整数入参下它们的返回值按定义
就是整数）。模块 docstring 从一行扩成完整的失效机理说明。

**上游原行为**：polars 把 `rolling_map` 回调的返回值**转回输入列的 dtype**。
本机实测（polars 1.43.0，输入 `[1,0,1,1,0,1,0,0]`、window=5）：

| 算子 | Int32 输入 | Float64 输入 |
|---|---|---|
| `ts_mean` | `[1,0,0,0,0,0,0,0]` | `[1.0, 0.5, 0.667, 0.75, 0.6, 0.6, 0.6, 0.4]` |
| `ts_std` | 全 0 | `[0, 0.5, 0.4714, 0.433, 0.4899, …]` |
| `ts_rank` | 全 0 | `[…, 0.3, 0.8, 0.3, 0.4]` |
| `ts_quantile`(q=0.3, [1..5]) | `2` | `2.2` |
| `ts_decay_linear` | 全 0 | `[0.6667, 0.5333, 0.7333, 0.5333]` |

**两条最直觉的修法都是死路**（都实测过）：`Expr.rolling_map()` 在 1.43.0 的签名
里**没有 `return_dtype`**（传了 `TypeError`）；去掉 cast 让 Boolean 直通则
`InvalidOperationError: 'rolling_map' operation not supported for dtype 'bool'`。
`utility.py:39` 那个 `.cast(pl.Int32)` 是被 polars 逼出来的。

**为什么修在算子而不是 `utility.py:39` 的 `_comparison_series`**（这是本轮唯一
有分歧的决定，明知它会 +1 个 merge 冲突文件仍然选它）：

1. **改 utility 是不完整的修法。** 实测
   `pl.when(...).then(pl.lit(1)).otherwise(pl.lit(0))` 的 dtype 也是 **Int32** ——
   `quesval` / `quesval2` / `sign` 三条路根本不经过 `_comparison_series`，
   Alpha101 的 `alpha92` 修不掉。整数来源是一份要维护的枚举，而这份枚举第一遍就
   已经数漏了。
2. **改 utility 等于单方面推翻上游决定。** `5881a61b`（2025-12-24「DataProxy的
   所有比较运算，直接返回pl.Int32」）是有意为之 —— 同一笔提交删掉了
   `math_function.cast_to_int` 并改了 `alpha_101.py` 八处，目的是让比较结果能
   直接参与算术。退回 Bool 会打断 alpha_101；改成 Float64 则要连带改上游测试
   `tests/alpha/test_dataproxy.py` 的 13 处 `assert_int_data`，fork 足迹从源码扩
   到上游测试。
3. **数学契约在算子里。** 「均值是实数」对任何输入都成立，包括还不存在的输入；
   「哪些生产者会产出整数」需要有人不断补全。

**哪些数会变**：本机实测（五只票 × 260 天的合成面板，逐列
`np.allclose(rtol=1e-9, atol=1e-12, equal_nan=True)`）：Alpha158 的 158 列里
**15 列变化，全是 `cntd_{5,10,20,30,60}` / `cntn_{…}` / `cntp_{…}`，143 列
一位不动**。连带修好 Alpha101 的 `alpha92`。精确语义比「截成 0/1」更准：向零取整
作用在 mean ∈ [0,1] 上，只有窗口内全为 1 才留下 1 —— 所以 `cntp_w` 退化成了
【过去 w 根全部上涨】的指示器。

⚠️ **「15」是有前提的，别把它当成这条改动的性质。** 同一份面板把 `volume` 换成
Int64 重测一遍，变化的是 **25 列** —— 多出来的十列是 `vma_5..60` 与 `vstd_5..60`
（`ts_mean(volume,w)/volume`、`ts_std(volume,w)/volume`，同样被这五个算子截断）。
`load_bar_df` 永远吐 Float64（`:262` 的停牌 NaN 掩码把整数列提升掉了），所以走 lab
这条路真的只有 15 列；但 `AlphaDataset` 收任何面板，别的来源不保证。上一版这里写的
是「恰好 15 列」，那是把一个条件结论固化成了定论。

**验证**：

```bash
cd vnpy && ../vnpy/.venv/bin/python -m pytest tests/alpha/test_ts_function_dtype.py -q  # 11 passed
```

变异验证：摘掉 `ts_mean` 一处的 cast → **5 例转红**；五处全摘 → **10 例转红**。

### 3. `semantics.py`（新文件）+ `lab.py` 四处接入 — 产物硬闸

**新增** `vnpy/alpha/semantics.py`（343 行）：`FEATURE_SEMANTICS_VERSION = 1`、
`SEMANTICS_HISTORY`（逐版写明改了什么、哪些既有产物因此作废）、
`stamp` / `assert_compatible` / `parquet_metadata` / `assert_parquet_compatible`、
以及 `describe_feature_health` 与它的 frozen 值对象 `FeatureHealth`。
异常基类 `AlphaSemanticsError`。

**接入** `lab.py` 六行：`save_dataset`(:427) / `save_model`(:462) 在
`pickle.dump` 前 `stamp(obj)`；`load_dataset`(:441) / `load_model`(:476) 在
`pickle.load` 之后 `assert_compatible(obj, file_path)`；`save_signal`(:501) 用
`write_parquet(metadata=...)` 盖戳，`load_signal`(:510) 校验。
**不动** missing-file 那条 `logger.error + return None` 分支 —— 调用方 branch 在
None 上，把「还没建」变成异常是另一个不相关的行为改变。

**这一处才真正适用「新增能力放独立文件」那条纪律**：它不是修 bug，是加一个上游
没有的闸。放独立文件 = 未来 merge 零冲突面，且这个文件不在 `upstream/alpha` 的
射程内。

**为什么闸必须 raise 而不是 warn**：`load_dataset` 现在的形态是 missing →
`logger.error` + 返回 None，是调用方可以忽略的 fail-open；而本工作区最常见的故障
模式就是「不报错、只是结果错」。审计量化过老模型喂新特征的后果：三棵树的根分裂
全在 `vwap_0 <= 43.781305`，修复后所有样本都 ≈ 1.0，**每一个分裂都倒向同一边**；
预测 max abs diff **0.4147**，而已发布 signal 自身 std 只有 **0.0778**（偏差是
信号量级的 5.3 倍），corr(旧,新) = 0.2246 —— 而 `booster.predict` 的 158 列 shape
检查全过，**不抛任何异常**。

**为什么戳是对象属性而不是 pickle 信封**：信封会改变盘上格式，让任何直接
`pickle.load` 的第三方代码拿到 dict 而不是对象。属性方案同样 fail-closed（老 pkl
取不到属性 → raise），盘上仍是一个裸对象。`AlphaDataset` / `AlphaModel` 都没有
`__slots__`，实测可设。

**为什么 signal 必须一起盖戳**：三种产物里它是唯一从文件本身**完全检测不出新旧**
的（只有 datetime / vt_symbol / signal 三列）。dataset pkl 能从
`df.group_by("vt_symbol").agg((vwap/close).median())` 看出各票的 close_0；model pkl
能从 `booster.trees_to_dataframe()` 里 `vwap_0` 的阈值看出来（旧口径的
43.781305 / 75.952701 / 125.535739 全部落在新值域 [0.963244, 1.418407] 之外）；
signal 什么都看不出来。

**为什么体检函数返回数据而不是直接 raise**：一个 turnover 由 `close × volume`
合成的 lab 上，修完之后 `vwap_0` **精确恒等于 1.0** —— 那是合法的数据后果，硬
raise 会误伤。把它变成一个必须记进 manifest 的数，比拦下来更有用。

**🔴 闸证明的是「谁存的」，不是「谁算的」。** `stamp` 在 `save_*` 里无条件执行，
所以一个 v0 口径算出来的对象只要经过 `save_dataset` 就会被盖上 v1 戳，闸随后放行
—— 实测确认，不是担心。现实中踩到它的路径只有一条：用裸 `pickle.load`（绕过闸）
读出老产物、再经 `AlphaLab` 写回去。**所以迁移只能搬文件，不能借 `AlphaLab` 重写**
（下面「迁移」那段的改名归档就是为此）。彻底堵上要把盖戳挪进
`AlphaDataset.prepare_data`（热路径），而且仍挡不住手工拼装的产物 —— 本轮不做，
代价写在这里，并由 `test_saving_an_unstamped_artifact_mints_a_current_stamp_on_it`
把这个漏洞钉成一条会说话的用例：它哪天转红，说明有人把盖戳挪走了，这段文字就过期了。

**这一步落地的瞬间，`vnpy_alphakit/lab/hk_bluechip_10/` 的三份产物开始 raise。**
这是预期行为，不是事故。处置方式是**改名归档**（加 `.pre-semantics-1` 后缀），
不要删、不要就地覆盖 —— `run_example.py` 无条件写同名文件，跑一次老产物就永久
消失，而它们是「修复前后确实变了」的唯一证据。`daily/*.parquet` 不动（存的是
原始 bar，vwap 是每次现算的）。

**验证**：

```bash
cd vnpy && ../vnpy/.venv/bin/python -m pytest tests/alpha/test_semantics.py -q          # 23 passed
```

变异验证：`assert_compatible` 的两处 raise 改成 return → **5 例转红**；**六个**接入点
逐个摘掉 → 各 **1 例转红**（`load_dataset` / `load_model` / `load_signal` /
`save_dataset` / `save_model` / `save_signal` 各有专属用例）。

⚠️ `save_model` 那条用例是复核阶段补的：原来只有 dataset 与 signal 有 round-trip，
摘掉 `save_model` 里的 `stamp(model)` 时 **21 例全绿**。它的失败形态不是静默算错而是
**假阳性拒绝** —— 模型存得进去，下一次 `load_model` 才 raise，故障点离原因隔着一整轮
训练。

### 4. `vnpy/__init__.py` — `__version__` 加 PEP 440 local 段

`"4.4.0"` → `"4.4.0+hexonal.1"`（`vnpy/__init__.py:34`）。

这是唯一能让既有产物停止「静默可比」的自动钩子：
`vnpy_alphakit/provenance.py` 走 `sys.modules["vnpy"].__version__` 把它写进每份
`runs/*.json`，而 fork 从没动过版本号 —— 不改它，修复前后两份 manifest **逐字
相同**（现存那份记的是 `"vnpy": "4.4.0"`；另一个字段 `data_fingerprint` 只哈希
`{symbols, row_count, span}`，实测值 `a950ce40a4bbc27b` 修复前后不变）。

风险逐条实测排除：`packaging.Version` 解析通过（base 4.4.0 / local hexonal.1、
`is_prerelease` False）、`import vnpy` 正常、`pyproject.toml:72-74` 的 hatch 版本
正则仍匹配、`uv build` 产出
`vnpy-4.4.0+hexonal.1{.tar.gz,-py3-none-any.whl}`，CI 只跑 `uv build`
**没有 publish / twine 步骤**（本地版本段不能上 PyPI，但这里不发布）。另两个消费
点 `trader/ui/widget.py:1202`（关于对话框）与 `mainwindow.py:52`（窗口标题）都只
显示，全工作区无一处做版本比较 —— GUI 会显示 `4.4.0+hexonal.1`，这正是想要的
效果：它同时告诉交易员这不是上游 4.4.0。

### 5. `mlp_model.py` — 训练循环三处 + 特征重要度

**改哪里**：`vnpy/alpha/model/models/mlp_model.py`，四处。

1. **`n_epochs` → `n_steps`**（行为一字不改，只是名字诚实），默认 300 → 3000。
   `_train_step` 每次迭代只用 `np.random.choice` 有放回抽**一个** batch，所以它
   从来就是梯度步数：同一个 300 在 12 万行训练集上约 5 个名义 epoch（欠拟合）、
   在 4 千行上约 150 个（过拟合）。
2. **`early_stop_rounds` → `early_stop_evals`** + 构造期可达性闸门。计数器只在
   评估时 +1，而每 `eval_steps` 步才评估一次 —— 老默认值下 300 步只发生 15 次
   评估，对着 50 的耐心值，**早停在数学上不可能触发**。闸门在
   `n_evals - 1 < early_stop_evals` 时 raise 并给出两条出路。默认值 300→3000 与
   闸门是**原子的**，不能拆：不抬默认值，闸门会让默认构造直接 raise。
3. **早停触发时最优权重不会被还原**：`_evaluate_step` 在函数体内重建
   `best_params = None`，于是每次不改进都把调用方持有的 checkpoint 打回 None，
   而早停的定义正是「连续 N 次不改进」。改成把 `best_params` 也当入参传进去、
   不改进时原样返回，`if best_params:` 改成 `is not None`（空 state_dict 是
   falsy）。**这个缺陷不以早停为前提** —— 只要最后一次评估不是最优的那次就丢
   权重。
4. **`detail()` 的特征重要度用 `torch.randn(1000, input_size)` 随机数据做扰动**，
   与真实分布无关、内部 randn 没设种子（同一模型算三次排名都不同）、指标是
   `std(Δpred)`。废弃之，`detail()` 返回 None（与同目录 LgbModel / LassoModel
   一致），新增 `permutation_importance(dataset, segment, seed)` 在真实数据上逐列
   打乱、指标改 `mean(|Δpred|)`。
   **`std` 究竟差在哪，复核阶段才量清楚**：置换不改变边缘分布，出来的 Δ 是近似中心
   化的，所以在寻常面板上 `mean(|Δ|)` 与 `std(Δ)` 的排名 Spearman 是 **0.94~1.00**
   —— 两者几乎无差别。**分野在稀有事件列**：一个只在 2% 行上取 1 的特征，置换只动
   ~4% 的预测、其余为零，实测它的 `std/mean` 比是 **5.13**，而稠密列是 **1.25**
   （三个种子上稳定到小数点后两位），即 `std` 把稀有列**相对抬高 4.1 倍**。
   `mean(|Δ|)` 回答的是「毁掉这一列，预测平均动多少」，才是决策相关的量。

**为什么必须原地改**：pickle 按全限定名 `vnpy.alpha.model.models.mlp_model.MlpModel`
存类，搬进独立文件会让所有 MlpModel pkl 永久不可读。今天代价为零（全工作区
**零个** MlpModel pkl），但那会挖一个不可逆的坑。改名的窗口就是现在。

**docstring 体裁例外**：本文件沿用 numpydoc（`Parameters` / `----------`，
在 `vnpy/alpha` 下出现 19 次），不要按工作区的全局禁令去删。

**故意做成响的破坏**：`examples/alpha_research/research_workflow_mlp.ipynb`
cell 20 的 `"n_epochs": 8000` 会 `TypeError`，已同步改成 `n_steps`；cell 22 的
`model.detail()` 是本补丁里唯一一处【静默】破坏（从显示一张表变成什么也不显示），
已补一个新 cell 调 `model.permutation_importance(dataset, Segment.VALID)`。

**验证**：

```bash
cd vnpy && ../vnpy/.venv/bin/python -m pytest tests/alpha/test_mlp_model.py -q          # 17 passed
```

变异验证：把 `best_params = None` 放回 `_evaluate_step` → **3 例转红**；摘掉可达性
闸门 → **1 例转红**；`permutation_importance` 换回带种子的 `torch.randn` →
**2 例转红**；指标换回 `std(Δ)` → **1 例转红**；`is not None` 改回 `if best_params:`
→ **1 例转红**。

⚠️ **这 17 例里有 4 例证明力弱，别把它们当成「缺陷已修」的证据。** 复核做过一次
决定性对照：把上游 HEAD 的 `mlp_model.py` 原样取出、**只机械改两个参数名**（让测试
能 import），17 例里 9 例转红、**4 例仍绿**（`test_n_steps_runs_exactly_that_many_
gradient_updates`、`test_n_steps_ignores_training_set_size_so_it_cannot_mean_epochs`、
`test_constructor_accepts_the_smallest_reachable_combination`、
`test_early_stopping_fires_after_that_many_non_improving_evaluations`）。
原因不是测试写坏了 —— 上面第 1 条本来就**不是行为缺陷**，上游循环写的就是
`for step in range(1, n_epochs + 1)`、`_train_step` 本来就一步一个 batch，错的只有
名字和默认值。这 4 例是不变量锁定，不是回归网：把循环改成 epoch 解释
（`n_steps * (train_samples // batch_size)`）它们会红，那正是老名字招来的错误。
写提交正文时的诚实说法是「9 例回归 + 4 例不变量锁定」，不是「13 例锁住缺陷③」。

复核阶段补的 4 例（`ShapedDataset` 那一族与两条 restore 用例）填的是三个空测试：
原来的 `FakeDataset` 每一列都来自 `rng.standard_normal` —— 与 `torch.randn`
**同分布**，所以它在构造上就无法区分真实数据与合成数据，把
`permutation_importance` 换成带种子的 randn 时 **13 例全绿**。这和
`tests/alpha/test_load_bar_df_vwap.py` 自己 docstring 里点名的陷阱
（`test_alpha101.py` 的 fixture 造 `vwap=(high+low+close)/3`，因此永远看不见 vwap
缺陷）是同一个坑，隔一个文件又踩了一次。**替身的分布就是测试的上限。**

### 6. `pyproject.toml` — alpha extra 的 polars 下限 1.26 → 1.30

**改哪里**：`[project.optional-dependencies].alpha` 的 `"polars>=1.26.0"` →
`"polars>=1.30.0"`。

**为什么**：第 3 条给 signal parquet 盖戳用了
`DataFrame.write_parquet(metadata=...)` 与 `pl.read_parquet_metadata`，两个 API
**都是 1.30.0 才有的**。这不是查文档得来的，是把 1.26.0 / 1.27.0 / 1.28.0 /
1.29.0 / 1.30.0 五个 wheel 逐个下载解包读源码确认的：前四个版本
`polars/io/parquet/functions.py` 里**没有** `read_parquet_metadata`，
`write_parquet` 的参数表从 `compression` 到 `retries` **没有** `metadata`，而且
它的形参是 keyword-only、不吃 `**kwargs`。

**不改会怎样**：今天看不出来 —— CI 与本机都解析到最新版（本机 1.43.0）。它只在
lockfile、constraints、或者有人照着下限复现时才发作，落点是
`AlphaLab.save_signal` 的 `TypeError: write_parquet() got an unexpected keyword
argument 'metadata'`，而唯一的生产消费点是 `vnpy_app/run_live_alpha.py:229` 的
`load_signal` —— 实盘信号入口。**声明与代码对不上就是债，哪怕今天不响。**

**验证**：

```bash
cd vnpy && ../vnpy/.venv/bin/python -c \
  "import polars as pl, inspect; \
   print('metadata' in inspect.signature(pl.DataFrame.write_parquet).parameters, \
         hasattr(pl, 'read_parquet_metadata'))"      # True True
```

## Alpha101 的三个算子 —— **这三条本身不构成推版本的理由**

上一轮的「已知没做的事」里挂着「Alpha101 仍不可用」。这一轮把它清掉。三条改动
全部落在 **只有 Alpha101 用得到** 的算子上，Alpha158 逐列对拍确认不受影响，所以
**这三条自己没有推 `FEATURE_SEMANTICS_VERSION` 的理由**，写作当时它还是 1。

⚠️ **这句话只限定在它自己的范围内，不是对那个常量终值的断言。** 紧接着的下一节
（停牌 NaN 护栏）把戳推到了 **2**，理由是它自己的。本节里所有「仍是 v1」「保持 1」
的说法，都请按「**Alpha101 这三条没有推动它**」来读，不要读成「今天的戳是 1」。

**为什么这三条可以不推版本**（这是这一轮唯一需要论证的决定）：`alpha_158.py` 的
82 条表达式对 `cs_*`、`pow1` / `pow2`、`quesval` / `quesval2`、`sign`、
`less` / `greater` 的引用数**全是 0**（只用 `ts_*`），而本轮改的三个函数分别在
`cs_function.py` 与 `math_function.py`，`ts_function.py` 一行没动。光有静态计数
不够，所以做了逐列对拍：同一份 `hk_bluechip_10`、同一个区间，改前改后各算一遍
Alpha158，**167 列里 164 列逐位相同，另外 3 列（`beta_60` / `rsqr_60` /
`resi_60`）差在 1e-13 量级**。

**这里有一条必须说出口的缝**：Alpha101 的值确实变了（十票 lab 上 82 列里 **56 列
逐位不同**），而戳还是 1 —— 所以「戳 = 1」这件事从今天起不再唯一确定 Alpha101 的
口径。之所以判定这不构成风险，是查过的，不是想当然：**全工作区不存在任何盖了 v1
戳的产物**。lab 里只有三个 `*.pre-semantics-1.*`（v0 口径、已改名搁置、闸本来就
拒绝），`protocols/us_ai_basket_2026-08-07/PROTOCOL.toml` 里 Alpha101 是以
`alpha101_unavailable` 记录在案的、协议一列都没用它。**代价是**：如果在推 v2
之前有人产出了 Alpha101 的 v1 产物，那份产物会被闸放行而实际口径已经不同 ——
届时正确的做法是推 v2，而不是给这条记录打补丁。

✅ **这条缝已经在下一节合上了，而且是按上面写的那条路合的**：戳推到 2 之后，
Alpha101 的新口径与 v2 一一对应，「戳 = 1」这个状态从此不会再被任何新产物盖上。
留着这段是因为**中间那个窗口真实存在过**：本轮三条改动落地到戳推到 2 之间，任何
盖 v1 戳的 Alpha101 产物都是不可信的 —— 而实测那个窗口里全工作区一份 v1 产物都
没有。

⚠️ 那 3 列**不是本轮改出来的**：同一份代码连跑两遍，`rsqr_60` 自己就差
4.3e-14（最大相对误差 3.9e-13）。`ts_slope` / `ts_rsquare` / `ts_resi` 用
`pl.sum_horizontal` 把 60 个 shift 列横向求和，polars 的线程池不保证求和次序，
所以窗口 60 的这三列**本来就不是逐位可复现的**。这条对以后有用：验证「重算是否
等价」时对这三列不能用精确相等，得用 `rtol=1e-9`。

### 1. `cs_function.py` — `cs_rank` 返分位而不是序号

**改哪里**：`cs_rank` 的整个函数体，外加把一行的模块 docstring 扩成完整的失效
机理说明。

**上游原行为**：`pl.col("data").rank().over("datetime")` —— 1..N 的序号。

**原论文怎么定义的**（去查了，不是想当然）：Kakushadze (2016) 附录 A.1 的原文
只有一句 **`rank(x) = cross-sectional rank`**，**没有**写分母。所以定义只能从
消费它的公式里反推，而公式把它钉死了三次：Alpha#1 结尾是 `rank(...) - 0.5`、
Alpha#27 判 `0.5 < rank(...)`、Alpha#19 与 Alpha#39 算 `1 + rank(...)`。这三个
常数对着一个上限等于宇宙大小的序号毫无意义。Alpha#85 / Alpha#94 用第四种方式
钉死它：`rank(...)^rank(...)` —— 界在 (0,1] 是个普通数，序号则是 `N**N`。

**实测代价**：

| 现象 | 修前 | 修后 |
|---|---|---|
| `alpha85` 峰值（50 票合成面板） | **8.88e+84** = `50**50` | 1.0 |
| `alpha78` 峰值（同上） | 1.26e+84 | 1.0 |
| `alpha85` 峰值（10 票 `hk_bluechip_10`） | 1e+10 = `10**10` | 1.0 |
| `alpha86`（10 票 lab，7350 行） | 恒为 **0**（DEGENERATE） | 2 个取值，flat 4.8% |
| `alpha1` 值域 | [-0.5, 9.5] | (-0.5, 0.5] |

**所以「pow2 溢出到 1e84」不是 `pow2` 的缺陷**。`8.88e+84` 就是 `50**50`，一位
不差 —— `pow2` 只是老老实实算了喂给它的数。修 `cs_rank` 之后四条 pow2 特征
（alpha78/84/85/94）在真实 lab 上的峰值全部落回 1.0。

**顺带修掉的第二半**：polars 把 NaN 排在所有实数之上，所以旧的 `rank()` 会把
停牌日和滚动窗口的暖机 NaN 排成截面**第一名** —— 那不是缺失值，是凭空造出来的
极值。现在非有限值先掩成 null 不参与排名，分母也只数真有值的票，于是「当天 3 只
有值」排成 1/3、2/3、1.0，而不是被 2 只 NaN 稀释成 1/5、2/5、3/5。

⚠️ **这一半会让若干列的 NaN 占比大幅上升，那是修对了不是修坏了。** 十票 lab 上
`alpha13` 12.2% → 75.0%、`alpha15` 13.3% → 94.5%、`alpha16` 11.7% → 75.2%、
`alpha50` 2.8% → 65.4%。这些列都是 `cs_rank(ts_corr(cs_rank(x), cs_rank(y), w))`
的形状：内层 `ts_corr` 在秩序列恒定的窗口上无定义（十票宇宙里成交量排名极稳，
这种窗口很多），旧实现把这些 NaN 洗成了「截面第一名」。**换句话说这四列此前有
三分之二到九成的值是伪造的。**

**`.cast(pl.Float64)` 是必需的**：`cs_rank` 经常收到 Int32 —— 每个 `DataProxy`
比较都刻意转 Int32，`quesval` / `quesval2` / `sign` 的分支是 `pl.lit(1)` /
`pl.lit(0)` 也是 Int32。polars 的 `is_not_nan` 对整数列直接
`InvalidOperationError`。

### 2. `math_function.py` — `quesval2` 的比较方向反了

**改哪里**：把 `threshold.df.join(feature1.df, suffix="_cond")` 改成先
`rename({"data": "data_cond"})` 再 join。

**机理**：polars 的 `suffix` 加在 **右**表上。写成
`threshold.df.join(feature1.df, suffix="_cond")`，`data_cond` 里装的是
`feature1`、裸 `data` 里装的是 `threshold`，于是
`pl.col("data_cond") < pl.col("data")` 读出来是 `feature1 < threshold` ——
**与它自己的 docstring 和原论文都相反**。实测：`quesval2(0, 1, 1, 0)` 答 0。

**受影响范围**：走 `quesval2` 的 11 条表达式（alpha7 / 21 / 23 / 61 / 74 / 75 /
81 / 86 / 92 / 95 / 99）**全部算出了论文的否定**。逐条比对过论文原式，11 条都是
把 `(a < b) ? x : y` 里的 `a` 当 `threshold` 传的。

**为什么活了这么久**：只有 `alpha86` 露了馅 —— 它的 `a` 是 [0,1] 的 `ts_rank`、
`b` 是 `cs_rank`，反过来的条件永远不成立，列就成了 7350 行的常数 0。**另外十条
只是符号反了，而符号反了的因子照样有方差、照样有 rankIC、照样能训。**

**为什么改的是命名而不是比较符**：`alpha62` / `alpha64` / `alpha65` / `alpha68`
把同一个论文构造用裸 `<` 运算符写了一遍，两种写法此前**逐行不一致**且无人发现。
兄弟函数 `quesval` 的阈值是标量、不需要 join，从来没这个毛病 —— 所以修法是让
列名自己说话，而不是再依赖「join 的哪一侧拿到后缀」这条隐式知识。

### 3. `math_function.py` — `pow2` 不再把「无定义」写成 0

**改哪里**：删掉结尾的 `.fill_nan(None).fill_null(0)`，补一条
`base == 0 且 exponent > 0 → 0` 的显式分支，其余落到 `None`。

**上游原行为**：任何算不出来的行都变成 `0.0`，并且**列的 NaN 占比报 0.00%**。
实测 `hk_bluechip_10`：`alpha78` 的指数侧有 73.76% 的行是 NaN（内层
`ts_corr` 在秩序列恒定的窗口上无定义），于是**那一列 75.32% 是伪造的 0**。另外
三个调用点分别伪造了 2.72% / 3.12% / 7.14%。

**为什么 0 是最坏的填充值**：四条表达式全是 `rank^rank` 或 `rank^ts_rank`，真值
域是 (0,1]。0 不是中性的中间值，它**低于整个合法值域**，对任何模型都读作「这一
列里最极端的一次观测」。换成 NaN 之后 `process_drop_na` / `process_cs_fill_na`
能接手；0 则是直接拿去训练。

⚠️ 顺带一条实测细节：polars 里 `NaN > 0` 为 **True**，所以 NaN 底数会走第一个
分支、由 `.pow()` 自己吐回 NaN。真正需要末尾 `otherwise` 的只有「负底数配非整数
指数」和「0 的非正次幂」。

### 修完之后 Alpha101 的实测判据

⚠️ **本小节的读数是在两份太小的面板上取的，收尾那一轮重做了，结论换了。**
不删是因为「面板尺寸会伪装成代码缺陷」这件事本身值得留档；**要引用判据请直接看
后面的「收尾一轮」，那里的面板是 50 票 × 800 天，判据也多了量级与 inf 两项。**
一句话对照：这里说「两份面板都 79 列可用」，重测之后是**无停牌面板 80 / 82、
有停牌面板 75 / 82**，而修前分别是 72 与 71。

同一份 `hk_bluechip_10`（10 票 × 735 天 = 7350 行）与 `tests/test_alpha101.py`
的 50 票 × 300 天合成面板各算一遍，判据用 `semantics.describe_feature_health`
（`flat_group_fraction >= 0.5` 判 DEGENERATE）：

| | 定义列 | 修前存活 | 修后存活 | 修后 DEGENERATE |
|---|---|---|---|---|
| 10 票真实 lab | 82 | 77 | **79** | alpha68 / alpha75 / alpha96 |
| 50 票合成面板 | 82 | 78 | **79** | alpha19 / alpha39 / alpha84 |

**「82」是定义数不是活列数** —— 上一轮记的 82 数的是 `add_feature` 的行数。101
条里 18 条含 `IndNeutralize`、1 条（alpha56）缺 `cap` 字段，全部注释掉，剩 82 条
生效。两份面板上真正可用的都是 **79 列**。

两份面板的 DEGENERATE 名单不重叠，因为它们是两种不同的成因，都不是代码缺陷：

* **10 票那三条是宇宙太小。** alpha68 / alpha75 / alpha96 都含
  `ts_corr(cs_rank(·), cs_rank(·), w)`，十票宇宙里秩序列在短窗口上频繁恒定 ⇒
  相关系数无定义。同样三条在 50 票面板上是健康的（alpha96 的 NaN 从 96.9% 掉到
  38.4%）。**判据是：Alpha101 需要一个像样的截面宽度，十票不够。**
* **50 票那三条是面板太短或单位问题。** alpha19 / alpha39 要
  `ts_sum(returns, 250)`，300 天的面板加上其它项的暖机根本产不出值（真实 lab 上
  它们 NaN 34%、健康）。alpha84 是 `SignedPower(Ts_Rank(...), delta(close, 5))`
  —— **论文自己把一个价格差当指数用**，量纲不成立，值随价格单位爆炸。

**alpha84 与 alpha54 刻意不 clip。** 合成面板上它们到 8.8e+245 / 1.2e+63，但那
是测试夹具故意注入的 `close = 1e-10` 加原始价格单位共同造成的；真实 lab 走
`load_bar_df` 的 `close_0` 归一化，`ts_delta(close,5)` 的 p99 只有 0.33，
alpha84 峰值 56.46、alpha54 峰值 1.0，两列都健康。clip 会凭空造一个公式里没有的
数，并把「面板单位不对」这件事永久藏起来；正确的表述是**它们对价格单位敏感，
喂原始价格的面板就会炸**。

**还剩两条已知、本轮不修的**：

* `alpha53` 在真实 lab 上有 **5.2% 的 ±inf**，来源是分母 `close - low` 在
  `close == low` 的行上为 0（同一份数据里这样的行占 2.72%）。论文 Alpha#53 的
  分母就是这个，仓里也已经有 `process_replace_inf` 专门收拾它 —— 改公式是改论文
  不是修 bug。
* `cs_mean` / `cs_std` / `cs_sum`（以及经由 `cs_sum` 的 `cs_scale`）**不跳过
  NaN**：一只票停牌就把当天整个截面的答案变成 NaN。实测 `alpha28` 在首个日期上
  十只票全 NaN。**不修的理由**是它 fail-**closed** —— 产出的是 NaN 不是一个像样
  的错数，跟本轮修的三条（都是把无定义洗成合法值）性质相反，值得单独一笔带自己
  的对拍。

**验证**：

```bash
cd vnpy
../vnpy/.venv/bin/python -m pytest tests/alpha/test_cs_rank_percentile.py -q   # 7 passed
../vnpy/.venv/bin/python -m pytest tests/alpha/test_quesval2_direction.py -q   # 6 passed
../vnpy/.venv/bin/python -m pytest tests/alpha/test_pow2_undefined.py -q       # 7 passed
```

变异验证：`cs_rank` 退回 `rank()` → **7 例全红**；`quesval2` 退回 suffix join →
**6 例里 5 例红**；`pow2` 补回 `.fill_null(0)` → **7 例里 5 例红**。全量
`pytest tests -q` 从 165 到 **185 passed**。

## 停牌日的 NaN 不再被比较运算判出方向 —— **语义 v2**

上一轮的「已知没做的事」第一条挂的就是这个，理由写的是「当前是潜伏态、修它会让
本轮的验证数字说不清归属」。Alpha101 那一轮结束后归属问题没了，这一轮把它清掉，
并把 `FEATURE_SEMANTICS_VERSION` 推到 **2**。

### 1. `utility.py` — 四个序关系比较先把 NaN 掩成 null

`DataProxy.__gt__` / `__ge__` / `__lt__` / `__le__` 现在都先过一个静态助手
`_ordering_operand`：**浮点**操作数先 `fill_nan(None)` 再比较。`__eq__` / `__ne__`
**刻意不动**（理由在下面）。

**旧写法错在哪**：polars 把 NaN 排在所有实数之上，并且**对它给出判决**，而不是
拒绝回答。实测 polars 1.43.0、Float64 列：`NaN > 11.0` 是 `True`，而
`12.0 > NaN` 是 `False` —— 同一个缺失价格从左边读是「大于」、从右边读是「不
大于」。

`lab.py:273-277` 把停牌日的每一列都写成 `float("nan")`，于是 Alpha158 那 15 个
`cnt*`（形状全是 `ts_mean(close > ts_delay(close, 1), w)`）**一次停牌要错两次**。
实测 `close = [10, 11, NaN, NaN, NaN, 12, 11.5, 11.8]`，未护栏的 flag 序列是
`[null, 1, 1, 0, 0, 0, 0, 1]`：

* 下标 2（停牌首日）被记成上涨（`NaN > 11.0`）—— **伪造一个涨日**
* 下标 5（复牌日，11.0 → 12.0 真涨 9.1%）被记成非上涨（`12.0 > NaN`）——
  **抹掉一个真涨日**

所以上一轮台账里写的「`cnt*` 会开始系统性高估上涨天数」**是错的描述**，这里更正：
偏差不是单边的，一次停牌同时注入一个假涨和一个假跌，净效应取决于被挤掉的真实日。

**为什么它值一次版本推进而不是「顺手修一下」**：它**不留任何痕迹**。比较结果被
`_comparison_series` 转成 Int32、再被滚动均值抹平，既不产生 NaN、也不改 dtype、
更不报警 —— 列里只是换了个数。这逐字就是 `semantics.py` 开篇描述的那种失效。

**实测爆炸半径**。合成面板 5 票 × 160 天 = 800 行，其中一票连停 3 天（占
**0.375%** 的行）；护栏开/关各跑一遍 Alpha158 的全部 158 条表达式（直接调
`calculate_by_expression`，不走 spawn Pool），逐列对拍：

| 列 | max\|Δ\| | 该列量程 | 变化行数 |
|---|---|---|---|
| `cntd_5` | **0.800** | [-1, 1] | 8 |
| `cntp_5` | **0.600** | [0, 1] | 8 |
| `cntd_10` | 0.400 | [-1, 1] | 13 |
| `cntp_10` | 0.300 | [0, 1] | 13 |
| `cntn_5` | 0.200 | [0, 1] | 6 |
| `cntp_20` | 0.0875 | [0, 1] | 23 |
| `cntn_60` | 0.0254 | [0, 1] | 63 |
| `cntd_60` | 0.0175 | [-1, 1] | 59 |

**恰好 15 列变化，一条不多一条不少，全是 `cnt*`**，合计 **411 个 cell**
（15 × 800 = 12000 的 3.4%），`extra_nan` 全 0。窗口越长单点偏差越小、污染行数越多
—— **一次 3 天停牌把 60 日窗口的后 59~63 个读数全改掉**。同一次跑里另有
`rsqr_60` (2.0e-14) 与 `resi_60` (9.1e-16) 出现差异，那是下面那条已知的浮点非
确定性，不是改出来的：**同一份代码连跑两遍**，`rsqr_60` 自己就差 4.3e-14。

**修完 `cnt*` 不会变成 NaN —— 这一点反直觉，必须写下来。** `ts_mean` 是
`rolling_map(np.nanmean, min_samples=1)`，null 进窗口是被**跳过**而不是被传染。
`cnt_w` 的语义因此从「停牌算一个上涨日」变成「**在真正观测到的那些天里，涨的占
几成**」—— 正是 qlib `Mean($close>Ref($close,1), w)` 的原意。实测 15 列 extra-NaN
全是 0。**回归测试因此不能靠数 NaN 来验证，必须比数值**：
`tests/alpha/test_suspended_day_comparison.py` 里有一条用例专门钉这件事，它在护栏
被摘掉之后**仍然是绿的**，这是有意的 —— 它守的是「护栏没有把列变哑」而不是护栏
本身。

**为什么不改 `_comparison_series`**：它拿到的是**已经算完的 Boolean**，`NaN > 2.0`
就是一个普通的 `True`，与真 `True` 无法区分。要在那里修就得改签名把两个操作数都
传进去 —— 那和现在这个改法是同一件事换个地方写，而且会让 `__eq__` / `__ne__` 也
一起被卷进去。

**为什么不碰 `utility.py:39` 的 `.cast(pl.Int32)`**：见下面独立的一节。两条理由
在这里都成立且独立：它是上游 `5881a61b` 的有意设计；而且错值在 cast **之前**就已
产生，摘掉它只是把 `1` 换成 `True`，错值原样保留，代价却是 `rolling_map` 对
Boolean 直接 `InvalidOperationError`、15 个 `cnt*` 一条都算不出来。

**`__eq__` / `__ne__` 刻意不护**：polars 里 `NaN == NaN` 是 `True`（实测，与 IEEE
754 相反）。那是一个**有定义的答案**而不是抛硬币，掩成 null 等于把定义换成未知。
测试里有一条正面钉住它，好让将来「把 NaN 统一掩掉」的顺手一刀先跟它吵一架。

**这个护栏覆盖不到的**（写下来，防止被当成通用 NaN 闸）：`sign(NaN)` 返 1、
`quesval` / `quesval2` 对 NaN 走 true 分支、`ts_less(x, 字面量)` 吞 NaN、
`Series.arg_max` 跳过 NaN。四个各自独立的生产者、四套独立机理。**Alpha158 一个都
不碰，Alpha101 四个全碰。**

### 2. `semantics.py` + `vnpy/__init__.py` — 戳推到 2，两处同进同出

`FEATURE_SEMANTICS_VERSION: int = 2`、`__version__ = "4.4.0+hexonal.2"`、
新增 `SEMANTICS_HISTORY[2]`，**必须在同一笔提交里**。

**为什么推 v2，而不是「实测没变所以不推」**。这是本轮真正需要论证的决定，因为
「不推」有一份看起来很硬的实测支撑：**在今天盘上的每一份面板上，护栏前后逐位
相同**（下面有数）。否掉它的理由是**戳这个机制能表达什么**：
`semantics.py:183` 做的是一次**加载产物时的标量等值检查**，它能回答的只有「造这个
产物的代码跟我一致吗」。它**表达不了条件命题**（「在无停牌面板上一致」）—— 因为
加载时手上只有产物、没有面板。

在这个约束下只需问一句：**哪个选择会让戳说谎？**

* **推 v2** 的错误方向是**假阳性**：一份在无停牌面板上建的 v1 产物其实与 v2 等价，
  却被拒。代价 = 一次重算。**实测代价为零** —— `find` 遍全工作区（排除
  `questdb-data/` 与 `.venv`），盖着 v1 戳的产物**一份都不存在**，只有三份
  `*.pre-semantics-1.*`（v0 口径、已改名搁置、闸本来就拒）。
* **保持 v1** 的错误方向是**假阴性**：在有停牌的面板上，坏代码建的产物和好代码建的
  产物**都盖 1**，而它们在 `cntd_5` 上能差 0.8。闸会把两者当成可互换的放行。代价 =
  **一次静默的不可比比较**，也就是这个模块存在的全部理由。

不对称是压倒性的：v2 的错今天代价为零，v1 的错正是这套机制要防的那件事。

**明确否掉的替代方案**（都想过，都不做）：

* **给 `load_bar_df` 加一道「拒收含停牌行的面板」的 fail-closed 闸**，用它换掉推
  版本。不做：它拒的是**合法输入** —— 掩码存在的意义就是处理停牌，它正上方 15 行
  注释整段在论证停牌日为什么必须变 NaN。而 `semantics.py` 自己已经实测拒绝过这个
  反模式：「**A gate that fires on legitimate inputs gets switched off within the
  week.**」何况它**只在不推 v2 时才承重**，戳到了 2 它就无事可做。
* **把「面板有没有停牌」也记进戳**，让闸做条件判断。不做：停牌行数是**面板**的
  属性，而戳盖在 dataset pkl / model pkl / signal parquet 上，其中 signal parquet
  只有 datetime / vt_symbol / signal 三列，里面**没有任何面板的痕迹**。要穿三种
  产物、三条路径，还要维护一张兼容矩阵，换来的是免掉一次当前代价为零的重算。
* **推 v2 但给一份「已验证等价」的白名单放行 v1 产物**。不做：白名单今天是**空
  的**。给一个 fail-closed 的闸永久加一条**被执行零次**的旁路，它第一次被执行时
  必然是错的。

等价性这件事本身没有丢掉，它写进了 `SEMANTICS_HISTORY[2]` 的散文里（带实测数字），
**但没有写进闸的逻辑**。历史表的职责本来就是这个：将来拿着 v1 读数的人可以自己
判断读数能不能平移，而闸一根旁路都不长。

**同进同出这条纪律现在是机器强制的**。`tests/alpha/test_suspended_day_comparison.py`
里的 `test_the_local_version_segment_tracks_the_feature_semantics_version` 断言
`vnpy.__version__ == f"4.4.0+hexonal.{FEATURE_SEMANTICS_VERSION}"`。实测两个方向
各自变异：只回滚常量 → 红；只回滚 `__version__` → 红。另外
`test_semantics.py:131` 的 `range(FEATURE_SEMANTICS_VERSION + 1)` 让缺失的历史
条目直接把测试打红（实测摘掉 `SEMANTICS_HISTORY[2]` → **6 例红**，因为 raise 语句
自己会 KeyError）—— 所以这一笔**不可能**落成一个没有说明的版本号。

### 3. 对已冻结协议的影响：不作废，改一行就够

`vnpy_alphakit/protocols/us_ai_basket_2026-08-07/PROTOCOL.toml` 声明
`[code].feature_semantics_version = 1`（注意它与 `[protocol].version = 2` 是两个
不同的数）。**本仓没有碰 `protocols/` 下任何文件**，以下是需要转达的判据：

PROTOCOL.md §6 第 4 条自己预注册了推版本时怎么办 ——「157 列真的动了就是新协议，
没动就在 `[code]` 里把版本号更上去」。**判据这边已经跑完了，落在「没动」那一支**：

| 面板 | 行数 | 停牌掩码命中 | Alpha158 逐列对拍 |
|---|---|---|---|
| `lab/hk_bluechip_10/daily`（只读拷贝） | 7350 | **0** | **158 / 158 逐位相同** |
| 协议源 `Kronos/finetune_us/data50_1d` | 174139（55 CSV） | **0** | 掩码不触发，护栏前后必然相同 |

掩码按 `lab.py:220` 的原式复算（七列 `sum_horizontal() == 0`）；`close == 0` 与
`volume == 0` 也都是 0 行。掩码一次都不触发 ⇒ 护栏前后逐位相同。所以协议要改的只
有 `[code]` 三个键：`feature_semantics_version` 1 → 2、`vnpy_version`
`4.4.0+hexonal.1` → `4.4.0+hexonal.2`、`base_commit` 换新 hash。

🔴 **但 `vnpy_alphakit` 那边会红两条，这不是意外、是那两条用例被造出来干的事**，
实测：

```
tests/test_protocol_freeze.py::test_protocol_records_the_feature_semantics_version_currently_installed
tests/test_protocol_basis.py::test_recorded_basis_is_what_the_installed_feature_code_emits_right_now
```

第一条比的是两个人手打的整数，改 `PROTOCOL.toml` 就绿。**第二条要看仔细**：它报
「15 列的指纹变了（`cntd_5..60` / `cntn_5..60` / `cntp_5..60`），受影响的读数
18 条」。这看起来像是在反驳上面那张表，其实不是 —— `vnpy_alphakit/basis.py` 的
指纹夹具是**8 票 × 400 天的合成面板，每 37 天一个停牌日**，它自己的模块 docstring
写明这样造是因为「下一个在途的语义变更就是停牌日 NaN 比较，**而在没有停牌的夹具
上那个变更什么都不动**」。

所以这两件事是同一个事实的两面，而且互相印证：

* 夹具**有**停牌 ⇒ 恰好 15 个 `cnt*` 的指纹变了 —— 这是本轮爆炸半径的**第三次
  独立复算**，而且它走的是完整的 `BarData → save_bar_data → load_bar_df →
  prepare_data` 真实路径，不是我手搓的 frame
* 协议的真实面板**没有**停牌（174139 行 0 命中）⇒ 读数不动

实测反证：把 `utility.py` 换回 HEAD（护栏摘掉、戳仍是 2），第二条用例**转绿** ——
所以那 15 列确实是护栏动的，不是别的什么东西顺路碰的。

**这 18 条读数要不要重测，是协议那边的判断，不是这里的。** 提醒一句
`basis.py:562` 自己写在错误消息末尾的话：**「把指纹改到匹配而不重测，是本文件存在
的唯一理由所针对的那个动作」** —— 正确顺序是先在真实面板上确认读数没动，再跑
`python -m vnpy_alphakit.basis --write`。

⚠️ **重跑协议 §5 的对拍之前必须先知道这条，否则要白烧一天**：
**`beta_60` / `rsqr_60` / `resi_60` 即便在完全相同的代码下也不是逐位可复现的。**
`ts_slope` / `ts_rsquare` / `ts_resi` 用 `pl.sum_horizontal` 折叠 60 个 shift 列，
polars 并行归约的加法次序每次不同。本轮同代码连跑两遍实测：`beta_60` 150 行 /
4.1e-17，`rsqr_60` 150 行 / **4.3e-14**。协议 §5 现在冻的是「142/142 列
max|Δ| = 0.0」，**复核这三列必须用 `rtol=1e-9` 而不是精确相等** —— 否则下一次
复现会红在一个与本次改动毫无关系的地方，而红的样子恰好像「修复动了特征」。

⚠️ 还有一条防反射动作的提醒：这次推戳**不产生**给那 50 条 `[实测]` 补
`[实测@v1]` 标签的需要 —— **没有任何读数改变**。

### 4. 下游立刻会发生什么

戳一到 2，**所有既有 signal / dataset / model 产物当场开始加载失败**。这是设计
意图，但它意味着排序很重要：`vnpy_app/run_live_alpha.py:229` 的 `load_signal`
必须**先**有 try/except（已在 `vnpy_app` 那边落地，退出码 `EXIT_STALE_SIGNAL = 6`
加三行中文提示），否则实盘入口第一次撞上这道闸时看到的是 40 行 polars/pickle 裸
traceback —— 而从「工具坏了」出发，最顺手的下一步就是绕开这道闸。

`vnpy_alphakit/run_example.py:183/189` 的 `load_dataset` / `load_model` 仍然没有
try，撞上闸会裸 traceback。**这是已知且接受的**：它退出非零、不碰网关，而一个宽
捕获会把真缺陷伪装成运维退出码。要接就单独一笔。

### 5. 这一轮刻意没修的（连同代价）

划线的判据只有一条：**这一轮只修「把无定义洗成一个看起来合法的数」的缺陷，不修
「产出 NaN」的缺陷。** 前者 fail-open、静默、会进模型；后者 fail-closed、吵闹、
看得见。合并两类会让 v2 的爆炸半径从 15 列涨到 35 列以上，还会让协议那边的不变量
复核难以归因。

* **`cs_mean` / `cs_std` / `cs_sum` / `cs_scale` 不跳过 NaN。** 与本轮**同源**
  （都是停牌 NaN），最容易被顺手扫进来。但它 fail-closed：一只票停牌就把当天整个
  截面变成 NaN（实测 `alpha28` 首个日期十票全 NaN）。**代价**：接入港股 / A 股后
  alpha28/29/31/32/60 会按当日停牌票数成比例丢日期 —— 而且是在 NaN 占比里**看得
  见地**丢。单独一笔，带自己的逐列对拍。
* **`imax_*` / `imin_*` / `imxd_*`（15 条）与 `wvma_*`（5 条）。** 两套各自独立的
  吞 NaN 机理（`Series.arg_max/arg_min` 跳过 NaN；`ts_mean` / `ts_std` 走
  `np.nanmean` / `np.nanstd`），实测在停牌盘上 extra-NaN 同样为 0。但它们是
  **【遗漏】不是【伪造】**：算子选择不看那个停牌日，而不是给它编一个方向。本轮的
  护栏修不到它们，**报告里也不能合并成一条**。代价：接入有停牌市场后这 20 列按
  「窗口内可见样本数」而非「窗口长度」计算，口径与文档不符 —— 但不会反向记账。
* **`beta_60` / `rsqr_60` / `resi_60` 的浮点非确定性。** 修它要在热路径上强制有序
  归约，为 7e-14 付这个价不值。**但它必须被写下来**（上面 §3 已写），否则下一个人
  会为一个与任何改动无关的红花掉一天。

### 验证

```bash
cd vnpy
../vnpy/.venv/bin/python -m pytest tests/alpha/test_suspended_day_comparison.py -q  # 10 passed
```

变异验证三个方向，全部实测：

| 摘掉什么 | 结果 |
|---|---|
| `_ordering_operand` 退回 `return values` | **10 例里 5 例红** |
| 只把 `FEATURE_SEMANTICS_VERSION` 回滚到 1 | 版本配对那条**红** |
| 只把 `__version__` 回滚到 `hexonal.1` | 同一条**红** |
| 摘掉 `SEMANTICS_HISTORY[2]` | `test_semantics.py` **6 例红** |

那 5 条不红的用例是**有意的不变量**：`NaN == NaN` 仍为真、整数操作数不受影响、
`cnt*` 修完仍是有限值、无停牌面板逐位不变、以及版本配对。它们守的是「护栏没有
顺手改坏别的东西」，摘掉护栏它们本来就该是绿的。

全量 `pytest tests -q` 从 185 到 **195 passed**。

## 收尾一轮：三处把话说过头的地方，加一处同源的 fail-open

这一轮**不动戳**（仍是 2），也不动 Alpha158 的任何一列 —— 逐列对拍确认过，见
下面的验证段。它做的是把前两轮留下的四个真问题清掉：三处是**文字比代码走得远**
（写了代码给不出的保证），一处是**修完 `cs_rank` 之后才被推到前台的老缺陷**。

### 1. `semantics.py` — 无戳产物的报错只讲了最新那一版

**改哪里**：`assert_compatible` 与 `assert_parquet_compatible` 的两个
`found is None` 分支，从 `SEMANTICS_HISTORY[FEATURE_SEMANTICS_VERSION].describe()`
换成 `describe_gap(UNSTAMPED_VERSION)`；新增模块常量 `UNSTAMPED_VERSION: int = 0`。

**旧写法错在哪**：无戳 = v0（戳是**作为 v1** 引入的），所以它的主人需要的是从 v0
到今天的**整份**变更表。历史表里只有一条记录的时候，「最新那一条」和「v0 之后的
全部」恰好是同一句话，缺陷看不出来；**戳一推到 2，一份 v0 产物就只会被告知 v2 改
了什么，v1 的 vwap 归一与 Float64 转型一个字都听不到**。实测：`describe_gap(0)`
渲染 **2359 字符**、同时含 `v1:` 与 `v2:`；旧写法 **1495 字符**、只含 `v2:`。

**为什么这不是小事**：`lab/hk_bluechip_10/` 里那三份 `*.pre-semantics-1.*` 正是
命中这个分支的人群，而这个模块存在的**全部理由**就是「告诉下一个人到底变了什
么」。少讲一半，等于把 puzzle 换成了半个 sentence。

**未来 merge 注意**：这是 fork 自己的文件，上游没有对应物。加 v3 时**不需要**改
这两处 —— 它们现在读的是常量与整段 gap，新增历史条目自动被覆盖到。

### 2. `utility.py` + `semantics.py` — 「zero extra NaN」是在三天停牌上量的

**改哪里**：`_ordering_operand` 的 docstring 与 `SEMANTICS_HISTORY[2].summary`，
**代码一行没动**；测试那边把断言改名为
`test_cnt_features_over_a_halt_shorter_than_the_window_stay_finite`，并新增
`test_a_halt_at_least_as_long_as_the_window_leaves_no_reading_at_all`。

**旧写法错在哪**：v2 那一节写的是「零 extra NaN」，那是在 `CLOSE_WITH_HALT`
（三天停牌）上量出来的，而**边界就在四天**。一次 `h` 天的停牌会让 `h + 1` 个
flag 变空 —— 停牌那几天，**外加复牌当天**，因为复牌日的 `ts_delay(close, 1)` 取
到的是最后一个停牌日而不是最后一个交易日。于是窗口 `w` 在 `h >= w - 1` 时窗口里
一个观测都不剩，读数变成 null。

实测（单票，逐个 halt 长度数缺失读数）：

| 停牌天数 h | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|
| `w = 5` 缺失读数 | 0 | **1** | 2 | 3 | 4 | 5 |
| `w = 10 / 20 / 60` | 0 | 0 | 0 | 0 | 0 | 0 |

**Alpha158 最窄的窗口就是 5**，所以**一次四天停牌就足以让 `cntp_5` / `cntn_5` /
`cntd_5` 变空** —— 港股停牌待公告是四天量级，A 股按周按月算。这是**正确行为**
（窗口里没有观测就没有分数可报），也是**看得见的行为**（`process_drop_na` 会把
那些行整行丢掉）；但写成无条件的「零 extra NaN」，第一个建 A 股面板的人会把它读
成一句代码从没许过的承诺。

50 票 × 800 天、每票一次五天停牌的面板端到端印证了这条公式：`cntp_5` / `cntn_5`
/ `cntd_5` 各丢 **100** 个读数 —— `h - w + 2 = 2` 每票，乘 50 票，一个不差；
`cnt*_10/20/30/60` 一个都不丢。

**未来 merge 注意**：纯散文与测试，与上游无冲突面。

### 3. `math_function.py` — `pow1` 也在把缺失洗成 0，而是 `cs_rank` 把它推到前台的

**改哪里**：`pow1` 的 `.otherwise(0)` 拆成「`base == 0` 且指数为正 → `0.0`」
与「其余 → null」两支；指数是 Python float，所以 `0 ** exponent` 在函数入口一次
定死，不是逐行判断。

**上游原行为**：`null` 底数在 polars 里既不满足 `> 0` 也不满足 `< 0`（与 null
比较得 null，不是 false），于是落进 `otherwise` 变成一个货真价实的 `0.0`。

**为什么这一轮必须修、不能挂到下一笔**：**是上一轮的 `cs_rank` 修复把 null 放到
那里的**。`cs_rank` 现在把非有限输入排除在排名之外、答 null，而 alpha71 / alpha81
/ alpha95 的形状全是 `pow1(cs_rank(...), k)`。实测四票截面含一个 NaN：`cs_rank`
答 `[0.333, null, 0.667, 1.0]`，旧 `pow1` 把它变成 `[0.111, 0.0, 0.444, 1.0]`
—— 这三条的真值域是 (0, 1]，**伪造的 0 低于整个合法值域**，与 `pow2` 那条的论证
逐字相同。不修等于把伪造点往下游挪了一格，而不是拿掉。

**爆炸半径（隔离测量：只回滚 `pow1`，其余全留）**：82 列里动 **3 列** ——
alpha1 / alpha81 / alpha95。alpha1 多出 50 个诚实的缺失（0.50% → 0.62%）；
alpha81 与 alpha95 是 `quesval2(..., 1, 0)` 的二值列，**无停牌面板上翻转
1207 / 644 个 cell，有停牌面板上翻转 3921 / 2418 个（9.8% / 6.0% 的行）**。
alpha41 / alpha47 / alpha54 的底数分别是 `high * low`、归一化 `close`、
`open`/`close`，永远为正，一个 cell 都没动 —— 这是「修得准不准」的旁证。

**未来 merge 注意**：与 `pow2` 同一个文件同一段逻辑。上游若重写 `math_function`，
这两条要一起看；判据是「`otherwise` 落到的是不是一个会被当数据用的常数」。

### 4. `tests/alpha/test_alpha101_health.py`（新文件）— Alpha101 第一次有值级回归网

**为什么需要**：`tests/test_alpha101.py` 是上游文件，它那 100 条断言**全是同一
行** `assert "data" in result.columns`。实测把本轮三条算子缺陷逐个放回去，**100
条一条都不红**：`alpha85` 飙到 `50 ** 50`、`alpha86` 近乎恒定、`alpha78` 有
75% 是伪造的 0 —— 它全部放行。这就是那三条缺陷能活到今天的原因，也意味着
「185 → 195 passed」对 Alpha101 的正确性**零证明力**。

按 FORK.md 的分线规矩，**新增能力放独立文件**，上游那 100 条一行没动。

新文件断的是**性质**不是形状，每条对准一个机理：

* **量级不随宇宙大小走。** 同一条表达式在 12 票与 20 票两个宽度上跑，要求上界
  一样。序号版 `cs_rank` 给的是 `N ** N`（12 票 8.92e+12、20 票 1.05e+26），
  单一阈值挡不住它、两个宽度可以。
* **真值域不含 0 的列里不许出现精确 0。** 这是缺失率看不见的东西 —— 被伪造的
  那些行**正是**缺失率读 0.00% 的原因。实测这份面板上修前 alpha78 有 397 个、
  alpha84 696 个、alpha85 130 个、alpha94 751 个。
* **退化用仓里自己的 `FLAT_GROUP_LIMIT` 判。** alpha27 / alpha86 / alpha95 在
  序号版下 flat 分别是 0.881 / 0.734 / **1.000**（alpha95 整列塌成一个值），
  现在是 0.003 / 0.172 / 0.147。用 `semantics.measure_feature` 而不是自己另发明
  阈值，顺带让那套健康读数从摆设变成承重件。

🔴 **这张网【看不见】`quesval2` 的方向反转，而这一条必须写下来。** 隔离实测：
只把 `quesval2` 的比较方向反过来，82 列里动 **11 列**（alpha7 / 21 / 23 / 61 /
74 / 75 / 81 / 86 / 92 / 95 / 99，正是 docstring 点名的那十一条），而**没有一列
的量级、缺失率、distinct 数或 flat 比例发生任何变化**。一个符号反了的因子仍然是
一个规规矩矩的列。**任何列级筛查都不可能抓到它**，所以守它的只能是
`test_quesval2_direction.py` 那种直接操作符测试；在这张网里硬加一条「碰巧会红」
的断言，量的其实是别的缺陷顶着它的名字。

### Alpha101 现在到底可不可用（这一轮重测的判据）

面板：50 票 × 800 天 = 40000 行，`vwap ≠ close`（否则三分之一的表达式塌成 0），
含一段刻意的平盘连击让 `>` 与 `<` 都吃到严格相等。**800 天是必需的** —— alpha19
与 alpha39 含 `ts_sum(returns, 250)`，300 天的面板上暖机就吃掉 83.3%，会让面板
长度伪装成代码缺陷。判据四项：缺失率 > 50% / `flat_group_fraction > 0.5` /
`absmax > 1e4` / 出现 inf，任一命中即判不可用。

| 面板 | 定义列 | 修前可用 | 修后可用 | 修后判不可用的 |
|---|---|---|---|---|
| 无停牌 | 82 | 72 | **80** | alpha53（论文自己的分母）、alpha96（缺失 50.6%）|
| 每票一次五天停牌 + 一次一天停牌 | 82 | 71 | **75** | alpha19 / alpha39 / alpha52 / alpha36（长窗口）、alpha28 / alpha32（`cs_*` 不跳 NaN）、alpha53 |

**所以答案是有条件的可用**：

* **无停牌面板上 80 / 82 可用**，比修前多 8 条。多出来的是 alpha17 / alpha20 /
  alpha27 / alpha78 / alpha83 / alpha85 / alpha86 / alpha95 —— 全部是被序号版
  `cs_rank` 撑爆量级或压成常数的那批。
* **有停牌面板上只有 75 / 82**，而且**四条长窗口列基本作废**：alpha19 / alpha39
  的缺失率 31.25% → **73.63%**，alpha52 32.78% → 71.73%，alpha36 24.88% →
  63.20%。机理是一次停牌污染整整一个 250 天窗口，而修前是 `cs_rank` 给那个 NaN
  发了个最高名次把它藏住了。**这不是修坏，是修前那几列有一部分本来就是编的。**
* **`process_drop_na` 吃全部 82 列在有停牌面板上剩 0 行 —— 修前修后都是 0。**
  这条要说清楚，因为它容易被记到本轮头上：无停牌面板上 9388 → 7673 行（−18%），
  有停牌面板上 **0 → 0**。排除那四条长窗口列之后是 4303 → 3836（−11%）。
  **代价是真的（少 11%~18% 的可训练行），但「面板被清空」在修之前就已经是事实。**

**一条实测更正**：上一轮复核报的「alpha19 / alpha39 变成 100% NaN」在这份面板上
**复现不出来**。逐个长度量过：无停牌面板上两列的缺失率**恰好等于暖机下界
`250 / N`**（300 天 83.3%、400 天 62.5%、500 天 50.0%、800 天 31.2%），**修前修后
逐位相同**。那个 100% 是「300 天面板 + 序列中段带 NaN」两件事叠出来的，属于面板
性质，不是这一轮的产物。

### 验证

```bash
cd vnpy
../vnpy/.venv/bin/ruff check .                                          # All checks passed!
../vnpy/.venv/bin/mypy vnpy                                             # 2 个既有错误
../vnpy/.venv/bin/python -m pytest tests -q                             # 205 passed
```

**Alpha158 逐列对拍（这一轮不推戳的依据）**：50 票 × 800 天无停牌面板上，HEAD 与
工作树的 158 列 **moved 0 / 158**，逐位相同。有停牌面板上 **恰好 15 列**（全部
`cnt*`），`cntp_5` / `cntn_5` / `cntd_5` 各丢 100 个读数。

⚠️ 头一遍对拍时 `beta_60` / `resi_60` 也进了名单（4.15e-17 / 1.33e-15）。**那不是
改动**：同一份 HEAD 代码连跑两遍，这两列给出的差值**逐字相同**；两边都换成第二遍
的结果再对拍，名单就是干净的 15 列。这次浮到面上的是 `beta_60` / `resi_60`，上一
轮是 `rsqr_60`，**每次哪几列会漂是不定的** —— 所以「我这次跑出来是 0，说明它是
确定的」是错误推理。

变异验证（六个方向，靶子是 `tests/alpha/` 下的六个文件共 63 例）：

| 摘掉什么 | 结果 | 其中新健康网 |
|---|---|---|
| `cs_rank` 退回序号 | **12 例红** | 4 / 5 |
| `quesval2` 比较方向反转 | **5 例红** | 0（见上，列级看不见）|
| `pow2` 补回 `.fill_null(0)` | **7 例红** | 2 / 5 |
| `pow1` 退回 `.otherwise(0)` | **3 例红** | 0 |
| `_ordering_operand` 退回 `return values` | **6 例红** | 0 |
| 无戳分支退回只讲最新一版 | **1 例红** | 0 |

## 🔴 下次同步上游的预警：`upstream/alpha` 正在重写 `ts_function.py`

这是这份台账真正的价值所在 —— 别人无论如何都不会自己发现。

`upstream/alpha` 分支领先 `upstream/master` **8 个提交**（最新 `e8d44b95`
2026-07-31，尚未并入 dev），`git diff --stat upstream/master...upstream/alpha` 是：
新增 `factor_performance.py`（1137 行，替换 alphalens）、`ts_function.py`
**+382/−38**（原文件才 329 行，近乎重写）、`template.py` 33 行、
`backtesting.py` 27 行、一个 149886 行的 notebook。

它把 `ts_mean` / `ts_std` 等收进新的 `_rolling_by_symbol` 助手，docstring 明写
「**Mirrors Polars 1.26 rolling_map semantics** with per-symbol NumPy windows」。
读过它的实现：内部**用 float64 算**（`np.empty(..., dtype=np.float64)`、
`data_series.cast(pl.Float64)`），末尾在

```python
    # Map null flags to Polars null and cast to the input dtype
    if _is_integer_rolling_dtype(data_dtype):
        value_expr: pl.Expr = (... .cast(data_dtype))
```

处**把整数 dtype 转回去**。**上游在一次性能重写里把 cnt\* 那个 bug 固化成了
规格。** 改在生产者侧躲不开它，只是把陷阱留给下一个整数来源。

我实测过合并成本（用临时索引造假想提交跑 `git merge-tree --write-tree
--name-only`，不碰 HEAD / 工作树 / 任何分支）：

| 组合 | 冲突文件 |
|---|---|
| `master` + `upstream/alpha`（今天的存量债） | 1：`alpha/strategy/backtesting.py` |
| `master`+【本轮改动】+ `upstream/alpha` | 2：多出 `alpha/dataset/ts_function.py` |
| `master`+【本轮改动】+ `upstream/master` | **0** |

**这个 +1 是知情下接受的**：文本冲突是响的，被静默重新装回来的 bug 不是。

**解冲突时必须做的事**：把五个有损算子的 `.cast(pl.Float64)` 重新加回到
`_rolling_by_symbol` 的入参上，然后跑

```bash
cd vnpy && ../vnpy/.venv/bin/python -m pytest tests/alpha/test_ts_function_dtype.py -q  # 必须 11 passed
```

那个测试文件在 `tests/alpha/`，`upstream/alpha` 不碰该路径，所以它会活过合并 ——
**它就是这条预警的执行体**。测试断的是**数值不是 dtype**：dtype 断言会被
`template.py:134` 的 `fill_null(float("nan"))` 提升掩盖，走 `prepare_data` 出来的
死列 dtype 也是 Float64，修前修后都绿。

另外两笔：

- `alpha/strategy/backtesting.py` 上今天已经有一个**存量冲突**（`c95490b0` 留下
  的），与本轮无关，别把它牵进来。
- `upstream/alpha` 的 `34956c73`（2026-07-30「[Mod] 增加vwap支持」）**不是**本轮
  第 1 条那个 vwap —— 它加的是回测撮合价 `fill_price="vwap"`
  （`get_bar_vwap(bar)` 用 `turnover / volume`），碰的是 `backtesting.py` 与
  `factor_performance.py`，与特征归一化无关。名字撞车，别合错方向。
- `upstream/alpha` **没有碰** `lab.py`、`dataset/utility.py`、`model/`
  （`git diff --name-only upstream/master...upstream/alpha -- <这三个路径>` 为空），
  所以本轮第 1、3、5 条在下次同步时冲突面为零。

上游 alpha 侧的工作历来在发版时整包并进 master（上一次 `7f529a4e` 2026-05-09），
节奏约 5~6 个月（4.1.0 2025-06 / 4.2.0 2025-11 / 4.4.0 2026-05），下一次大概在
2026-11 前后。

## 为什么保留 `utility.py:39` 的 `.cast(pl.Int32)` 不动

写下来是为了防止后来者「顺手统一一下」。上游 `5881a61b`（2025-12-24）把比较运算
改成 Int32 是**有意为之** —— 同一笔提交删掉了 `math_function.cast_to_int` 并改了
`alpha_101.py` 八处，目的是让比较结果能直接参与算术。**退回 Bool 会打断
alpha_101**（而且 polars 的 `rolling_map` 对 Boolean 直接 `InvalidOperationError`）；
改成 Float64 则要连带改上游测试 `tests/alpha/test_dataproxy.py` 的 13 处
`assert_int_data`。我们选择不碰它，把修法放在算子侧。

`tests/alpha/test_ts_function_dtype.py` 里有一条
`test_comparison_operators_still_hand_integer_data_to_the_operators` 正面钉住这个
决定 —— 它在修复前后都是绿的，作用是让「哪天上游改了主意」这件事被看见。

**v2 那一轮又替它挡了一次**：停牌 NaN 那条缺陷看上去像是「cast 把 NaN 洗成了
1」，实际上错值在 cast **之前**就已产生（`NaN > 11.0` 本身就是 `True`），摘掉
cast 只会把 `1` 换成 `True`，错值原样保留，代价却是 15 个 `cnt*` 一条都算不出来。
**同一处代码被两轮不同的缺陷各诬告了一次，结论都是它无辜。**

## 语义版本与产物的绑定规则

`vnpy.alpha.semantics.FEATURE_SEMANTICS_VERSION` 与 `vnpy/__init__.py` 的
`__version__` local 段（`4.4.0+hexonal.N`）**必须同步递增**。

🔴 **回滚算法时必须连常数一起回滚。** 闸做的是**相等比较**不是大小比较，所以退回
旧算法却留着新常数 → 新存的产物带新戳、旧代码算的却是旧口径，闸会放行一批错的
东西。**这是整个方案里唯一能把闸从保护变成危害的路径。**

单独回滚闸（`semantics.py` + `lab.py` 六处接入）是安全的，任何时候都可以，代价
只是失去保护、不会产生错值。反过来单独回滚算法而留下闸 = 上面那个坑。

**这条纪律从 v2 起是机器强制的**，不再只是一段散文：
`tests/alpha/test_suspended_day_comparison.py` 的
`test_the_local_version_segment_tracks_the_feature_semantics_version` 断言
`vnpy.__version__ == f"4.4.0+hexonal.{FEATURE_SEMANTICS_VERSION}"`，两个方向各自
变异实测都红。配合 `test_semantics.py:131` 的
`range(FEATURE_SEMANTICS_VERSION + 1)`（缺历史条目 → 6 例红），推版本这件事
**不可能**落成「一个没人解释的数字」或「只滚了一半的一对常量」。

| 版本 | 这一版改了什么 | 哪些既有产物因此作废 |
|---|---|---|
| v0 | 上游 vnpy 4.4.0 语义：vwap 未归一化、五个滚动算子截断整数输入 | 一切在本模块之前建的产物；它们不带戳 |
| v1 | vwap 与价格同除 `close_0`；`ts_rank`/`ts_mean`/`ts_std`/`ts_quantile`/`ts_decay_linear` 入参转 Float64 | v0 下建的全部 dataset pkl / model pkl / signal parquet |
| v2 | 四个序关系比较先把 NaN 掩成 null，停牌日不再被判出方向（15 个 `cnt*`）；同一批提交里 Alpha101 的 `cs_rank` / `quesval2` / `pow2` / `pow1` 也已改口径 | v1 下、由**含停牌行的 bar** 建的全部产物。无停牌面板建的 v1 产物在数值上与 v2 相同（实测 158/158 逐位相同），**但一样被拒** —— 闸是等值比较，它看不见面板 |

⚠️ **`pow1` 那条是在 v2 落地之后补进来的，戳没有再动。** 判据与 Alpha101 前三条
一样：`alpha_158.py` 对 `pow1` 的引用数是 **0**，50 票 × 800 天无停牌面板上
Alpha158 **158 / 158 逐位相同**。表格里把它并进 v2 行是因为**从产物的角度它们不可
分** —— 没有任何盖 v1 戳的产物存在过（查过全工作区），所以「v2 的 Alpha101 口径」
指的就是这四条全部落地之后的口径，不存在一个只含前三条的中间态需要被区分。

## 投研子系统的三条缺陷 —— 本轮的规矩是「先复现，再改」

这一轮与前几轮不同的地方在方法而不在结论：**每一条都必须先写探针把它真的跑出来，
复现不了就当场划掉，不许「读代码推断它应该会出错」，也不许改条件去凑一个能出错的
场景**（那是造缺陷不是复现缺陷）。五条候选里有一条因此被降级（成分股台账的幸存者
偏差，实测已实现偏差为 **0**），一条被判定不属于本仓（见下节）。

### 1. `alpha/logger.py` — 导入研究子系统不再删掉交易日志的 sink

**上游原行为**：`logger.remove()` 裸调（`5247ac45`，2025-03-26 至今一字未改）。
loguru 的 handler 表是**进程级全局**的，这一句删的是【全部】handler，而它自己上面
那行注释写的是 `# Remove default output` —— **意图只是 loguru 的默认 handler 0，
调用写宽了**。`vnpy/trader/logger.py:40` 那句同理。

**实测的失效**（探针在 sandbox 的 `.vntrader` 里跑，真实 `~/.vntrader/log` 未污染）：
起一个真的 `MainEngine`、`write_log` 一条 marker、去磁盘上找 —— marker 上了 stdout，
当天日志文件 **0 字节**。不抛异常、`LogEngine` 照常转发每个 `EVENT_LOG`、GUI 日志
面板照常滚动。**一整个交易时段的落盘记录就这么没了。**

**中招的是三个入口里的两个，而且那两行都不提 `vnpy.alpha`**：`run.py:35` 装上 →
`run.py:40` 删掉；`run_gui.py:48` 装上 → `run_gui.py:50` 删掉。链路是
`vnpy_alphakit.rules` → `vnpy_alphakit/__init__.py:10 from .bridge` →
`bridge.py:42 from vnpy.alpha import ...`。也就是 **LLM Agent 下单入口与 Fluent
交易终端**。`run_live_alpha.py` 幸存纯属它把 `vnpy.alpha.lab` 写在 `MainEngine`
前面。顺带被翻掉三件事：电平门限 20（`SETTINGS["log.level"]`=INFO）→ 10（loguru 的
DEBUG 默认）；`colorize` 自动探测的 False → 强制 True（重定向输出里真的出现
`\x1b[32m`）；`{"log.console": false}` 下配置被**精确反转** —— 要「只写文件」的人
拿到「只打屏幕」。

**为什么不是删掉那一行了事**（本条唯一需要论证的决定）：alpha 的 sink 是给
「notebook 里只 import 研究子系统」用的便利默认值。光删 `remove()`，它会叠在
trader 的 stdout sink 之上，GUI 进程每行日志打两遍。所以改法是**两处都收窄**：按 id
丢掉 loguru 自己的默认 handler（`logger.remove(0)` + `except ValueError`），然后
**只在表为空时**才添自己的 sink。**反向顺序刻意不动** —— alpha 先、trader 后时
trader 那句宽的 remove 会扫掉我们的 sink 留下它自己的两个，那是对的（trader 的
format 带 level 与 gateway、文件 sink 才是要紧的那个）。

**用私有属性 `logger._core.handlers` 的代价**：loguru 没有公开 API 能回答「有人配过
我吗」，`logger.remove(0)` 也答不了（`ValueError` 只说默认 handler 没了，不说有没有
别的顶上）。外面包了 `except AttributeError` 退化成「上游行为减去清场」—— 多一行
控制台重复是看得见的烦人，交易日志文件消失不是。

**测试为什么必须开子进程**：缺陷全在 module import 的副作用里，同一解释器里第二次
import 是 no-op，不开子进程每条断言都会**无条件变绿**。

### 2. `dataset/template.py` + 三个模型 — label 按名字找，不按位置切

`lgb_model.py` / `lasso_model.py` / `mlp_model.py` 一共 6 处把特征矩阵写成
`df.select(df.columns[2: -1])`，等于把「`prepare_data()` 会把 label 排到最后一列」
这条约定硬编码成了切片下标。

**约定本身是真的** —— 实测 11 个 shipped processor 逐个跑过，label 全部仍在最后
一列；`add_feature(result=...)` 在 label 之后 join 也会被 `prepare_data` 的重排救
回；Alpha158 / Alpha101 又都自己 `set_label`。**所以上游自带的任何管线都踩不到，
缺的是守护它的东西**：`add_processor` 收的是任意 `Callable[[pl.DataFrame], ...]`，
没有契约也没有校验。

只要有一个调用方写的处理器在 label 之后留下一列（顺手打的流动性标记、忘了 drop 的
中间列），切片就变成 `[f1..fN, label]`：`fit` 把 label 同时当 X 和 y，`predict` 照
同样的切法喂，**列数前后自洽，所以 LightGBM / sklearn / torch 一个都不会吭声**。
在 `lab/hk_bluechip_10` 真日线上实测（10 只 / 6 特征 / 多出一列）：label 独占
LightGBM 总 gain 的 **99.9965%**，TEST corr(signal, label) 从 **0.004942 变
0.999952**，干净信号与被污染信号的相关系数只有 0.004657；Lasso 给 label 的系数是
**0.99964**，六个真因子系数**全部恰好为 0** —— 模型退化成恒等映射 y=y，回测读数
是一台印钞机，实盘一根 bar 都对不上。

**注意题面那条更直觉的猜想是【错的】**：「没有 set_label → 最后一个特征被静默丢掉」
实测三条路径全部大声报错（`ColumnNotFoundError` / LightGBM 的 feature count
mismatch）。**静默不来自列数错，只来自列数对、身份错。**

改法是加一条按【名字】的共同判据 `feature_names()` / `select_features()`（放在
`dataset/template.py`，因为 label 这个概念归 `AlphaDataset` 所有）。推理侧刻意**不**
重新推导名单，一律用训练时记下的名字取列 —— 这样 `predict` 反而能接受合法地没有
label 的实盘帧（前瞻标签在最新一根 bar 上不可能存在），而旧写法在那种帧上会丢掉
最后一个特征、再以一句只字不提 label 的 shape 错误挂掉。

**不需要重训任何存量产物。** LgbModel 的名字直接读 Booster 自己记下的
`feature_name()`（`_prepare_data` 传的是 pandas 帧，所以每个已落盘的 Booster 里都
有），Lasso / MLP 的 `self.feature_names` 本来就在 fit 时存了。实测：加载上一次
`run_example.py` 落盘的 dataset.pkl + model.pkl（158 特征 Booster、161 列
infer_df）重跑 predict，1340 行信号与当时保存的 signal parquet **逐值相同、最大
偏差恰为 0.0**。

### 3. 四份 notebook 传的 `hold_thresh` 是上游的哑弹，本仓把它变成了响弹

`EquityDemoStrategy` 的参数名从上游起就叫 `min_days`，`hold_thresh` 是上游 notebook
从 qlib 抄来的错名。而上游 `AlphaStrategy.__init__` 写的是
`if hasattr(self, k): setattr(...)` —— 未知键静默丢弃。

**它之所以活到今天，是因为 `min_days` 的类默认恰好也是 3**：想设的值与默认值撞在
一起，「配置没生效」与「生效了」跑出来的结果**逐位相同**，没有任何观测能把两者
分开。语义 v1 那轮把那个循环换成未知键直接 raise（`template.py:43-49`）—— 那是对
的，但它同时把四份随包发布的 notebook 打断在 `engine.add_strategy(...)`。

实测：只换数据坐标（10 处，逻辑一行不动）指向 `hk_bluechip_10`，lgb 一路跑到
**cell 33** 才死在这里；改名之后三份从头跑到 cell 34 全过，lgb 出真回测（134 个
交易日、**338 笔成交**）。顺带把 `mlp_model.py` 的 `input_size : int, default 360`
改掉 —— 那是 qlib Alpha360 的遗留，而签名里它一直是**必填位置参数**。

**一条不是 vnpy 的坑，但会咬人**：同一进程里先 `import lightgbm` 再用 torch，本机
必挂 —— 一次死锁在 `__kmp_join_barrier`（`sample` 抓到栈，10 分钟零进展），一次段
错误退出码 139。两份 libomp。一份 notebook 一个模型碰不到；**把多份塞进同一个
Jupyter 内核依次跑就会碰到**。

### 验证

```bash
cd vnpy && MPLBACKEND=Agg ../vnpy/.venv/bin/python -m pytest tests -q   # 205 -> 229 passed
```

新增三份用例共 24 例（`test_logger_sink_isolation.py` 9 /
`test_model_label_column.py` 9 / `test_notebook_strategy_settings.py` 6）。
`ruff check .` 全绿；`mypy vnpy` 的 2 个错误与改动前**逐字相同**（`qt.py:39`
windll、`chart/item.py:122` unused-ignore，都在未触碰的文件里）。

变异验证三轮：① `logger.py` 退回上游原样 → 9 例里 7 例红（诚实说法是 **6 例回归 +
1 例弱证据** —— 有一条红在 `AttributeError: 没有 _configure_default_sink`，那是找不
到助手而不是抓到缺陷；另 2 例绿是**故意的不变量锁定**）；② **只删 `remove()`、不做
占用检查** → 4 例红，那正是「上游为什么 remove」这个问题必须被回答的地方；③
`feature_names` 的返回改回 `list(df.columns[2:-1])` → 2 例红。

## 明确决定【不放进本仓】：walk-forward 的 purge / embargo 与逐日 rank IC

落在 `vnpy_alphakit/folds.py`（543 行）而不是 `vnpy/alpha/`，本仓这一条**一行未改**，
记在这里是因为它是「加能力」里唯一一条**判断落在仓外**的。

**缺陷本身是真的。** `AlphaDataset` 把三段日期原样交给 `query_by_time`
（`dataset/template.py:274`），段与段**首尾相接**，而 Alpha158 / Alpha101 的标签是
`ts_delay(close, -3) / ts_delay(close, -1) - 1` —— 跨 3 天。实测
`lab/hk_bluechip_10`：train 收在 2025-06-30，把 artifact 的 `raw_df.label` 与手算
`close[2025-07-04] / close[2025-07-02] - 1` 并排比，**10/10 只票逐位相同（8 位小数），
两个价格都在 valid 段**；train 4750 行里 30 行、valid 1260 行里 30 行如此。

**不放进本仓的理由**有两条，都是结构性的。其一，判官用的 `newey_west_se` 在
`vnpy_alphakit/prereg.py`，而依赖 DAG 单向 —— 内核不能 import 卫星，放进来就得
**复制一份必须与判官逐位一致的估计量**，那正是 `prereg.py` 整段散文要否掉的东西。
其二，`data_periods` 是公开 dict，purge 不必发生在 `fetch_learn` 内部（四种切法的
复现全靠改这个 dict 完成，生产代码零改动）。**代价是**：上游若把这条能力做进
`AlphaDataset`，我们这边会与它重叠，届时 purge 算术该搬回内核。

⚠️ **不要把「泄漏幅度」记成 +0.0493。** 那是单切分上「无 purge +0.0331」与
「purge=3 +0.0824」的差，**方向还是反的** —— 删掉 30 行泄漏样本不该【提高】样本外
读数。做了 30 个安慰剂（删 train 段任意互不重叠的 3 天）：零分布均值 +0.0632、
sd 0.0266、跨度 +0.0080~+0.1151，**真 purge 落在 21/30 分位，单侧经验 p = 0.300**。
LgbModel 的 `seed` 在此完全不起作用（10 个种子逐位相同，sd 0.0000 —— `params` 里
没有 bagging / feature_fraction）。传导路径是**早停**：`best_iteration` 在这些扰动
下取遍 1..30。所以正确的记法是：**泄漏是结构性事实，幅度在这个面板上不可测，因为
单切分读数自身的分辨率（±0.027）比要争的效应还大** —— 这也是为什么只补 purge 而
继续读单切分等于没做。

## 回测引擎的可用现金不再返回负数 —— long-only 的 demo 策略曾会开出空头

**改哪里**：`vnpy/alpha/strategy/backtesting.py` 的
`BacktestingEngine.get_cash_available`，函数体从 `return self.cash` 改成
`return max(self.cash, 0.0)`，下面这条链写进该方法的注释。

**上游原行为**：`return self.cash`，从上游至今一字未改。它读起来像一次余额查询，
但**所有调用方都把它当预算花**：`AlphaStrategy.get_portfolio_value()` 拿它当现金项，
`equity_demo_strategy.on_bars` 直接 `cash * cash_ratio / len(buy_symbols)` 切给每只
待买的票。**「余额是负的」与「不要买」在这条路上不是同一件事** —— 后者是 0，
前者是【买负的量】。

**账为什么会先变负**：`cross_order` 的扣减是无条件的，而策略按 bar 收盘价编预算、
按 `close * (1 + price_add)` 挂单，再把股数**向上**取整到整手。合成小面板上实测：
1 万本金、9500 预算、50.00 的票算出 190 股，`round_to` 给回 200 股，成交价 52.50
加 13.65 手续费花掉 10513.65 —— 账上剩 **-513.65**。透支不是异常路径，是常态。

**实测的失效**（`lab/hk_bluechip_10`，10 只港股，2026-01-02 ~ 2026-07-22，本金
1_000_000，`top_k=3 / n_drop=1 / min_days=3`，滑点 5bp。逐 bar 驱动 `new_bars` 而
不走 `run_backtesting` —— 后者的宽 except 会把回测静默截断成一段假读数）：

* **负现金 24 根 bar，最低 -21526.24。** 2026-02-05 那根上 `get_cash_available()`
  返回 **-20689.95**。
* 预算除以股价得 -123.952491，`round_to(-123.952491, 100)` 返回 **-100.0**。
  `round_to` 是 Decimal 量化、**对符号没有意见**，闸建不到那里去。
* `set_target(9988.SEHK, -100.0)`；`execute_trading` 读 `diff = target - pos`，
  `pos == 0` 时走 `diff < 0` 分支，`short_volume = abs(diff)`，调 `self.short()`。
  **一个 long-only 的 demo 策略开出了空头** —— 不抛异常、不写日志、不产生拒单。
* ⚠️ **负 target 有两个计数口径，别混。** `set_target` 收到负值 **1 次**；逐 bar 扫
  `target_data` 会数成 **3** —— 那个值留在字典里直到下一轮被覆盖。两个数都对，
  但答的不是同一个问题，转述时要带口径。
* **残留比空头本身活得久。** `on_trade` 只在 `Direction.SHORT` 时 pop
  `holding_days`，所以把空头平掉的那笔 `cover` 不清计数器；而 `on_bars` 一路在加，
  因为 `if pos` 对 -100 为真。实测计数器**冻在 3、跨 23 根空仓 bar**。于是下一次
  真买入（2026-03-19 成交）在它的**第一天**就已经越过 `min_days`，2026-03-20 就被
  卖掉 —— **`min_days=3` 之下持有 1 根 bar**。
* 同一份数据加上这道闸：负 target 0 次、`short()` 0 次、冻结 0 根、最短持有回到
  3 根。

**这治的是症状不是账，而且是故意的。** `self.cash` 该负还是负 —— 扣减无条件，
这一行碰不到它；实测**加闸之后负现金 bar 反而更多（38 根 vs 24 根，最低
-21292.75）**，因为不再被负预算压住的买单买得更多。又因为
`AlphaStrategy.get_portfolio_value() = get_cash_available() + get_holding_value()`，
这道闸让透支账户的组合价值被**高报**而不是低报 —— 方向是 fail-open。两害相权取
其轻：另一头是策略拿一个负数去算仓位。**真正的根因在叶子层** —— 按真实会成交的
价格编预算、把股数向下取整到整手，让预算根本不被打穿 —— **那是改策略不是改引擎，
是另一笔**。

**为什么不是别的改法。** 「让 `cross_order` 拒绝把 cash 扣成负数」会把一笔已按
市场规则成交的单子改成没成交，回测的成交序列从此不可复述；透支是**事实**，该被
记下来而不是被撤销。「在 `set_target` 里拒绝负值」则站错了层：那个位置只看得见
一个数，分不清它来自负预算还是来自策略真想做空，而 `AlphaStrategy` 是 long/short
都支持的模板，`short()` / `cover()` 就在它身上。

**实盘一直有护栏、回测没有**：`vnpy_alphakit/vnpy_alphakit/live.py:1632` 是
`max(lookup.equity - self.get_holding_value(), 0.0)`。两条路径对「可用现金」的定义
不一致时，**回测读数不可迁移到实盘**；这一行是把它们对齐。

### 爆炸半径

网格 48 配置 = `top_k{2,3,4,5} × n_drop{1,2} × min_days{2,3,5} × slippage{0, 5bp}`，
面板与上面同一份。挑这四个维度是因为前三个直接决定换手率与每笔预算的规模（也就是
现金被打穿的频率），slippage 决定每笔成交的现金消耗，四个都是 `run_example.py` 里
用户真会去改的旋钮；本金与 universe 固定，改它们等于换实验。改前 / 改后各跑一遍：

| 读数 | 值 |
|---|---|
| \|Δ总收益\| 均值 | **6.5431 pp** |
| \|Δ总收益\| 最大 | **19.1538 pp** |
| \|Δ总收益\| 中位 | 5.4629 pp |
| \|Δ\| 恰为 0 的配置 | 1 / 48 |
| Spearman 排名相关系数 | **+0.4540** |
| A 臂有空头污染的配置 | **32 / 48**（SHORT/OPEN 成交共 78 笔） |
| B 臂有空头污染的配置 | **0 / 48** |

**A 表的第 1 名在 B 表是第 16 名，而且从 +6.99% 变成 -8.32%** —— 那正是上面逐环
追下来的那个配置。排名移动最大的一个是 `top_k=4 / n_drop=1 / min_days=3 /
slip=0`：A 表 **#46 → B 表 #10**（-22.52% → -5.91%）。**改前那张表选出来的「最优
参数」，在改后那张表里是一个亏钱的配置** —— 这就是为什么它不是一次「小数点后的
修正」。

⚠️ **这个 A/B 不是最小扰动：空头污染与仓位规模变化混在一起，没拆开。** 闸同时改了
两件事 —— 不再产生负 volume（空头），以及在 cash 为负的 bar 上把预算从负数抬到 0
（所有买单的仓位规模）。实测能证明两者都在、但分不开各自的贡献：**A 臂一笔空头都
没有的 16 个配置里，15 个照样变了**，它们的 |Δ| 均值 3.9902 pp、最大 19.1538 pp ——
**全网格最大的那个 |Δ| 恰恰来自一个零空头污染的配置**。要拆开就得再造一臂「只压住
负 volume、预算仍按负 cash 算」的人造中间态，本轮没做，代价是上面那三个数回答的是
「换掉这一行的总影响」而不是「空头污染的影响」。

**这些数字量的是这一个面板**（10 只港股、134 个交易日、一份信号），不是这条缺陷的
一般幅度。网格的坐标轴写在上面而不是只写结论，正因为读数是随网格变的 —— 换 universe
或换信号，量级会变。

### 验证

```bash
cd vnpy && MPLBACKEND=Agg ../vnpy/.venv/bin/python -m pytest tests -q   # 229 -> 238 passed
```

新增 `tests/alpha/test_cash_available_floor.py` 9 例。面板是手写的 3 只票 × 8 根
bar，不碰 lab、不读 parquet：`FakeLab` 只实现 `load_contract_setttings`，
`load_bar_data` **故意不实现** —— 将来有人把它改成读真数据会立刻报错，而不是静默
生效。`ruff check .` 全绿；`mypy vnpy` 的 2 个错误与改动前**逐字相同**
（`qt.py:39` windll、`chart/item.py:122` unused-ignore，都在未触碰的文件里）。

变异验证：把 `max(self.cash, 0.0)` 改回 `self.cash` → **9 例里 4 例转红**（可用现金
本身、不得开空头、不得出负 target、持有期不得短于 `min_days`），还原后 9 例全绿。
**另 5 例在变异下故意保持绿**：`test_the_panel_overdraws_...` 锁的是「面板确实透支」
这个前提（两臂都该绿，它一旦红说明面板失效而不是缺陷复现），
`test_reverting_the_floor_...` 自己就把闸 monkeypatch 掉了。

其中一例的第一版是**假绿**，记在这里免得后来者重走：
`test_no_target_is_ever_negative_...` 原本读回放结束后的 `strategy.target_data`，
而 target 会被下一轮覆盖 —— 变异之下末态字典里一个负值都没有，用例照样通过。改成
`RecordingTargets` 包住 `set_target` 逐次记录，才真的抓得到那 1 次。

## 已知没做的事

本仓不留待办标记 —— 以下是明确决定「现在不做」的条目，连同代价。

**`processor.py` 里同款位置切片还有 7 处**（`columns[2:-1]` 5 处、`columns[2:]`
2 处）。实测无 label 的帧过 `process_robust_zscore_norm`，最后一个特征 `ma_20`
被**静默跳过、不归一、不报错**；另有一条同源的：特征若恰好叫 `mean` / `std` /
`mad`，`process_cs_norm` 的临时列同名，先覆盖再 drop，**整列特征被静默删掉**
（实测 `[datetime, vt_symbol, kmid, mean, label]` → `[datetime, vt_symbol, kmid,
label]`）。**不修的理由**是它们与上面第 2 条同源但触发路径不同，混在一笔里会让
变异验证说不清归属。**代价是**：Alpha158 / Alpha101 恰好没有这三个列名，所以今天
不触发 —— 换一套特征集就触发，而且不响。

**`equity_demo_strategy.on_trade` 只在 `Direction.SHORT` 时 pop `holding_days`，
这条不对称保留原样。** 上面那一节切断的是【产生空头的那条路】，不是计数器本身：
只要有任何一条路径让 `pos` 变负，把它平掉的 `cover` 走 `Direction.LONG`，计数器
就仍然会留在原地（实测冻结 23 根 bar，随后一次 `min_days=3` 的持仓只活了 1 根
bar）。**不修的理由**：`AlphaStrategy` 是 long/short 都支持的模板，正确的语义是
「仓位回到 0 时清计数」而不是「卖出时清计数」，改它要动的是 `on_trade` 的判据本身，
而本轮的验证数字全部建立在「long-only demo 不该有空头」这个前提上，混进一笔会让
变异验证说不清归属。**代价是**：`get_cash_available` 这一道闸是目前唯一挡着它的
东西 —— 换一个会做空的策略，`min_days` 立刻又不是硬闸。

**买入预算仍然按 bar 收盘价编、股数仍然向上取整到整手。** 这才是把 cash 打穿的
根因（实测 1 万本金一笔买单花掉 10513.65），上面那道闸只是不让透支额再变成负
volume。**不修的理由**：那是叶子层的策略语义（按真实会成交的价格编预算、向下取整），
改它会改掉每一个既有回测的成交序列，属于另一笔带自己一组验证数字的改动。
**代价是**：负现金依旧发生，而且加闸之后更频繁（38 根 vs 24 根）。

**`vnpy/trader/logger.py:40` 那句宽的 `logger.remove()` 原样保留。** 它对称地会
扫掉任何在它之前装的 sink。**不修的理由**：今天不构成故障（没有生产代码在 trader
之前配 loguru，而「alpha 先、trader 后」正是靠它得到正确结果），而收窄它会立刻换来
双控制台输出 —— 要一起修就得把 trader 的 stdout sink 也做成条件式，那是另一笔改动、
另一组验证数字。

**`BacktestingEngine.show_performance` 的基准是按【位置】拼进 daily_df 的**
（`backtesting.py:463-479`），而 `load_bar_data` 缺文件时只 `logger.error` 返回 `[]`。
长度不等时报的 `ShapeError: unable to add a column of length 0 to a DataFrame of
height 134` **一个字不提基准缺失**；长度相等而交易日不同时**静默错位**。
**不修的理由**：它在本轮射程外，且修法牵涉 daily_df 的拼装口径。**代价是**：任何
带 benchmark 的 `show_performance` 读数，在基准与策略交易日不一致时是错的且不报。

**`lab.py:302` `load_component_data` 的裸 `@lru_cache` 挂在实例方法上** —— 键含
`self` 而 `save_component_data` 不失效。实测同一进程「读 → 改台账 → 再读」拿到旧
名单，只有换 `AlphaLab` 实例才看得到新的；而 `run_example` 正是「`define_basket`
写完立刻读 filters」这个顺序。同源第二条：`lab.py:290` 的 `save_component_data` 用
`db.update(...)` 是**合并而非替换** —— 改了区间再跑一次 `define_basket`，旧快照原地
留下，台账变成两代混合（实测三次写入后 shelve 里是 3 个键）。**不修的理由**：
`vnpy_alphakit` 侧的 `load_component_filters_strict` 已经用 `cache_clear()` 把第一
条对本链路的影响挡住了 —— **挡住不等于修好**，这句要留着。**代价是**：任何直接用
`AlphaLab` 而不走那个包装的调用方，仍然会读到进程内的陈旧台账。

✅ **停牌日 NaN 被比较运算判出方向 —— 已在「语义 v2」那一节清掉。** 上一版这里
写的「`cnt*` 会开始系统性高估上涨天数」**是错的描述**，更正见那一节：一次停牌
同时伪造一个涨日、抹掉复牌那天真实的涨，偏差不是单边的。上一版「本轮不修」的
理由（会让「恰好 15 列变化」说不清归属）在 Alpha101 那一轮结束后就不成立了。

✅ **`run_live_alpha.py` 的裸 traceback —— 已在 `vnpy_app` 那边接上。**
`vnpy_app/run_live_alpha.py` 现在把 `AlphaSemanticsError` 捕成
`EXIT_STALE_SIGNAL = 6` 加三行中文提示，并有 6 条用例钉住「拒绝发生在
`build_main_engine()` 之前」。**顺序不是随意的**：那一笔必须先于本仓的 v2 落地，
因为戳一推到 2，所有既有 signal 当场开始加载失败 —— 没有它，实盘入口第一次撞上
这道闸时看到的是一屏栈。

**`vnpy_alphakit/run_example.py:183/189` 的 `load_dataset` / `load_model` 仍然
没有 try。** 与上面那条同形，但那是研究脚本、不在下单链上。**不接的理由**：它
退出非零、不碰网关，而一个宽捕获会把真缺陷伪装成运维退出码。**代价是**：戳推到
2 之后它会开始裸 traceback。要接就单独一笔。

**`imax_*` / `imin_*` / `imxd_*`（15 条）与 `wvma_*`（5 条）同样在停牌日吞 NaN**，
但机理与 v2 那条无关：`Series.arg_max` / `arg_min` 跳过 NaN，`ts_mean` / `ts_std`
走 `np.nanmean` / `np.nanstd`。**不修的理由**是它们属于【遗漏】而非【伪造】——
算子不看那个停牌日，而不是给它编一个方向。**代价是**：接入有停牌市场后这 20 列
按「窗口内可见样本数」而非「窗口长度」计算，口径与文档不符。

**`beta_60` / `rsqr_60` / `resi_60` 不是逐位可复现的**（`pl.sum_horizontal` 折叠
60 个 shift 列，polars 并行归约加法次序每次不同；同代码连跑两遍实测 `rsqr_60`
差 4.3e-14 / 150 行，另一轮量到的是 `beta_60` 4.15e-17 与 `resi_60` 1.33e-15）。
**不修的理由**：要在热路径上强制有序归约，为 1e-14 付这个价不值。**代价是**：
任何「重算是否等价」的对拍对这三列必须用 `rtol=1e-9`，写成精确相等就会红在一个
与改动无关的地方。⚠️ **而且哪几列会漂是不定的** —— 有的面板上一列都不漂
（50 票 × 800 天工作树侧连跑两遍 moved 0 / 158）。所以「这次跑出来是 0」**不能**
推出「它是确定的」；要判断一处差异是不是改动造成的，正确做法是**同侧连跑两遍**
再对拍，而不是看它小不小。

**`tests/test_alpha101.py` 那 100 条断言仍然全是 `assert "data" in result.columns`。**
**不改的理由**是它是上游文件，而本仓的分线是「加能力放独立文件」——
值级回归网已经另起在 `tests/alpha/test_alpha101_health.py`。**代价是**：那 100 条
绿**不构成任何正确性证据**，看见它们全绿不要当成 Alpha101 没问题；引用判据要引
新文件与「收尾一轮」那节的表。

**列级筛查抓不到 `quesval2` 那类方向反转。** 隔离实测：反转后 82 列里 11 列变值，
而量级 / 缺失率 / distinct / flat 四项**一项都不变**。**不修的理由**是没得修 ——
这是筛查方法的固有上界，不是哪段代码的缺陷。**代价是**：所有「比较方向」类缺陷
必须靠直接操作符测试守，健康读数在这个方向上给不出任何保证。

**Alpha101 的四个算子缺陷已经清掉** —— `cs_rank` 改成分位、`quesval2` 的比较
方向改正、`pow2` 与 `pow1` 不再把无定义写成 0。上一轮这里记的三条判断有两条要
更正：`pow2` 的 `1e84` **不是 `pow2` 的缺陷**，`8.88e+84` 就是 `50**50`，根因在
`cs_rank`；`alpha96` 的 46.5% NaN **不是缺陷**，是宇宙太窄导致秩序列在短窗口上
恒定、`ts_corr` 无定义，属数据性质。

⚠️ **但「Alpha101 已可用」这句话本身也要限定**，判据见「收尾一轮」那节：无停牌
面板 **80 / 82**，有停牌面板 **75 / 82**，而且有停牌面板上四条长窗口列
（alpha19 / 39 / 52 / 36）的缺失率涨到 63%~74%。**算子缺陷清完了，剩下的是面板
条件** —— 需要够宽的截面（十票不够）与够长的历史（250 天窗口要 800 天以上），
并且长窗口那四条在有停牌的市场上基本不能用。

**`cs_mean` / `cs_std` / `cs_sum` / `cs_scale` 不跳过 NaN**，一只票停牌就把当天
整个截面变成 NaN（实测 `alpha28` 首个日期十票全 NaN）。**不修的理由**是它
fail-closed，产出的是 NaN 而不是一个像样的错数 —— 与已修的三条性质相反。**代价
是**：接入有停牌的市场后，`cs_scale` 系列（alpha28/29/31/32/60）会按停牌票数
成比例地丢日期。修的时候单独一笔，带自己的逐列对拍。

## 本仓的验证命令

CI（`.github/workflows/pythonapp.yml`）是 windows-latest + Python **3.13**，装
`.[alpha,dev]`，顺序为 `ruff check .` → `mypy vnpy` → `pytest tests -q` →
`uv build`。本机只有 3.14，**本地绿不等于 CI 绿**。

```bash
cd /Volumes/ORICO/Developer/vnpy-workspace/vnpy
../vnpy/.venv/bin/ruff check .                      # All checks passed!
../vnpy/.venv/bin/mypy vnpy                         # 恰好 2 个既有错误，不加 --strict
../vnpy/.venv/bin/python -m pytest tests -q         # 205 passed
```

用例数的对照基线是 **110**（特征语义 v1 之前）。v1 那一轮加到 **165**，分布是
`test_ts_function_dtype.py` 11 / `test_load_bar_df_vwap.py` 4 /
`test_semantics.py` 23 / `test_mlp_model.py` 17。Alpha101 算子那一轮再加 20：
`test_cs_rank_percentile.py` 7 / `test_quesval2_direction.py` 6 /
`test_pow2_undefined.py` 7，合计 **185**。语义 v2 那一轮再加 10：
`test_suspended_day_comparison.py` 10，合计 **195**。收尾那一轮再加 10：
`test_alpha101_health.py` 5（新文件）/ `test_pow2_undefined.py` +3（`pow1`）/
`test_suspended_day_comparison.py` +1（停牌长度边界）/ `test_semantics.py` +1
（无戳报错要讲全），合计 **205**。**收集数低于 205 就是有 collect error**，不是
「少写了几条」。

⚠️ 跑门禁前先确认工作树是静止的。本轮复核踩过一次：变异验证正在另一个进程里
跑（`mlp_model.py` 50 秒内出现 5 个不同哈希），三次全量跑给出 159 / 3 failed /
3 failed 三个结果。变异验证是「改坏 → 跑 → 还原」，中途被 kill 就会把文件留在
坏状态**而 `git status` 看不出异常**（它本来就是 M）。稳妥做法是先对
`lab.py` / `ts_function.py` / `mlp_model.py` / `semantics.py` 取一轮 `shasum`，
确认连续不变，再跑。

`mypy vnpy` **不加 `--strict`**（CI 也没加）。那 2 个既有错误是
`trader/ui/qt.py:39` 的 `windll` 与 `chart/item.py:122` 的 unused-ignore —— 多一条
就是自己引入的。

`pytest` 必须**显式写 `tests`**：本仓没有 `[tool.pytest.ini_options]`，裸跑会从
cwd 全量收集。
