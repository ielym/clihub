# em-crawler —— 使用导向的东方财富数据 CLI

按「数据意图」查询东方财富数据，而非按「东财模块」抓取。查一个指标，只返回一个干净、口径明确的值。

> 原名 `em`，2026-10 重命名为 `em-crawler`（包名 `em_crawler`、命令 `em-crawler`）。旧命令 `em` 已移除。

- CLI 源码：`/mnt/data01/projects/clihub/em-crawler/`（纯 Python，自包含，指向 `src/em_crawler` 包）
- 命令：`em-crawler`（`bin/em-crawler` 为入口脚本）

## 核心理念

| 概念 | 说明 |
| :-: | :-: |
| **指标 metric** | 一个数据意图（如「收盘价」「涨跌幅」「净利润」「质押比例」），全局唯一 ID |
| **口径 calibration** | 同一指标上「会改变数值语义」的少数维度：复权(前/后/不复权)、市盈率(静态/动态/TTM) 等 |
| **多源兜底** | 同一指标可能来自多个东财接口，按优先级尝试，主源失败自动降级到下个源 |
| **结果纯净** | 查「涨跌幅」只返回涨跌幅，不带换手率/市值等无关字段 |

## 安装

```bash
cd /mnt/data01/projects/clihub/em-crawler
pip install -e . --break-system-packages     # 提供全局命令 em-crawler
# 或仅本会话（不安装）：
export PATH="$PATH:$PWD/bin"
```

依赖：`httpx` `curl_cffi` `pyyaml` `pycryptodome`（`pycryptodome` 用于股吧人气榜解密）。

## 用法

```bash
em-crawler list                              # 列出全部指标（意图），JSON
em-crawler list --group quote                # 按分组列出（分组键：quote/capital/finance/f10/company/news/fund/macro/guba/tool/event）
em-crawler <指标> <代码> [--口径/参数 ...]     # 查询单一指标（干净单值）
em-crawler batch <代码> 指标1,指标2,...        # 批量合并查询（同接口一次请求）
em-crawler help                              # 帮助
```

位置参数绑定：多数指标是 `code`；对唯一必填参数不是 `code` 的指标（如龙虎榜的 `trade_date`、宏观指标的 `indicator`），位置参数会绑定到该必填参数。

### 示例

```bash
em-crawler close 000001                              # 收盘价 11.57 元
em-crawler close 000001 --trade_date 2025-06-30 --adjust qfq   # 历史前复权收盘价
em-crawler pct_change 000001                         # 涨跌幅 1.94 %
em-crawler pe 000001 --scope ttm                     # 市盈率(TTM)
em-crawler turnover_rate 000001                      # 换手率
em-crawler net_profit 000001                         # 净利润
em-crawler holder_num 000001                         # 股东户数
em-crawler cpi                                       # CPI 时间序列
em-crawler zt_pool                                   # 涨停池
em-crawler lhb --trade_date 2026-09-30               # 龙虎榜
em-crawler batch 000001 close,high,low,pct_change,volume,turnover_rate,pe,pb,total_mv
```

### 输出格式

```json
{
  "ok": true,
  "metric": "close",
  "calibration": {"adjust": "none"},
  "value": 11.57,
  "unit": "元",
  "as_of": "2026-09-30",
  "provider": "quote.kline",
  "fallback": false
}
```

- `value`：`scalar` 指标为单一值；`series`/`table` 指标为数组。
- `calibration`：仅回显「本指标可变的口径」，不冗余输出定位维度。
- `fallback`：true 表示主源失败、由兜底源命中。
- 失败时输出 `{"ok": false, "error": "..."}`。

## 指标目录（506 个，11 组）

| 分组键 | 组名 | 内容（示例） |
| :-: | :-: | :-: |
| `quote` | 行情 | price/close/open/high/low/pct_change/volume/amount/turnover_rate/pe/pb/市值/量比/kline/分时/盘口/行业板块/概念板块/全球指数/债券/北交所/涨跌停池/港美股/期货/期权/外汇/黄金/沪深港通标的 |
| `capital` | 资金 | 主力·超大单·大单·中单·小单净流入、龙虎榜（含营业部维度）、融资·融券（多口径）、沪深港通（十大成交/机构/板块）、大宗交易（多口径）、质押、股东户数、账户统计 |
| `finance` | 财务 | eps/bps/营收/净利润/roe/毛利率/每股经营现金流/同比、三表、业绩预告·快报、预约披露、分红、解禁、调研、评级 |
| `f10` | 公司资料 | 概况、十大股东、流通股东、股本结构、主要指标、杜邦分析、概念、机构持股、重大事项、高管、股权激励、融资、分红融资、行业对比、关联公司、估值、港股/美股 F10 |
| `company` | 股东与高管 | 高管持股变动、限售解禁、十大股东/流通股东分析、股东户数、主力持仓 |
| `news` | 资讯 | 公告列表/正文、研报列表/正文、快讯、财经新闻、新股申购 |
| `fund` | 基金 | 代码表、净值、持仓、经理、排行、ETF/LOF、定期报告 PDF |
| `macro` | 宏观 | CPI/PPI/PMI/GDP/M2/LPR/财政/社融/外汇储备/用电量、海外宏观、行业指标库 |
| `guba` | 股吧 | 帖子列表/正文/评论、人气榜 |
| `tool` | 工具 | 个股诊断、互动易、主力监控、指数估值、定投计算、组合回测、财报图解 |
| `event` | 数据中心事件 | 千股千评、港通持股、配股、回购、高管增减持、商誉、IPO 日历、股东大会、期货龙虎榜、关联交易、重大合同、委托理财、市场估值、股东持股、一致行动人、转融通、公司投资、并购重组、IPO 审核、停复牌 |

完整清单：`em-crawler list`。

## 口径（calibration）

- **行情复权**：`--adjust none|qfq|hfq`（历史 K 线/收盘价有意义）
- **市盈率口径**：`--scope ttm|dynamic|static`（默认 ttm）
- **报告期**：`--report_date YYYY-MM-DD`（财务类）
- 未显式给口径时用默认值，并在结果 `calibration` 中回显。

## 多源兜底与校验

- 每个指标在 `src/em_crawler/catalog/metrics.yaml` 中声明有序 `providers` 链（主源 + 兜底源）。
- 查询引擎按优先级尝试主源，命中即停；主源异常/空值时自动降级到兜底源并标记 `fallback=true`。
- 对「同口径多接口」数据做交叉校验登记（`equivalence` 字段），口径不一致则拆分为两个指标。

## 环境变量

| 变量 | 说明 |
| :-: | :-: |
| `EM_HTTP_TIMEOUT` | 单请求超时秒数，默认 30；走 IP 隧道建议 40+ |
| `EM_PROXY` / `HTTP_PROXY` / `HTTPS_PROXY` | 代理（`push2*.eastmoney.com` 行情域名需 IP 隧道） |
| `EM_VERIFY_TLS` | 置 0 关闭 TLS 校验 |

> `push2*.eastmoney.com`（快照/K线/榜单/资金流）存在 TLS 指纹反爬，直连可能被断开，需经 IP 隧道代理执行；`datacenter-web`（财务/资金/宏观/事件）、`push2ex`（涨停池）等域名直连即可。

## 架构

```
em-crawler (CLI 意图面)
 └─ engine/     查询引擎：分组规划(同接口合并请求) + 兜底链 + 字段裁剪
     ├─ catalog/  指标目录 metrics.yaml（意图→口径→多源 provider 链→一致性断言）
     └─ providers/ 底层东财接口封装（quote/datacenter/fflow/news/fund/f10/guba/pool/macro/tools/cross/event/extended）
```

新增数据源只需：在 `providers/` 加一个 endpoint 函数 + 在 `metrics.yaml` 登记一个指标 → 无需改动引擎与 CLI。

> CLI 只负责查询返回，不承担存储功能。
