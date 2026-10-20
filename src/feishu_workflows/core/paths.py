"""所有路径都从这里取；默认放在各系统的用户数据目录，可在 config.paths 中覆盖。"""

from pathlib import Path

from feishu_workflows.core.config import ROOT
from feishu_workflows.settings import default_data_dir, guard_test_path

APP = "feishu-intent"


def _p(cfg, key, default: Path) -> Path:
    v = (cfg.get("paths") or {}).get(key)
    if not v:
        return default
    p = Path(v).expanduser()
    return p if p.is_absolute() else ROOT / p


def data_dir(cfg) -> Path:
    return guard_test_path(_p(cfg, "data_dir", default_data_dir()))


def state_db(cfg) -> Path:
    p = guard_test_path(_p(cfg, "state_db", data_dir(cfg) / "state.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def candidates_dir(cfg) -> Path:
    p = _p(cfg, "candidates_dir", data_dir(cfg) / "candidates")
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir(cfg) -> Path:
    p = _p(cfg, "log_dir", data_dir(cfg) / "logs")
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir(cfg, batch=None) -> Path:
    p = _p(cfg, "work_dir", default_data_dir() / "work")
    p = p / batch if batch else p
    p.mkdir(parents=True, exist_ok=True)
    return p


def followups_path(cfg):
    v = (cfg.get("followups") or {}).get("path")
    if not v:
        return None
    p = Path(v).expanduser()
    return p if p.is_absolute() else ROOT / p


def schema() -> str:
    return (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")


def name_cache(cfg) -> Path:
    """open_id→姓名 缓存（只存这两项，7 天过期）；在 data/ 下，不入库。"""
    return data_dir(cfg) / "name_cache.json"


def dept_cache(cfg) -> Path:
    """部门名缓存（只存名字，7 天过期），用作人名校验的豁免表；在 data/ 下，不入库。"""
    return data_dir(cfg) / "dept_names.json"
