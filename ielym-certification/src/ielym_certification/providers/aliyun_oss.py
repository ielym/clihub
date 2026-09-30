"""aliyun-oss provider —— 按 Bucket 维度取回阿里云 OSS 访问凭证。

凭证在 OSS 上的存放约定：

    oss://<store-bucket>/certification/aliyun-oss/<name>/<name>.json

其中 <name> 即 `--bucket` 指定的 Bucket 名，<store-bucket> 缺省与其相同
（即凭证自身就存在被认证的那个 Bucket 里）。
"""
from __future__ import annotations

import argparse
import os
import re
from typing import Any, Dict, List

from .. import bootstrap, ossutil
from .base import BaseProvider, CertificationError, NotFoundError

#: 凭证对象 key 的默认模板
KEY_TEMPLATE = "certification/{provider}/{name}/{name}.json"

ENV_BUCKET = "IELYM_CERT_BUCKET"
ENV_STORE_BUCKET = "IELYM_CERT_STORE_BUCKET"
ENV_ENDPOINT = "IELYM_CERT_OSS_ENDPOINT"
ENV_REGION = "IELYM_CERT_OSS_REGION"

# 从 ls 输出行里取出 certification/<provider>/<name>/ 中的 <name>
_OBJECT_RE = re.compile(r"oss://[^\s]+?/certification/[^/\s]+/([^/\s]+)/")


class AliyunOssProvider(BaseProvider):
    name = "aliyun-oss"
    summary = "阿里云 OSS 访问凭证（按 Bucket 维度）"

    # ---- 参数 ----

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--bucket", default=os.environ.get(ENV_BUCKET),
                            help=f"要获取凭证的 Bucket 名；缺省读 ${ENV_BUCKET}")
        parser.add_argument("--store-bucket", default=os.environ.get(ENV_STORE_BUCKET),
                            help="凭证文件所在 Bucket；缺省与 --bucket 相同")
        parser.add_argument("--key", default=None,
                            help=f"直接指定凭证对象 key，覆盖默认模板 {KEY_TEMPLATE}")
        parser.add_argument("-e", "--endpoint", default=os.environ.get(ENV_ENDPOINT),
                            help=f"OSS 访问域名；缺省读 ${ENV_ENDPOINT}")
        parser.add_argument("--region", default=os.environ.get(ENV_REGION),
                            help=f"地域 ID；缺省读 ${ENV_REGION}")
        parser.add_argument("-c", "--config-file", default=None, help="ossutil 配置文件路径")
        parser.add_argument("--profile", default=None, help="ossutil 配置中的 profile 名")

    def _opts(self, args: argparse.Namespace) -> Dict[str, Any]:
        # 默认走 bootstrap 落盘的专属配置；未引导时给出明确的引导提示
        cred = bootstrap.load_bootstrap()
        config_file = args.config_file
        if not config_file:
            if cred is not None:
                config_file = bootstrap.ossutil_config_path()
            else:
                raise CertificationError(
                    "尚未引导：请先执行 ielym-certification bootstrap"
                    "（经飞书登录态取回引导凭证，每台设备一次）"
                )
        endpoints = (cred or {}).get("endpoints") or {}
        return {
            "endpoint": args.endpoint or endpoints.get("internal"),
            "region": args.region or (cred or {}).get("region"),
            "config_file": config_file,
            "profile": args.profile,
            # 抑制 ossutil 尾部的 "x.xxx(s) elapsed"，避免混进凭证内容
            "quiet": True,
        }

    # ---- 定位 ----

    def _name(self, args: argparse.Namespace) -> str:
        if args.bucket:
            return args.bucket
        # 缺省用引导凭证自身的 Bucket（凭证库所在 Bucket）
        cred = bootstrap.load_bootstrap()
        if cred and cred.get("bucket"):
            return cred["bucket"]
        raise CertificationError(
            f"尚未引导：请先执行 ielym-certification bootstrap；"
            f"引导后仍可显式传 --bucket（或设置 ${ENV_BUCKET}）定位其他 Bucket"
        )

    def _store_bucket(self, args: argparse.Namespace) -> str:
        return args.store_bucket or self._name(args)

    def _key(self, args: argparse.Namespace) -> str:
        if args.key:
            return args.key
        return KEY_TEMPLATE.format(provider=self.name, name=self._name(args))

    def target(self, args: argparse.Namespace) -> Dict[str, Any]:
        name = self._name(args)
        store = self._store_bucket(args)
        key = self._key(args)
        return {
            "provider": self.name,
            "bucket": name,
            "store_bucket": store,
            "key": key,
            "oss_path": f"oss://{store}/{key}",
        }

    # ---- 读取 ----

    def fetch(self, args: argparse.Namespace) -> str:
        oss_path = self.target(args)["oss_path"]
        res = ossutil.run(["cat", oss_path], **self._opts(args))
        if not res.ok:
            err = (res.stderr or "").strip()
            if "NoSuchKey" in err or "Not Found" in err or "404" in err:
                raise NotFoundError(f"凭证不存在：{oss_path}")
            raise CertificationError(err or f"ossutil 退出码 {res.code}")
        return res.stdout

    def list_names(self, args: argparse.Namespace) -> List[str]:
        store = self._store_bucket(args)
        prefix = f"oss://{store}/certification/{self.name}/"
        res = ossutil.run(["ls", prefix], **self._opts(args))
        if not res.ok:
            raise CertificationError((res.stderr or "").strip() or f"ossutil 退出码 {res.code}")
        names: List[str] = []
        for line in res.stdout.splitlines():
            m = _OBJECT_RE.search(line)
            if m and m.group(1) not in names:
                names.append(m.group(1))
        return sorted(names)