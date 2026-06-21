# ETF 基础信息

## 接口信息

| 项目 | 内容 |
| --- | --- |
| 接口名称 | `etf_basic` |
| 描述 | 获取国内 ETF 基础信息，包括 QDII；数据来源于沪深交易所公开披露信息 |
| 调取限量 | 单次最多返回 5,000 条数据，当前 ETF 总数未超过 2,000 |
| 积分要求 | 用户达到 8,000 积分后可调取 |
| 积分说明 | [Tushare 积分获取办法](https://tushare.pro/document/1?doc_id=13) |

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| `ts_code` | `str` | 否 | ETF 代码，格式为带 `.SZ` 或 `.SH` 后缀的六位数字，例如 `159526.SZ` |
| `index_code` | `str` | 否 | 跟踪指数代码 |
| `list_date` | `str` | 否 | 上市日期，格式为 `YYYYMMDD` |
| `list_status` | `str` | 否 | 上市状态：`L` 上市、`D` 退市、`P` 待上市 |
| `exchange` | `str` | 否 | 交易所：`SH` 上交所、`SZ` 深交所 |
| `mgr` | `str` | 否 | 管理人简称，例如 `华夏基金` |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| `ts_code` | `str` | 是 | 基金交易代码 |
| `csname` | `str` | 是 | ETF 中文简称 |
| `extname` | `str` | 是 | ETF 扩位简称，对应交易所简称 |
| `cname` | `str` | 是 | 基金中文全称 |
| `index_code` | `str` | 是 | ETF 基准指数代码 |
| `index_name` | `str` | 是 | ETF 基准指数中文全称 |
| `setup_date` | `str` | 是 | 设立日期，格式为 `YYYYMMDD` |
| `list_date` | `str` | 是 | 上市日期，格式为 `YYYYMMDD` |
| `list_status` | `str` | 是 | 存续状态：`L` 上市、`D` 退市、`P` 待上市 |
| `exchange` | `str` | 是 | 交易所：`SH` 上交所、`SZ` 深交所 |
| `mgr_name` | `str` | 是 | 基金管理人简称 |
| `custod_name` | `str` | 是 | 基金托管人名称 |
| `mgt_fee` | `float` | 是 | 基金管理人收取的费用 |
| `etf_type` | `str` | 是 | 基金投资通道类型，例如境内、QDII |

## 接口示例

```python
# 获取当前所有上市的 ETF 列表
df = pro.etf_basic(
    list_status="L",
    fields="ts_code,extname,index_code,index_name,exchange,mgr_name",
)

# 获取嘉实基金旗下所有已上市 ETF
df = pro.etf_basic(
    mgr="嘉实基金",
    list_status="L",
    fields="ts_code,extname,index_code,index_name,exchange,etf_type",
)

# 获取嘉实基金在深交所上市的所有 ETF
df = pro.etf_basic(
    mgr="嘉实基金",
    list_status="L",
    exchange="SZ",
    fields="ts_code,extname,index_code,index_name,exchange,etf_type",
)

# 获取所有跟踪沪深 300 指数的 ETF
df = pro.etf_basic(
    index_code="000300.SH",
    fields="ts_code,extname,index_code,index_name,exchange,mgr_name",
)
```

## 数据示例

| ts_code | extname | index_code | index_name | exchange | mgr_name |
| --- | --- | --- | --- | --- | --- |
| 159238.SZ | 300ETF增强 | 000300.SH | 沪深300指数 | SZ | 景顺长城基金 |
| 159300.SZ | 300ETF | 000300.SH | 沪深300指数 | SZ | 富国基金 |
| 159330.SZ | 沪深300ETF基金 | 000300.SH | 沪深300指数 | SZ | 西藏东财基金 |
| 159393.SZ | 沪深300指数ETF | 000300.SH | 沪深300指数 | SZ | 万家基金 |
| 159673.SZ | 沪深300ETF鹏华 | 000300.SH | 沪深300指数 | SZ | 鹏华基金 |
| 159919.SZ | 沪深300ETF | 000300.SH | 沪深300指数 | SZ | 嘉实基金 |
| 159925.SZ | 沪深300ETF南方 | 000300.SH | 沪深300指数 | SZ | 南方基金 |
| 159927.SZ | 鹏华沪深300指数 | 000300.SH | 沪深300指数 | SZ | 鹏华基金 |
| 510300.SH | 沪深300ETF | 000300.SH | 沪深300指数 | SH | 华泰柏瑞基金 |
| 510310.SH | 沪深300ETF易方达 | 000300.SH | 沪深300指数 | SH | 易方达基金 |
| 510320.SH | 沪深300ETF中金 | 000300.SH | 沪深300指数 | SH | 中金基金 |
| 510330.SH | 沪深300ETF华夏 | 000300.SH | 沪深300指数 | SH | 华夏基金 |
| 510350.SH | 沪深300ETF工银 | 000300.SH | 沪深300指数 | SH | 工银瑞信基金 |
| 510360.SH | 沪深300ETF基金 | 000300.SH | 沪深300指数 | SH | 广发基金 |
| 510370.SH | 300指数ETF | 000300.SH | 沪深300指数 | SH | 兴业基金 |
| 510380.SH | 国寿300ETF | 000300.SH | 沪深300指数 | SH | 国寿安保基金 |
| 510390.SH | 沪深300ETF平安 | 000300.SH | 沪深300指数 | SH | 平安基金 |
| 515130.SH | 沪深300ETF博时 | 000300.SH | 沪深300指数 | SH | 博时基金 |
| 515310.SH | 沪深300指数ETF | 000300.SH | 沪深300指数 | SH | 汇添富基金 |
| 515330.SH | 沪深300ETF天弘 | 000300.SH | 沪深300指数 | SH | 天弘基金 |
| 515350.SH | 民生加银300ETF | 000300.SH | 沪深300指数 | SH | 民生加银基金 |
| 515360.SH | 方正沪深300ETF | 000300.SH | 沪深300指数 | SH | 方正富邦基金 |
| 515380.SH | 沪深300ETF泰康 | 000300.SH | 沪深300指数 | SH | 泰康基金 |
| 515390.SH | 沪深300ETF指数基金 | 000300.SH | 沪深300指数 | SH | 华安基金 |
| 515660.SH | 沪深300ETF国联安 | 000300.SH | 沪深300指数 | SH | 国联安基金 |
| 515930.SH | 永赢沪深300ETF | 000300.SH | 沪深300指数 | SH | 永赢基金 |
| 561000.SH | 沪深300ETF增强基金 | 000300.SH | 沪深300指数 | SH | 华安基金 |
| 561300.SH | 300增强ETF | 000300.SH | 沪深300指数 | SH | 国泰基金 |
| 561930.SH | 沪深300ETF招商 | 000300.SH | 沪深300指数 | SH | 招商基金 |
| 561990.SH | 沪深300增强ETF | 000300.SH | 沪深300指数 | SH | 招商基金 |
| 563520.SH | 沪深300ETF永赢 | 000300.SH | 沪深300指数 | SH | 永赢基金 |

## Demo 阶段 CSV 存储约定

- 建议路径：`data/raw/etf_basic/etf_basic.csv`
- 文件粒度：保存全部 ETF 的最新基础信息
- 唯一键：`ts_code`
- 同步范围：同时获取 `L`、`D`、`P` 三种状态，避免遗漏退市或待上市 ETF
- 更新方式：每次全量拉取并原子覆盖 CSV
- 日期字段保留为 `YYYYMMDD` 字符串
- `list_status`、`exchange` 和 `etf_type` 保留 Tushare 原始枚举值
