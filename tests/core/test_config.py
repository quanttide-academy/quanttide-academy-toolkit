from quanttide_academy_toolkit.core import config
from tests.helpers import *


def test_load_explicit_and_env(tmp_path, monkeypatch):
    p = tmp_path / "c.yaml"
    p.write_text("timezone: Asia/Shanghai\nuser:\n  display_name: 小明\n", encoding="utf-8")
    assert config.load(p)["user"]["display_name"] == "小明"
    monkeypatch.setenv("FEISHU_WORKFLOWS_CONFIG", str(p))
    assert config.load()["timezone"] == "Asia/Shanghai"
    (tmp_path / "e.yaml").write_text("", encoding="utf-8")
    assert config.load(tmp_path / "e.yaml") == {}
