import contextlib

from quanttide_academy.core import db
from quanttide_academy.intent import followups
from tests.helpers import *


def test_followups_json_source(tmp_path):
    f = tmp_path / "fu.json"
    f.write_text(
        json.dumps([{"id": "F3", "title": "运营部、游戏部待代表大会审批"}], ensure_ascii=False), encoding="utf-8"
    )
    cfg = {"paths": {"data_dir": str(tmp_path)}, "followups": {"path": str(f)}}
    with contextlib.closing(db.connect(cfg)) as d:
        followups.sync(cfg, d)
        assert followups.titles(cfg, d) == {"F3": "运营部、游戏部待代表大会审批"}


def test_followups_missing_aborts(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path)}, "followups": {"path": str(tmp_path / "无.md")}}
    with contextlib.closing(db.connect(cfg)) as d:
        with pytest.raises(followups.FollowupError):
            followups.sync(cfg, d)
        assert followups.sync({"paths": {"data_dir": str(tmp_path)}}, d) == []


def test_markdown_follower_column(tmp_path):
    md = tmp_path / "fu.md"
    md.write_text(
        "| 编号 | 议题 | 关键词 | 状态 | 负责 |\n|---|---|---|---|---|\n| F2 | 活动审批 | 审批 | 进行中 | 小明（ou_me） |\n| F3 | 名单 | 名单 | 进行中 | 小明 |\n",
        encoding="utf-8",
    )
    cfg = {"paths": {"data_dir": str(tmp_path / "d")}, "followups": {"path": str(md)}}
    with contextlib.closing(db.connect(cfg)) as d:
        followups.sync(cfg, d)
        f = followups.followers(cfg, d)
        assert f["F2"] == {"name": "小明", "open_id": "ou_me"} and f["F3"] == {"name": "小明", "open_id": None}


def test_missing_followups_fails_loudly(env, tmp_path):
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c["followups"] = {"path": str(tmp_path / "不存在.md")}
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    rc, r = run("next")
    assert rc == 1 and r["status"] == "fail" and "跟进清单读不到" in r["reason"]
    src = (ROOT / "src" / "quanttide_academy" / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert 'cfg["_followup_titles"]={}' not in src
