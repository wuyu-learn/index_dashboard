# ETF Dashboard

Demo 阶段使用本地 Excel 维护目标指数池，通过 Tushare 获取这些指数的周线行情。

## 初始化

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g mmx-cli
cp .env.example .env
```

编辑 `.env`：

```dotenv
TUSHARE_TOKEN=你的_token
INDEX_POOL_FILE=./data/data_result_fixed.xlsx
INDEX_WEEKLY_START_DATE=20260501
INDEX_WEEKLY_LOOKBACK_DAYS=28
MINIMAX_API_KEY=你的_key
MINIMAX_REGION=cn
```

真实 Token 只能放在 `.env`，不要写入 `.env.example` 或 Python 代码。

## 指数池

指数池源文件为：

```text
data/data_result_fixed.xlsx
```

代码会读取 `f_code`、`ts_code`、`f_name`、`f_short_name`、`f_pro_type`、`Q` 和 `P`。

- 有 `ts_code` 时使用 Tushare 官方代码；
- `ts_code` 为空时暂时回退到原 `f_code`；
- 最终按实际使用的指数代码去重。

生成：

```text
data/processed/tracked_indices.csv
```

重新下载 `index_basic` 并更新 Excel 时，匹配顺序为：代码完全匹配、代码主体与名称匹配、名称唯一匹配。无法唯一匹配的记录保持空白，不猜测代码。

只重建指数池、不调用 Tushare：

```bash
python -m backend.collector.runner sync-basic
```

## 每周自动更新

每周六 `03:00` 执行：

```bash
python -m backend.collector.runner sync-weekly
```

执行顺序：

```text
本地 Excel
→ 重建 tracked_indices.csv
→ 用 000001.SH 探测实际周线交易日
→ 按交易日分页获取全市场 index_weekly
→ 保存完整的日期原始快照
→ 按代码或唯一名称映射到指数池
→ 合并并保存每个指数的周线 CSV
→ 刷新指数池周线状态
```

`index_weekly` 单次最多返回 1000 行。程序使用 `limit=1000` 和递增 `offset` 自动翻页，直到最后一页不足 1000 行。

Linux cron 示例：

```cron
0 3 * * 6 cd /path/to/etf_dashboard && .venv/bin/python -m backend.collector.runner sync-weekly >> data/metadata/weekly-sync.log 2>&1
```

下面的逐指数命令保留用于诊断，不参与每周自动任务：

```bash
python -m backend.collector.runner sync-index-weekly
```

同步指定指数：

```bash
python -m backend.collector.runner sync-index-weekly \
  --end-date 20260619 \
  --index-code 000300.SH
```

周线最早从 `20260501` 获取；增量更新会回看最近 28 天，但不会越过该日期。

## 数据目录

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

`index_weekly_by_date` 保存 Tushare 当日完整原始结果，可在映射规则变化后重新处理。生成数据不会提交 GitHub；`data/data_result_fixed.xlsx` 被单独保留为项目输入文件。CSV 会先写临时文件，再原子替换目标文件。

## 分类强弱 Dashboard

根据当前 CSV 重新计算一级分类排名：

```bash
python3 scripts/build_dashboard_data.py
```

启动本地预览：

```bash
python3 -m http.server 4312 --directory designs
```

浏览器打开：

```text
http://127.0.0.1:4312/weekly-index-dashboard/dashboard.html
```

Dashboard 仅展示有行情的“行业主题”和“规模指数”，支持切换涨幅/跌幅以及最新一周/区间累计榜单。上方展示前三名，点击指数后会在下方各周前五排名矩阵中高亮其历史上榜位置；区间涨跌幅口径为首期昨收到末期收盘。

## 财联社收评采集

项目可在 A 股交易日采集当日财联社收评：

```bash
python -m backend.news.runner
```

指定日期重新采集：

```bash
python -m backend.news.runner --date 20260618 --force
```

执行流程：

```text
Tushare trade_cal 判断 SSE 是否交易
→ MiniMax Search 搜索“财联社 收评 财联社X月X日电”
→ 按目标日期与标题“收评”硬过滤候选
→ MiniMax 文本模型从合格候选中选择
→ 下载公开资讯页并提取正文
→ 保存 data/raw/market_review/{YYYYMMDD}.json
```

非交易日会直接跳过，不调用 MiniMax。正文抓取失败时保留搜索摘要，并将结果标记为 `partial`。
最终 JSON 只保存被选中收评的交易日期、发布时间、来源、标题、链接、完整正文、正文来源及采集时间；搜索候选和模型判断过程不落盘。

### 服务器定时执行

赋予脚本执行权限：

```bash
chmod +x scripts/run_market_review.sh
```

编辑服务器的 `crontab`：

```bash
crontab -e
```

按上海时区每周一至周五晚上 `20:00` 执行：

```cron
CRON_TZ=Asia/Shanghai
0 20 * * 1-5 /path/to/etf_dashboard/scripts/run_market_review.sh
```

请将 `/path/to/etf_dashboard` 替换为服务器上的实际绝对路径。脚本会优先使用项目 `.venv`，并将执行日志写入：

```text
data/metadata/market-review.log
```

周一至周五仍可能遇到法定休市日；任务会通过 Tushare `trade_cal` 判断，非 A 股交易日不会调用 MiniMax。
