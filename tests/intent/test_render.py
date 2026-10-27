from quanttide_academy_toolkit.intent import render
from tests.helpers import *


def test_render_utf8_newlines(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path)}, "labels": {"priority_names": {}}}
    data = {
        "header": TEXT,
        "items": [
            {
                "no": 1,
                "title": "测试🎉",
                "type": "建议",
                "confidence": "高",
                "relation": "需执行",
                "summary": TEXT,
                "priority": "P3",
                "sources": [
                    {"chat": "群", "time": "10-20 10:00", "account": "内部", "link": "https://x", "message_id": "om_1"}
                ],
            }
        ],
    }
    p = render.render(data, cfg)
    raw = p.read_bytes()
    assert b"\r\n" not in raw and TEXT in raw.decode("utf-8") and "P3（" not in raw.decode("utf-8")
