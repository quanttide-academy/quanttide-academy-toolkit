"""唯一读写环境变量的地方：配置路径、数据目录、密钥是否存在。其他模块一律经这里取。"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 仓库根目录
PKG = Path(__file__).resolve().parent  # 包目录（schema、prompt、schemas）
TZ_NAME = "Asia/Shanghai"
CONFIG_ENVS = ("FEISHU_WORKFLOWS_CONFIG", "FEISHU_INTENT_CONFIG")  # 后者为兼容旧名


class UnsafeTestPath(RuntimeError):
    pass


def env(name, default=None):
    return os.environ.get(name, default)


def secret(name):
    """返回密钥环境变量的值（只供适配器直接使用，不得打印）；未设置返回 None。"""
    return os.environ.get(name) if name else None


def has_secret(name):
    return bool(secret(name))


def config_path() -> Path:
    for k in CONFIG_ENVS:
        if os.environ.get(k):
            return Path(os.environ[k])
    return ROOT / "config.yaml"


def default_data_dir() -> Path:
    return Path(os.environ.get("FEISHU_WORKFLOWS_DATA_DIR") or ROOT / "data")


def lark_cli_bin():
    return os.environ.get("LARK_CLI_BIN")


DEFAULT_MAX_PAGES = 50


def max_pages(cfg=None) -> int:
    v = ((cfg or {}).get("lark_cli") or {}).get("max_pages")
    if v is None:
        v = (cfg or {}).get("max_pages")
    if v is None:
        v = os.environ.get("FEISHU_WORKFLOWS_MAX_PAGES") or os.environ.get("LARK_CLI_MAX_PAGES")
    n = int(v) if v is not None else DEFAULT_MAX_PAGES
    if n < 1:
        raise ValueError("max_pages 必须 >= 1")
    return n


def is_test():
    return os.environ.get("FI_TEST") == "1"


def guard_test_path(p: Path) -> Path:
    """FI_TEST=1 时，数据文件必须在系统临时目录下，防止测试碰到真实数据。"""
    if is_test():
        tmp = Path(tempfile.gettempdir()).resolve()
        if tmp not in Path(p).resolve().parents:
            raise UnsafeTestPath(f"FI_TEST=1 时数据路径必须在临时目录下：{p}")
    return p


@contextmanager
def override_config(path):
    """临时把配置指向 path（selftest、setup 自检用），退出时恢复。"""
    old = {k: os.environ.get(k) for k in CONFIG_ENVS}
    os.environ["FEISHU_WORKFLOWS_CONFIG"] = str(path)
    os.environ.pop("FEISHU_INTENT_CONFIG", None)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def unset(name):
    os.environ.pop(name, None)


SENSITIVE_HMAC_ENV = "FEISHU_WORKFLOWS_HMAC_KEY"
SENSITIVE_HASHES_ENV = "FEISHU_WORKFLOWS_HASHES_PATH"


def sensitive_hmac_key() -> bytes | None:
    v = secret(SENSITIVE_HMAC_ENV)
    return v.strip().encode("utf-8") if v and v.strip() else None


def sensitive_hashes_path() -> Path:
    p = os.environ.get(SENSITIVE_HASHES_ENV)
    return Path(p) if p else ROOT / "data" / "sensitive_hashes.txt"
