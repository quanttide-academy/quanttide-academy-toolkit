from quanttide_academy.core.migrations import STATUS_V2
from quanttide_academy.intent.status import ZH, label


def test_status_round_trip():
    assert {v: k for k, v in STATUS_V2.items()} == ZH  # 迁移映射与显示映射一致
    assert label("written") == "已写入" and label(None) == "未知" and label("x") == "x"
