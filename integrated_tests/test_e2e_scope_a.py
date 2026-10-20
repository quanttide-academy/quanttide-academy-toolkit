"""e2e 范围 A（两个群）v3 规则：#6 指派卡（执行员是别人，用户为审批人），#7 指派卡（征集意见、办理人待定），#8～#10 执行卡；发言人已解析姓名。
依赖本地数据（local/、data/work/e2e-6-10/），不入库；缺失则跳过。运行：pytest integrated_tests"""

import json
import re

import pytest

from integrated_tests import e2e_render as E

pytestmark = pytest.mark.skipif(not E.available("A"), reason="缺本地 e2e 数据")


def test_scope_a_cards():
    rep = E.render("A")
    W = E.OUT["A"]
    allow = {
        c["chat_id"]
        for c in json.loads((E.ROOT / "data" / "e2e-scope-A.json").read_text(encoding="utf-8"))["include_chats"]
    }
    assert (
        len(allow) == 2
        and {m["chat_id"] for m in json.loads((W / "messages.json").read_text(encoding="utf-8"))["messages"]} <= allow
    )
    cards = (W / "cards.txt").read_text(encoding="utf-8")
    assert [int(n) for n in re.findall(r"^【#(\d+)】", cards, re.MULTILINE)] == [6, 7, 8, 9, 10]
    assert rep["info"] == 0 and rep["to_assign"] == 2 and "纯资讯 0 条，待你指派 2 条。" in cards
    b7 = cards.split("【#7】")[1].split("【#8】")[0]
    assert "执行员：（办理人待定）" in b7 and "行动：指派（按规则：办理人待定）" in b7
    assert "（未知发言人）" not in cards and "（未知成员）" not in cards and "{person:" not in cards
    b6 = cards.split("【#6】")[1].split("【#8】")[0]
    assert "行动：指派（按规则：执行员是别人）" in b6 and "审批人：" in b6 and "（按规则：执行员是别人）" in b6
    assert "（原 " in cards.split("【#8】")[1].splitlines()[1]  # 部门名不当人名，摘要保留原部门名
    assert "按角色推断" not in cards.split("【#8】")[1].split("【#9】")[0]  # #8 按原话
    assert cards.count("行动：执行（按角色推断：") == 2  # #9、#10 唯一执行员按角色
    assert "F3" not in cards and "fi:" not in cards and "<!--" not in cards
    assert sorted(json.loads((W / "versions.json").read_text(encoding="utf-8"))) == ["10", "6", "7", "8", "9"]
