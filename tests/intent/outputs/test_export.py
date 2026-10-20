import types

from feishu_workflows.intent.outputs.export import ExportAdapter, csv_safe, ics_esc
from tests.helpers import *


def test_export_injection_and_formats(tmp_path, monkeypatch):
    assert csv_safe("=1+1") == "'=1+1" and csv_safe("ok") == "ok"
    assert "\n" not in ics_esc("a\nBEGIN:VEVENT")
    cfg = {"paths": {"data_dir": str(tmp_path)}, "labels": {"priority_names": PN}}
    item = {
        "no": 1,
        "title": "=cmd",
        "priority": "P2",
        "labels": ["业务"],
        "ddl": "2026-10-25",
        "subtasks": ["s1"],
        "links": [],
    }
    csv_ad = ExportAdapter({"format": "csv"}, cfg)
    assert csv_ad.describe()["priority"] is True and csv_ad.check()[0] is True
    eid, _ = csv_ad.create(item)
    assert eid and "'=cmd" in (tmp_path / "confirmed.csv").read_text(encoding="utf-8")
    with pytest.raises(NotImplementedError):
        csv_ad.comment(eid, "hi")
    ics_ad = ExportAdapter({"format": "ics"}, cfg)
    assert ics_ad.create({**item, "ddl": None})[0] is None
    assert ics_ad.create(item)[0] and "BEGIN:VEVENT" in (tmp_path / "confirmed.ics").read_text(encoding="utf-8")
    assert ExportAdapter({"format": "webhook"}, cfg).check()[0] is False
    wh_ad = ExportAdapter({"format": "webhook", "url": "https://example.com/hook", "secret_env": "FI_WH_SEC"}, cfg)
    assert wh_ad.check()[0] is True
    monkeypatch.setenv("FI_WH_SEC", "sec123")
    reqs = []
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: reqs.append(req) or types.SimpleNamespace())
    wh_ad.create(item)
    wh_ad.comment("e1", "note")
    assert len(reqs) == 2 and "X-signature" in dict(reqs[0].header_items())
