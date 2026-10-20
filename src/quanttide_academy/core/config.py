"""统一读取配置。查找顺序：环境变量 FEISHU_INTENT_CONFIG → 项目根目录 config.yaml。"""

from pathlib import Path

import yaml

from quanttide_academy.settings import ROOT, TZ_NAME, config_path  # noqa: F401


def load(path=None) -> dict:
    p = Path(path) if path else config_path()
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
