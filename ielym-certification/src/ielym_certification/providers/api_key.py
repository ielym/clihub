"""api-key provider —— 按服务名维度取回第三方 API Key / Token。

凭证在 OSS 上的存放约定：

    oss://<store-bucket>/certification/api-key/<name>/<name>.json

<name> 即第三方服务名（如 artificial-analysis、openrouter），由 --name 指定；
<store-bucket> 缺省为引导凭证自身的 Bucket（凭证库所在 Bucket）。

凭证文件内容为 JSON，具体取哪个字段由调用方（如 artificial-analysis、openrouter）约定，
本 provider 只负责把整个 JSON 文本原样取回。
"""
from __future__ import annotations

import argparse
import os
from typing import Any, Dict

from .. import bootstrap
from .aliyun_oss import ENV_ENDPOINT, ENV_REGION, ENV_STORE_BUCKET, AliyunOssProvider
from .base import CertificationError


class ApiKeyProvider(AliyunOssProvider):
    name = "api-key"
    summary = "第三方 API Key / Token（按服务名维度）"

    # ---- 参数 ----

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--name", default=None,
                            help="第三方服务名，如 artificial-analysis、openrouter（--list 时可省略）")
        parser.add_argument("--key", default=None,
                            help="直接指定凭证对象 key，覆盖默认模板 certification/api-key/<name>/<name>.json")
        parser.add_argument("--store-bucket", default=os.environ.get(ENV_STORE_BUCKET),
                            help=f"凭证文件所在 Bucket；缺省用引导凭证的 Bucket（或 ${ENV_STORE_BUCKET}）")
        parser.add_argument("-e", "--endpoint", default=os.environ.get(ENV_ENDPOINT),
                            help=f"OSS 访问域名；缺省读 ${ENV_ENDPOINT}")
        parser.add_argument("--region", default=os.environ.get(ENV_REGION),
                            help=f"地域 ID；缺省读 ${ENV_REGION}")
        parser.add_argument("-c", "--config-file", default=None, help="ossutil 配置文件路径")
        parser.add_argument("--profile", default=None, help="ossutil 配置中的 profile 名")

    def _name(self, args: argparse.Namespace) -> str:
        if not args.name:
            raise CertificationError("必须用 --name 指定第三方服务名")
        return args.name

    def _store_bucket(self, args: argparse.Namespace) -> str:
        if args.store_bucket:
            return args.store_bucket
        cred = bootstrap.load_bootstrap()
        if cred and cred.get("bucket"):
            return cred["bucket"]
        raise CertificationError(
            f"未指定凭证库 Bucket：请传 --store-bucket、设置 ${ENV_STORE_BUCKET}，"
            "或先执行 ielym-certification bootstrap"
        )

    # ---- 定位 ----

    def target(self, args: argparse.Namespace) -> Dict[str, Any]:
        name = self._name(args)
        store = self._store_bucket(args)
        key = self._key(args)
        return {
            "provider": self.name,
            "name": name,
            "store_bucket": store,
            "key": key,
            "oss_path": f"oss://{store}/{key}",
        }
