# Changelog

本项目的主要变更将记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-06-21

### Added

- 基于本地 Excel 的指数跟踪池管理。
- Tushare 指数周线采集、分页、映射和增量更新。
- 行业主题与规模指数的周期强弱 Dashboard。
- 周度涨跌榜、区间累计榜和跨周期指数追踪高亮。
- Tushare 交易日历支持。
- 基于 MiniMax Search 与文本模型的财联社收评采集。
- 公开资讯页正文提取与结构化 JSON 存储。
- 工作日定时执行收评采集的 Linux cron 脚本。
- 数据采集、新闻筛选和搜索能力的单元测试。

### Security

- API Key 仅通过 `.env` 读取，不提交至版本库。
- 网页正文抓取包含私网地址检查、超时和响应大小限制。
