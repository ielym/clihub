"""ielym-certification —— 统一的权限凭证获取工具。

按 provider 维度组织：每个 provider 负责一类权限的定位与取回，
新增权限只需在 providers/ 下新增一个模块，CLI 会自动发现。
"""

__version__ = "1.0.0"