from quanttide_academy.intent import roles, validate_roles
from quanttide_academy.intent.item import render_card
from quanttide_academy.intent.validate import validate, warnings
from tests.helpers import *

CFG = {
    "labels": {"priority_names": PN},
    "self_open_id": "ou_demo_self",
    "user": {"display_name": "示例用户", "roles": ["示例负责人"]},
}


def test_check_ok_and_user_basis_needs_promotion():
    it = copy.deepcopy(EX["items"][1])
    meta = fixture_msgs()
    msgs = {k: v["text"] for k, v in meta.items()}
    assert validate_roles.check(it, "#2", msgs, meta, CFG) == []
    it["assignees"][0]["basis"] = "reply"
    assert any("升格" in e for e in validate_roles.check(it, "#2", msgs, meta, CFG))
    assert validate_roles.check(it, "#2", msgs, meta, CFG, promoted={2}) == []


def test_personal_needs_exactly_one_and_pending_type():
    it = copy.deepcopy(EX["items"][2])
    it["task_type"] = "personal"
    assert any("恰好 1 人" in e for e in validate_roles.check(it, "#3", None, {}, CFG))
    it["task_type"] = None
    assert validate_roles.check(it, "#3", None, {}, CFG) == []


def test_quote_two_tiers():
    it = copy.deepcopy(EX["items"][1])
    meta = fixture_msgs()
    me = {
        "name": "示例用户",
        "open_id": "ou_demo_self",
        "basis": "quote",
        "evidence": "活动报名表请@小李 负责收集",
        "message_id": "om_demo_2",
    }
    it["consultees"] = [me]
    named = meta["om_demo_2"]["text"] + " 示例用户"
    ext = {**meta, "om_demo_2": {**meta["om_demo_2"], "text": named, "sender_external": True, "mentions_self": False}}
    e = validate_roles.check(it, "#2", {k: v["text"] for k, v in ext.items()}, ext, CFG)
    assert any("外部成员的消息只认 @ 用户" in x for x in e)
    assert roles.derive_actions({**it, "reviewers": [], "consultees": [{**me, "open_id": None}]}, CFG) == ["指派"]
    inn = {**meta, "om_demo_2": {**meta["om_demo_2"], "text": named, "sender_external": False, "mentions_self": False}}
    assert validate_roles.check(it, "#2", {k: v["text"] for k, v in inn.items()}, inn, CFG) == []
    it["consultees"] = [{**me, "open_id": None}]
    assert any(
        "open_id 必须写用户的 open_id" in x
        for x in validate_roles.check(it, "#2", {k: v["text"] for k, v in inn.items()}, inn, CFG)
    )
    ext2 = {**ext, "om_demo_2": {**ext["om_demo_2"], "mentions_self": True}}
    it["consultees"] = [me]
    assert validate_roles.check(it, "#2", {k: v["text"] for k, v in ext2.items()}, ext2, CFG) == []


def test_unknown_basis_lists_all_values():
    it = copy.deepcopy(EX["items"][0])
    it["assignees"][0]["basis"] = "guess"
    e = "\n".join(validate_roles.check(it, "#1", None, {}, CFG))
    assert all(v in e for v in ("quote", "role", "reply", "rule")) and "'guess'" in e


def test_system_message_rejected_in_role_inference():
    it = copy.deepcopy(EX["items"][0])
    meta = fixture_msgs()
    meta["om_demo_1"] = {**meta["om_demo_1"], "system": True, "speaker": "（系统消息）"}
    msgs = {k: v["text"] for k, v in meta.items()}
    e = "\n".join(validate_roles.check(it, "#1", msgs, meta, CFG))
    assert "系统消息" in e and "不参与角色推断" in e
    it2 = copy.deepcopy(EX["items"][0])
    it2["links"] = [{"message_id": "om_demo_1", "quote": "q"}]
    it2["assignees"] = [{"name": "示例用户", "open_id": "ou_demo_self", "basis": "role", "evidence": "示例负责人"}]
    e2 = "\n".join(validate_roles.check(it2, "#1", msgs, meta, CFG))
    assert "系统消息不参与角色推断" in e2


def test_role_basis_and_mentions_rule():
    cfg = {**CFG, "user": {"display_name": "小明", "roles": ["实训基地负责人"]}}
    t = copy.deepcopy(EX)
    it = t["items"][1]
    nom = no_self_mention(fixture_msgs())
    it["reviewers"] = [
        {
            "name": "小明",
            "open_id": "ou_demo_self",
            "basis": "quote",
            "evidence": "活动报名表请@小李 负责收集",
            "message_id": "om_demo_2",
        }
    ]
    assert any("没有 @ 或点名用户" in e for e in validate(t, nom, cfg))
    it["reviewers"] = [{"name": "小明", "open_id": "ou_demo_self", "basis": "role", "evidence": "实训基地负责人"}]
    assert any("不能按角色推断" in e for e in validate(t, fixture_msgs(), cfg))
    it["reviewers"] = [
        {
            "name": "小明",
            "open_id": "ou_demo_self",
            "basis": "quote",
            "evidence": "周五前交给〔我〕审核",
            "message_id": "om_demo_2",
        }
    ]
    assert validate(t, fixture_msgs(), cfg) == []
    full = {
        **it,
        "links": [
            {
                "url": "u",
                "message_id": "om_demo_2",
                "direct": True,
                "time": "10-19 10:05",
                "quote": it["links"][0]["quote"],
            }
        ],
    }
    c = render_card(full, cfg)
    assert "行动：评审\n" in c and "评审员：执行员 -> 小明" in c and "执行员：小李" in c
    s = copy.deepcopy(EX)
    s["items"][0]["assignees"] = [
        {"name": "示例用户", "open_id": "ou_demo_self", "basis": "role", "evidence": "不存在的角色"}
    ]
    assert any("user.roles" in e for e in validate(s, fixture_msgs(), cfg))
    s["items"][0]["assignees"][0]["evidence"] = "实训基地负责人"
    assert validate(s, fixture_msgs(), cfg) == []
    s["items"][0]["assignees"].append({"name": "小李", "open_id": "ou_demo_li", "basis": "role", "evidence": "组员"})
    s["items"][0]["task_type"] = "team"
    assert sum("按角色推断只允许" in e for e in validate(s, fixture_msgs(), cfg)) == 2


def test_counter_example_assign_card(env):
    cfg, tmp = env
    t = json.loads((ROOT / "tests" / "fixtures" / "topics_counter.json").read_text(encoding="utf-8"))
    prepare(cfg, tmp, topics=t, messages="messages_counter.json")
    rc, r = run("validate", "b1")
    assert rc == 20 and "不能按角色推断" in r["reason"]
    t["items"][1]["reviewers"] = []
    prepare(cfg, tmp, b="b2", topics=t, messages="messages_counter.json")
    assert run("validate", "b2")[0] == 0
    _rc, r = run("render", "b2")
    cards = (tmp / "w" / "b2" / "cards.txt").read_text(encoding="utf-8")
    blk = cards.split("【#2】")[1].split("【#3】")[0]
    assert r["to_assign"] == 1 and "行动：指派" in blk and "审批人：示例用户（按规则：执行员是别人）" in blk
    it = json.loads((tmp / "w" / "b2" / "topics.json").read_text(encoding="utf-8"))["items"][1]
    assert roles.approver(it, cfg)["basis"] == "rule"


def test_role_hard_rules():
    def errs(f):
        t = copy.deepcopy(EX)
        f(t["items"])
        return "\n".join(validate(t, fixture_msgs(), CFG))

    li = {"name": "小王", "open_id": None, "basis": "role", "evidence": "组长"}
    assert "恰好 1 人" in errs(lambda I: I[1]["assignees"].append(li))
    assert "缺依据" in errs(lambda I: I[1]["assignees"][0].update(evidence=""))
    assert "须含 name" in errs(lambda I: I[1]["assignees"][0].pop("basis"))
    assert "不在执行员、评审员或咨询对象里" in errs(
        lambda I: I[1]["ddl_by_person"].append({"person": "路人", "date": "2026-10-30", "basis": "x"})
    )
    assert "与角色推导结果 [] 不一致" in errs(lambda I: I[2].update(actions=["执行"]))
    assert "纯资讯（kind=info）不能有执行员" in errs(
        lambda I: I[2].update(assignees=I[0]["assignees"], task_type="personal")
    )
    assert "含执行任务" in errs(lambda I: I[2].update(subtasks=["做点事"]))
    assert "kind 只能是" in errs(lambda I: I[0].update(kind="x"))
    assert "basis=rule（审批人）只由程序推导" in errs(lambda I: I[1]["reviewers"][0].update(basis="rule"))
    assert "叠加审批人" in errs(
        lambda I: I[0].update(
            approvers=[{"name": "示例用户", "open_id": "ou_demo_self", "basis": "rule", "evidence": "x"}]
        )
    )
    assert "与角色推导结果" in errs(lambda I: I[1].update(actions=["执行"]))
    assert errs(lambda I: I[1].update(actions=["评审"])) == ""
    assert "basis=reply 只由程序" in errs(lambda I: I[1]["assignees"][0].update(basis="reply"))
    assert "已有执行员时 task_type" in errs(lambda I: I[0].update(task_type=None))


def test_no_open_id_never_self():
    it = copy.deepcopy(EX["items"][1])
    it["reviewers"] = [{"name": "示例用户", "open_id": None, "basis": "role", "evidence": "示例负责人"}]
    assert (
        roles.own_roles(it, CFG) == []
        and roles.derive_actions(it, CFG) == ["指派"]
        and roles.category(it, CFG) == "card"
    )
    assert any("没有你的 open_id" in w for w in warnings({"items": [it]}, {}, CFG))
    assert roles.derive_actions(it, {**CFG, "self_open_id": None}) == []
