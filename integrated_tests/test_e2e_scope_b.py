"""e2e 范围 B（只含实训基地群的对照）新角色格式：v3 规则：#6、#7 都是指派卡。缺本地数据则跳过。"""

import json

import pytest

from integrated_tests import e2e_render as E

pytestmark = pytest.mark.skipif(not E.available("B"), reason="缺本地 e2e 数据")


def test_scope_b_cards():
    rep = E.render("B")
    W = E.OUT["B"]
    assert len(json.loads((E.ROOT / "data" / "e2e-scope-B.json").read_text(encoding="utf-8"))["include_chats"]) == 1
    cards = (W / "cards.txt").read_text(encoding="utf-8")
    assert (
        rep["card_count"] == 2
        and "【#6】" in cards
        and "【#7】" in cards
        and rep["info"] == 0
        and rep["to_assign"] == 2
    )
    assert "（未知发言人）" not in cards and sorted(json.loads((W / "versions.json").read_text(encoding="utf-8"))) == [
        "6",
        "7",
    ]
