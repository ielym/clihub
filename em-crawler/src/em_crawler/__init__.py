"""em-crawler —— 使用导向（intent-oriented）的东方财富数据 CLI。

把「按数据意图查询」与「底层东财接口抓取」解耦：
- catalog/   指标目录（数据意图 → 口径 → 多源 provider 链）
- providers/ 底层东财接口封装（只出原始字段）
- engine/    查询引擎（分组规划 / 兜底 / 校验 / 结果裁剪）
"""
__version__ = "2.0.0"