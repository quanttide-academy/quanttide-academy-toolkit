from quanttide_academy_toolkit.core import db
from quanttide_academy_toolkit.intent import outputs
from tests.helpers import *


def test_markdown_adapter_utf8(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path)}, "todo": {"provider": "markdown"}}
    a = outputs.load(cfg)
    assert a.check()[0]
    item = {
        "no": 1,
        "title": TEXT,
        "priority": "P1",
        "labels": ["跟进"],
        "fingerprint": "fp1",
        "subtasks": ["子任务一"],
        "links": [],
    }
    with pytest.raises(outputs.NotConfirmed):
        a.create(item)
    d = db.connect(cfg)
    d.execute("insert into topics(fingerprint,title,confirmed) values('fp1','t',1)")
    d.commit()
    d.close()
    a.create(item)
    assert TEXT in a.inner._f().read_text(encoding="utf-8")
