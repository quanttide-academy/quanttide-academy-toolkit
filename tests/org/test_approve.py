"""审批来源核验：缺来源、发送人不对、会话不对、过早/过期、文本或 ID 不符、消息重复使用都拒绝；全部为虚构 ID。"""

import json
import sqlite3
import time

import pytest

from quanttide_academy.core import migrations
from quanttide_academy.org import apply as AP
from quanttide_academy.org import approve as A
from quanttide_academy.org import plan as P
from tests.org.helpers import message
from tests.org.test_plan import cfg, fake_big


def setup(tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    f = fake_big()
    c = cfg()
    pl = P.compute(c, f)
    P.store(d, pl)
    return d, f, c, pl


def test_ok_and_single_use(tmp_path):
    d, f, c, pl = setup(tmp_path)
    mid = message(f, f"批准 {pl['plan_id'][:8]}")
    r = A.approve(c, d, mid, f)
    assert r["approved"] == [1, 2] and "北京时间" in r["approval_sent_at"]
    with pytest.raises(A.ApprovalError, match="已经用过"):
        A.approve(c, d, mid, f)
    assert d.execute("select count(*) from org_approvals").fetchone()[0] == 1
    d.close()


@pytest.mark.parametrize(
    "over,msg",
    [
        ({"sender": "ou_someone"}, "不是本人"),
        ({"sender_type": "app"}, "不是本人"),
        ({"chat_id": "oc_other"}, "审批单聊"),
        ({"create_ms": (int(time.time()) - 3600) * 1000}, "早于"),
        ({"create_ms": (int(time.time()) + 25 * 3600) * 1000}, "24 小时"),
        ({"deleted": True}, "已删除"),
        ({"msg_type": "post"}, "恰为"),
    ],
)
def test_rejects_bad_metadata(tmp_path, over, msg):
    d, f, c, pl = setup(tmp_path)
    with pytest.raises(A.ApprovalError, match=msg):
        A.approve(c, d, message(f, f"批准 {pl['plan_id'][:8]}", **over), f)
    assert d.execute("select status from org_plans").fetchone()[0] == "pending"
    d.close()


@pytest.mark.parametrize(
    "text,msg",
    [
        ("同意", "恰为"),
        ("批准", "恰为"),
        ("批准  {id}", "恰为"),
        ("批准 {id} 1,3", "恰为"),
        ("批准 {id}。", "恰为"),
        ("批准 deadbeef", "不符"),
        ("批准 {full}", "恰为"),
        ("批准 {id} 1", "建群"),
    ],
)
def test_rejects_text_or_id_mismatch(tmp_path, text, msg):
    d, f, c, pl = setup(tmp_path)
    t = text.format(id=pl["plan_id"][:8], full=pl["plan_id"])
    with pytest.raises(A.ApprovalError, match=msg):
        A.approve(c, d, message(f, t), f)
    d.close()


def test_missing_source(tmp_path):
    d, f, c, pl = setup(tmp_path)
    with pytest.raises(A.ApprovalError, match="message_id"):
        A.approve(c, d, "", f)
    with pytest.raises(A.ApprovalError, match="取不到"):
        A.approve(c, d, "om_nope", f)
    with pytest.raises(A.ApprovalError, match="approval_chat_id"):
        A.approve(cfg(approval_chat_id=""), d, message(f, f"批准 {pl['plan_id'][:8]}"), f)
    with pytest.raises(A.ApprovalError, match="self_open_id"):
        A.approve({**c, "self_open_id": None}, d, message(f, f"批准 {pl['plan_id'][:8]}"), f)
    with pytest.raises(A.ApprovalError, match="找不到唯一"):
        A.find(d, "ffffffff", ("pending",))
    with pytest.raises(A.ApprovalError, match="没有登记"):
        A.reverify(c, d, pl["plan_id"], f)
    d.close()


def test_api_sent_by_user_token_is_indistinguishable(tmp_path):
    """元数据核验：sender_type=app（机器人/应用发的）被拒；但用本人用户令牌经接口发的消息，元数据与手打一致（sender_type=user，无 app_id 字段），无法区分——这是已记录的残余风险。"""
    d, f, c, pl = setup(tmp_path)
    assert A.approve(c, d, message(f, f"批准 {pl['plan_id'][:8]}", sender_type="user"), f)["approved"]
    d.close()


def test_extra_kind_needs_its_own_number(tmp_path):
    d, f, c, _ = setup(tmp_path)
    items = [
        {"idx": 1, "kind": "rename", "chat_id": "oc_a", "person": None, "name": "n"},
        {"idx": 2, "kind": "disband", "chat_id": "oc_a", "person": None},
    ]
    pid = "ab12cd34" + "0" * 56
    d.execute("insert into org_plans(plan_id,items_json,status) values(?,?,'pending')", (pid, json.dumps(items)))
    d.commit()
    assert A.approve(c, d, message(f, "批准 ab12cd34"), f)["approved"] == [1]
    assert A.approve(c, d, message(f, "批准 ab12cd34 2"), f)["approved"] == [1, 2]
    d.close()


def test_apply_reverifies(tmp_path):
    d, f, c, pl = setup(tmp_path)
    mid = message(f, f"批准 {pl['plan_id'][:8]}")
    A.approve(c, d, mid, f)
    log = []
    f.messages[mid]["text"] = "批准 00000000"  # 审批后消息被改（或换成别的）
    with pytest.raises(A.ApprovalError):
        AP.run(c, d, pl["plan_id"][:8], reader=f, runner=log.append)
    del f.messages[mid]
    with pytest.raises(A.ApprovalError, match="取不到"):
        AP.run(c, d, pl["plan_id"][:8], reader=f, runner=log.append)
    with pytest.raises(A.ApprovalError, match="审批单聊"):
        (
            f.messages.__setitem__(
                mid,
                {
                    "message_id": mid,
                    "chat_id": "oc_x",
                    "sender": "ou_me",
                    "sender_type": "user",
                    "create_ms": (int(time.time()) + 60) * 1000,
                    "msg_type": "text",
                    "text": f"批准 {pl['plan_id'][:8]}",
                    "deleted": False,
                },
            ),
            AP.run(c, d, pl["plan_id"][:8], reader=f, runner=log.append),
        )
    other_pid = "cc34dd56" + "0" * 56
    d.execute(
        "insert into org_plans(plan_id,items_json,status,approved_items) values(?,'[]','approved','[]')", (other_pid,)
    )
    d.commit()
    f.messages[mid] = {
        "message_id": mid,
        "chat_id": "oc_appr",
        "sender": "ou_me",
        "sender_type": "user",
        "create_ms": (int(time.time()) + 60) * 1000,
        "msg_type": "text",
        "text": "批准 cc34dd56",
        "deleted": False,
    }
    with pytest.raises(A.ApprovalError, match="对应的计划不符"):
        A.reverify(c, d, pl["plan_id"], f)
    assert log == []
    d.close()


def test_approval_24h_window_consistent_before_and_after_v5_and_compat(tmp_path):
    """点名测试：兼容旧的秒级 Z 值与 +08:00 值；24 小时审批窗口在 v4→v5 迁移前后（含 sent_at 秒转 .000Z、新写存毫秒）判断一致。"""
    assert A._utc("2026-10-19T12:00:00Z") == A._utc("2026-10-19T12:00:00.000Z") == A._utc("2026-10-19T20:00:00+08:00")
    assert A.bj("2026-10-19T12:00:00.000Z") == "2026-10-19 20:00:00（北京时间）"
    p = tmp_path / "v4.db"
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=4)
    for v in (1, 2, 3, 4):
        migrations._record(d, v, "x")
    f = fake_big()
    c = cfg()
    pl = P.compute(c, f)
    pid = pl["plan_id"]
    base = 1792411200  # 2026-10-19T12:00:00Z
    d.execute(
        "insert into org_plans(plan_id,items_json,held_json,status,created_at,updated_at) values(?,?,?,'pending','2026-10-19T12:00:00Z','2026-10-19T12:00:00Z')",
        (pid, P.json.dumps(pl["items"], sort_keys=True), "[]"),
    )
    ok_mid = message(f, f"批准 {pid[:8]}", create_ms=(base + 3600) * 1000 + 456)
    late_mid = message(f, f"批准 {pid[:8]}", create_ms=(base + 25 * 3600) * 1000)
    assert A.verify(c, d, ok_mid, ("pending", "approved"), f)[0] == pid
    with pytest.raises(A.ApprovalError, match="24 小时"):
        A.verify(c, d, late_mid, ("pending", "approved"), f)
    d.execute(
        "insert into org_approvals(message_id,plan_id,sender,chat_id,sent_at,text,created_at,updated_at) values(?,?,?,?,?,?,?,?)",
        (ok_mid, pid, "ou_me", "oc_ap", base + 3600, f"批准 {pid[:8]}", "2026-10-19T13:00:00Z", "2026-10-19T13:00:00Z"),
    )
    d.execute("update org_plans set status='approved',approved_items='[1, 2]' where plan_id=?", (pid,))
    d.close()
    assert migrations.migrate(p) == [5]
    d = sqlite3.connect(str(p))
    assert (
        d.execute("select sent_at from org_approvals where message_id=?", (ok_mid,)).fetchone()[0]
        == "2026-10-19T13:00:00.000Z"
    )
    assert A.verify(c, d, ok_mid, ("pending", "approved"), f)[0] == pid
    with pytest.raises(A.ApprovalError, match="24 小时"):
        A.verify(c, d, late_mid, ("pending", "approved"), f)
    assert A.reverify(c, d, pid, f) == ["2026-10-19 21:00:00（北京时间）"]
    mid2 = message(f, f"批准 {pid[:8]}", create_ms=(base + 7200) * 1000 + 789)
    A.approve(c, d, mid2, f)
    assert d.execute("select sent_at from org_approvals where message_id=?", (mid2,)).fetchone()[0].endswith(".789Z")
    d.close()
