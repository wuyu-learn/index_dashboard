# 交易日历

## 接口信息

| 项目 | 内容 |
| --- | --- |
| 接口名称 | `trade_cal` |
| 描述 | 获取各大交易所交易日历数据，默认提取上交所交易日历 |
| 在线调试 | [Tushare 数据工具](https://tushare.pro/webclient/) |
| 积分要求 | 需要 2,000 积分 |

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| `exchange` | `str` | 否 | 交易所代码；默认为上交所。支持 `SSE`、`SZSE`、`CFFEX`、`SHFE`、`CZCE`、`DCE`、`INE` |
| `start_date` | `str` | 否 | 开始日期，格式为 `YYYYMMDD` |
| `end_date` | `str` | 否 | 结束日期，格式为 `YYYYMMDD` |
| `is_open` | `str` | 否 | 是否交易：`0` 表示休市，`1` 表示交易 |

## 交易所代码

| 代码 | 交易所 |
| --- | --- |
| `SSE` | 上海证券交易所 |
| `SZSE` | 深圳证券交易所 |
| `CFFEX` | 中国金融期货交易所 |
| `SHFE` | 上海期货交易所 |
| `CZCE` | 郑州商品交易所 |
| `DCE` | 大连商品交易所 |
| `INE` | 上海国际能源交易中心 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| `exchange` | `str` | 是 | 交易所代码，例如 `SSE`、`SZSE` |
| `cal_date` | `str` | 是 | 日历日期，格式为 `YYYYMMDD` |
| `is_open` | `str` | 是 | 是否交易：`0` 表示休市，`1` 表示交易 |
| `pretrade_date` | `str` | 是 | 上一个交易日，格式为 `YYYYMMDD` |

## 接口示例

```python
import tushare as ts

pro = ts.pro_api()

# 获取默认交易所（上交所）2018 年交易日历
df = pro.trade_cal(
    exchange="",
    start_date="20180101",
    end_date="20181231",
)

# 通过通用 query 方法获取
df = pro.query(
    "trade_cal",
    start_date="20180101",
    end_date="20181231",
)

# 仅获取指定区间内的交易日
df = pro.trade_cal(
    exchange="SSE",
    start_date="20180101",
    end_date="20181231",
    is_open="1",
)
```

## 数据示例

| exchange | cal_date | is_open |
| --- | --- | ---: |
| SSE | 20180101 | 0 |
| SSE | 20180102 | 1 |
| SSE | 20180103 | 1 |
| SSE | 20180104 | 1 |
| SSE | 20180105 | 1 |
| SSE | 20180106 | 0 |
| SSE | 20180107 | 0 |
| SSE | 20180108 | 1 |
| SSE | 20180109 | 1 |
| SSE | 20180110 | 1 |
| SSE | 20180111 | 1 |
| SSE | 20180112 | 1 |
| SSE | 20180113 | 0 |
| SSE | 20180114 | 0 |
| SSE | 20180115 | 1 |
| SSE | 20180116 | 1 |
| SSE | 20180117 | 1 |
| SSE | 20180118 | 1 |
| SSE | 20180119 | 1 |
| SSE | 20180120 | 0 |
| SSE | 20180121 | 0 |

## Demo 阶段 CSV 存储约定

- 建议路径：`data/raw/trade_cal/{exchange}.csv`
- 文件粒度：每个交易所一个文件，保存完整交易日历
- 唯一键：`exchange + cal_date`
- 日期字段 `cal_date` 和 `pretrade_date` 保留为 `YYYYMMDD` 字符串
- `is_open` 保留为字符串 `0` 或 `1`
- 增量更新时应覆盖未来一段时间的日历，以纳入节假日安排调整
- 写入前与已有数据合并，按唯一键去重并按 `cal_date` 升序排列

## 使用建议

- 判断某天是否为交易日时，应读取 `is_open`，不要只按工作日或星期判断。
- 获取最新完整交易周时，可先从交易日历筛选开放日，再确定该周最后一个交易日。
- 股票指数通常可使用 `SSE` 日历；涉及期货品种时，应使用对应期货交易所的日历。
- `pretrade_date` 可用于寻找上一交易日，避免自行处理周末和法定节假日。
