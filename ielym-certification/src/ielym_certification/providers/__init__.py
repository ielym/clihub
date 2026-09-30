"""权限提供方（provider）包。

扩展方式：在本目录新增一个模块，定义 BaseProvider 的子类并设置 name / summary，
实现 add_arguments 与 fetch（如需支持列举再实现 list_names），
无需修改 registry.py 或 cli.py，CLI 会自动加载。
"""