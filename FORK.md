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

## 语义版本与产物的绑定规则

`vnpy.alpha.semantics.FEATURE_SEMANTICS_VERSION` 与 `vnpy/__init__.py` 的
`__version__` local 段（`4.4.0+hexonal.N`）**必须同步递增**。

🔴 **回滚算法时必须连常数一起回滚。** 闸做的是**相等比较**不是大小比较，所以退回
旧算法却留着新常数 → 新存的产物带新戳、旧代码算的却是旧口径，闸会放行一批错的
东西。**这是整个方案里唯一能把闸从保护变成危害的路径。**

单独回滚闸（`semantics.py` + `lab.py` 六处接入）是安全的，任何时候都可以，代价
只是失去保护、不会产生错值。反过来单独回滚算法而留下闸 = 上面那个坑。

| 版本 | 这一版改了什么 | 哪些既有产物因此作废 |
|---|---|---|
| v0 | 上游 vnpy 4.4.0 语义：vwap 未归一化、五个滚动算子截断整数输入 | 一切在本模块之前建的产物；它们不带戳 |
| v1 | vwap 与价格同除 `close_0`；`ts_rank`/`ts_mean`/`ts_std`/`ts_quantile`/`ts_decay_linear` 入参转 Float64 | v0 下建的全部 dataset pkl / model pkl / signal parquet |

## 已知没做的事

本仓不留待办标记 —— 以下是明确决定「现在不做」的条目，连同代价。

**polars 里 `pl.Series([nan]) > 1` 返回 `True`**（numpy 返回 False），而
`lab.py:260-266` 刻意把停牌日写成 NaN。于是停牌日会被
`close > ts_delay(close, 1)` 记成上涨日 —— 今天被整数截断盖住（截断后整窗口全 1
才留 1），修完 dtype 就变成一个活的错数。

**本轮不修**，理由：实测 HK 与 US55 两个 lab 的停牌行数都是 **0**（当前是潜伏
态），而改比较语义会再动一遍 143 条健康列的口径，让本轮「恰好 15 列变化」这条
验证数字说不清归属。**代价是**：一旦接入有停牌的市场，`cnt*` 会开始系统性高估
上涨天数。修的时候应当单独一笔提交，并重新跑一次全量列对拍。

**`run_live_alpha.py` 现在会以裸 traceback 退出，本轮不接。**
`vnpy_app/run_live_alpha.py:229` 的 `signal = lab.load_signal(args.basket)` 外面
没有 try/except，所以老信号会让 `AlphaSemanticsError` 一路冒到顶层。方向是对的
—— 实跑确认它断在 `build_main_engine()`（:238）**之前**，没有网关被构造、没有
connect、没有任何委托，是 fail-closed 里最安全的位置；难看的只是运维看到的是
traceback 而不是紧邻下面那段写好的中文提示 + `return 2`。

**本轮不接**，理由：那是 `vnpy_app` 仓、有自己的 CI 与 292 例测试，而
`run_live_alpha.py` 是实盘下单入口 —— 就算只动它的起飞前检查，也该是一笔单独
的、有人盯着的改动，不该搭在特征语义这趟车上。**代价是**：在有人补那个
try/except 之前，跑 `run_live_alpha.py` 拿老 basket 会看到一屏栈。补的时候连
`vnpy_app/tests` 一起补一条「未盖戳的 signal 让入口以 2 退出且不构造
MainEngine」。

**Alpha101 仍不可用**，修 vwap 是必要不充分条件。修完之后它还有三个与 vwap 无关
的独立缺陷：`cs_function.py:10-17` 的 `cs_rank` 是 `rank()` 的 1..N 序号而不是
WorldQuant 定义的 [0,1] 分位（82 条活跃表达式里 62 条受影响，**特征量级随宇宙
大小变**）；`pow2(rank, rank)` 在 50 票面板上溢出到 **1e84**（alpha78/84/85/94
四条）；`alpha96` 在干净的 50×300 面板上仍有 **46.5% NaN**。所以本轮的正确表述是
「Alpha101 的 22 条 vwap 特征从错值恢复成对值、alpha92 从常数恢复成特征」，
**不是**「Alpha101 修好了」。

## 本仓的验证命令

CI（`.github/workflows/pythonapp.yml`）是 windows-latest + Python **3.13**，装
`.[alpha,dev]`，顺序为 `ruff check .` → `mypy vnpy` → `pytest tests -q` →
`uv build`。本机只有 3.14，**本地绿不等于 CI 绿**。

```bash
cd /Volumes/ORICO/Developer/vnpy-workspace/vnpy
../vnpy/.venv/bin/ruff check .                      # All checks passed!
../vnpy/.venv/bin/mypy vnpy                         # 恰好 2 个既有错误，不加 --strict
../vnpy/.venv/bin/python -m pytest tests -q         # 165 passed
```

用例数的对照基线是 **110**（本轮之前）。165 − 110 = **55 例新增**，分布是
`test_ts_function_dtype.py` 11 / `test_load_bar_df_vwap.py` 4 /
`test_semantics.py` 23 / `test_mlp_model.py` 17。**收集数低于 165 就是有 collect
error**，不是「少写了几条」。

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
