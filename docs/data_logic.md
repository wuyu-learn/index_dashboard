# ETF Dashboard 数据逻辑

## 当前目标

项目跟踪一份人工整理的 ETF 相关指数池，并获取这些指数的周线行情。

由于当前 Tushare 账号没有 `etf_basic`、`etf_index` 和 `index_basic` 等高积分接口权限，项目不再依赖这些接口生成指数池。

## 数据源

### 本地指数池

源文件：

```text
data/data_result_fixed.xlsx
```

工作表需要包含：

| 原字段 | 项目字段 | 说明 |
| --- | --- | --- |
| `f_code` | `index_code` | Tushare 指数代码 |
| `ts_code` | `index_code` | 从 `index_basic` 匹配得到的官方调用代码，优先使用 |
| `f_name` | `index_name` | 指数名称 |
| `f_short_name` | `index_short_name` | 指数简称 |
| `f_pro_type` | `product_type` | 原始产品类型编码 |
| `Q` | `category_primary` | 一级分类 |
| `P` | `category_secondary` | 二级分类 |

当前文件有 483 行，其中 `000903.CSI` 完全重复一次。加入 `ts_code` 后，部分旧代码会映射到同一个官方代码，当前最终指数池为 479 个指数。

代码选择规则：

1. `ts_code` 有值时使用 `ts_code`；
2. `ts_code` 为空时回退到原 `f_code`；
3. 按最终使用的代码去重。

`ts_code` 来自 Tushare `index_basic`。匹配不到或无法唯一确认的记录保持空白，不写入猜测值。

### Tushare 周线

只调用：

```text
index_weekly
```

不再调用：

```text
etf_basic
etf_index
index_basic
fund_daily
etf_share_size
```

## 每周自动更新

整套任务每周六 `03:00` 开始，并严格串行执行：

```text
1. 读取 data_result_fixed.xlsx
2. 校验必要字段
3. 生成 tracked_indices.csv
4. 用 000001.SH 探测需要更新的实际周线交易日
5. 对每个交易日按 limit=1000、offset 递增分页
6. 保存完整日期快照 index_weekly_by_date/{trade_date}.csv
7. 优先按代码匹配指数池
8. 代码不一致时通过 index_basic 名称唯一匹配
9. 按指数合并历史并去重
10. 更新 tracked_indices.csv 中的周线状态
```

执行命令：

```bash
python -m backend.collector.runner sync-weekly
```

如果 Excel 缺失、字段不完整或无法读取，任务立即停止，不会开始调用 Tushare。

## 日期分页规则

`index_weekly(trade_date=...)` 可能返回超过 1000 条数据，因此必须分页：

```text
offset=0
offset=1000
offset=2000
...
```

当某页返回不足 1000 行时结束。所有页面合并后按 `ts_code + trade_date` 校验唯一性，并保存为：

```text
data/raw/index_weekly_by_date/{trade_date}.csv
```

周线日期不固定为星期五。程序通过 `000001.SH` 的区间周线自动发现真实交易日。

## 指数映射规则

完整日期数据与指数池按以下顺序匹配：

1. `index_code` 与行情 `ts_code` 完全匹配，忽略大小写；
2. 若代码不同，则通过本地 `index_basic.csv` 补充行情代码名称；
3. 标准化名称后仅有一个行情代码时建立映射；
4. 无法唯一确认时保持未匹配，不猜测代码。

映射保存为：

```text
data/processed/index_weekly_code_map.csv
```

例如：

```text
000811.CSI → 000811.SH
399975.CSI → 399975.SZ
931187.CSI → 399608.SZ
```

## 按指数保存规则

每个指数单独保存：

```text
data/raw/index_weekly/{index_code}.csv
```

例如：

```text
data/raw/index_weekly/000300.SH.csv
data/raw/index_weekly/000905.SH.csv
```

同步规则：

1. 首次日期分页从 `20260501` 开始。
2. 后续更新从本地最新周线日期向前回看 28 天。
3. 回看开始日期不得早于 `20260501`。
4. 原始行情代码保存在 `source_ts_code`。
5. CSV 主代码统一使用指数池中的 `index_code`。
6. 合并后按 `ts_code + trade_date` 去重并按日期升序保存。

周线交易日期是当周最后一个实际交易日，不固定为星期五。

## 指数池变更

需要新增或删除跟踪指数时，直接编辑或替换：

```text
data/data_result_fixed.xlsx
```

下一次周任务会重建指数池：

- 新增指数会从 `20260501` 开始初始化周线；
- 删除指数会停止后续更新；
- 已下载的历史 CSV 不自动删除；
- 修改名称或分类会反映到新的 `tracked_indices.csv`。

## 生成文件

```text
data/
├── data_result_fixed.xlsx
├── raw/
│   ├── index_basic/index_basic.csv
│   ├── index_weekly/{index_code}.csv
│   └── index_weekly_by_date/{trade_date}.csv
├── processed/
│   ├── tracked_indices.csv
│   └── index_weekly_code_map.csv
└── metadata/
    └── sync_state.json
```

`tracked_indices.csv` 包含：

| 字段 | 说明 |
| --- | --- |
| `index_code` | 指数代码 |
| `source_index_code` | Excel 原始 `f_code` |
| `ts_code` | `index_basic` 匹配结果 |
| `ts_code_matched` | 是否成功匹配官方代码 |
| `index_name` | 指数名称 |
| `index_short_name` | 指数简称 |
| `product_type` | 原始产品类型编码 |
| `category_primary` | 一级分类 |
| `category_secondary` | 二级分类 |
| `has_weekly_data` | 是否已有周线文件 |
| `last_weekly_trade_date` | 本地最新周线日期 |
| `source_file` | 指数池源文件名称 |
| `updated_at` | 指数池生成时间 |

## 当前决策

1. 本地 Excel 是指数池的唯一来源。
2. Tushare 只用于获取 `index_weekly`。
3. 每周六 `03:00` 先重建指数池，再按交易日分页更新周线。
4. 指数周线最早日期为 `20260501`。
5. 当前阶段不采集 ETF 日线、份额规模或 Tushare 基础信息。
6. 逐指数请求仅作为诊断工具，正式任务使用按日期分页。
