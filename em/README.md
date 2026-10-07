# em —— 使用导向的东方财富数据 CLI

按「数据意图」查询东方财富数据，而非按「东财模块」抓取。查一个指标，只返回一个干净、口径明确的值。

- CLI 源码：`/mnt/data01/projects/clihub/em/`（纯 Python，自包含，指向 `src/em` 包）
- 命令：`em`（`bin/em` 为入口脚本）

## 核心理念

| 概念 | 说明 |
| :-: | :-: |
| **指标 metric** | 一个数据意图（如「收盘价」「涨跌幅」「净利润」「质押比例」），全局唯一 ID |
| **口径 calibration** | 同一指标上「会改变数值语义」的少数维度：复权(前/后/不复权)、市盈率(静态/动态/TTM)、报告期等 |
| **多源兜底** | 同一指标可能来自多个东财接口，按优先级尝试，主源失败自动降级到下个源 |
| **结果纯净** | 查「涨跌幅」只返回涨跌幅，不带换手率/市值等无关字段 |

## 安装

```bash
cd /mnt/data01/projects/clihub/em
export PATH="$PATH:$PWD/bin"     # 或 ln -s bin/em /usr/local/bin/em
```

依赖：`httpx` `curl_cffi` `pydantic` `pyyaml`（`pycryptodome` 用于股吧人气榜解密）。

## 用法

```bash
em list                                # 列出全部指标（意图）
em list --group 行情                    # 按分组列出
em <指标> <代码> [--口径 ...]            # 查询单一指标（干净单值）
em batch <代码> 指标1,指标2,...          # 批量合并查询（同接口一次请求）
em <指标> <代码> --help                 # 无（指标口径通过 --key value 传入）
```

### 示例

```bash
em close 000001                              # 收盘价 11.57 元
em close 000001 --trade_date 2025-06-30 --adjust qfq   # 历史前复权收盘价
em pct_change 000001                         # 涨跌幅 1.94 %
em pe 000001 --scope ttm                     # 市盈率(TTM) 5.17 倍
em pe 000001 --scope static                  # 市盈率(静态)
em turnover_rate 000001                      # 换手率 0.54 %
em net_profit 000001                         # 净利润
em eps 000001                                # 每股收益
em holder_num 000001                         # 股东户数
em cpi                                       # CPI 时间序列
em guba_rank                                 # 股吧人气榜
em batch 000001 close,high,low,pct_change,volume,turnover_rate,pe,pb,total_mv
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

- `value`：标量指标为单一值；`series`/`table` 指标为数组。
- `calibration`：仅回显「本指标可变的口径」，不冗余输出定位维度。
- `fallback`：true 表示主源失败、由兜底源命中。

## 指标目录（487 个，11 组）

| 组 | 内容（示例） |
| :-: | :-: |
| 行情 quote | price/close/open/high/low/pct_change/volume/amount/turnover_rate/pe/pb/市值/kline/分时/盘口/行业板块/概念板块/全球指数/债券/涨跌停池/港美股/期货/期权/外汇/黄金等 |
| 资金 capital | 主力/大单净流入、龙虎榜、两融余额、沪深港通、大宗交易、质押比例、股东户数、账户统计 |
| 财务 finance | eps/bps/营收/净利润/roe/毛利率/现金流/同比、三表、业绩预告/快报、分红、解禁、调研、评级 |
| 公司资料 f10 | 概况、股东、股本结构、概念、机构持股、重大事项、高管、融资、行业对比、关联公司、估值、港股/美股 F10 |
| 股东与高管 company | 高管持股变动、限售解禁、十大股东/流通股东分析、股东户数、主力持仓 |
| 资讯 news | 公告列表/正文、研报、快讯、财经新闻、新股申购 |
| 基金 fund | 代码表、净值、持仓、经理、排行、ETF/LOF、定期报告PDF |
| 宏观 macro | CPI/PPI/PMI/GDP/M2/LPR/财政/社融/外汇储备/用电量、海外宏观 |
| 股吧 guba | 帖子、正文、评论、人气榜 |
| 工具 tool | 个股诊断、互动易、主力监控、指数估值、定投计算、组合回测、财报图解 |
| 事件 event | 千股千评、港通持股、配股、回购、高管增减持、商誉、IPO日历、股东大会、期货龙虎榜、关联交易、重大合同、委托理财、市场估值、一致行动人、转融通、并购重组、IPO审核、停复牌 |

完整清单：`em list`。

## 口径（calibration）

- **行情复权**：`--adjust none|qfq|hfq`（历史 K 线/收盘价有意义）
- **市盈率口径**：`--scope ttm|dynamic|static`（默认 TTM）
- **报告期**：`--report_date YYYY-MM-DD`（财务类）
- 未显式给口径时用默认值，并在结果 `calibration` 中回显。

## 多源兜底与校验

- 每个指标在 `src/em/catalog/metrics.yaml` 中声明有序 `providers` 链（主源 + 兜底源）。
- 查询引擎按优先级尝试主源，命中即停、不再解析兜底源；主源异常/空值时自动降级到兜底源并标记 `fallback=true`。
- 对「同口径多接口」数据做交叉校验登记（如换手率 = 快照 f168 vs K线），口径不一致则拆分为两个指标。
- 校验清单：`src/em/catalog/metrics.yaml` 中 `equivalence` 字段（构建期交叉比对落成）。

## 环境变量

| 变量 | 说明 |
| :-: | :-: |
| `EM_HTTP_TIMEOUT` | 单请求超时秒数，默认 30；走 IP 隧道建议 40+ |
| `EM_PROXY` / `HTTP_PROXY` / `HTTPS_PROXY` | 代理（港股行情域名 push2 需 IP 隧道） |
| `EM_VERIFY_TLS` | 置 0 关闭 TLS 校验 |

> `push2*.eastmoney.com`（行情快照/K线/榜单）存在 TLS 指纹反爬，直连可能被断开，需经 IP 隧道代理执行；`datacenter-web`（财务/资金/宏观/事件）、`push2ex`（涨停池）等域名直连即可。

## 架构

```
em (CLI 意图面)
 └─ engine/     查询引擎：分组规划(同接口合并请求) + 兜底链 + 字段裁剪
     ├─ catalog/  指标目录 metrics.yaml（意图→口径→多源 provider 链→一致性断言）
     └─ providers/ 底层东财接口封装（quote/datacenter/fund/f10/guba/news/macro/pool/tools/cross/event）
```

新增数据源只需：在 `providers/` 加一个 endpoint 函数 + 在 `metrics.yaml` 登记一个指标 → 无需改动引擎与 CLI。

> CLI 只负责查询返回，不承担存储功能。