from quanttide_academy_toolkit.intent import names
from tests.helpers import *


def fake(calls, members, contacts):
    def call(cfg, *a, **k):
        calls.append(a)
        assert a[0] == "api" and a[1] == "GET"  # 只读
        if "/members" in a[2]:
            return [
                {
                    "code": 0,
                    "data": {"items": [{"member_id": o, "name": n, "tenant_key": "t"} for o, n in members.items()]},
                }
            ]
        oid = a[2].rsplit("/", 1)[1]
        n = contacts.get(oid)
        return [{"code": 0, "data": {"user": {"name": n, "mobile": "13800000000", "email": "a@b.c"} if n else {}}}]

    return call


def test_members_then_contact_and_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(names.larkcli, "call", fake(calls, {"ou_a": "甲"}, {"ou_b": "乙"}))
    p = tmp_path / "name_cache.json"
    msgs = [
        {"chat_id": "oc_1", "sender_open_id": "ou_a", "mentions": ["ou_b"]},
        {"chat_id": "oc_1", "sender_open_id": "ou_c", "mentions": []},
    ]
    assert (
        names.fill({}, msgs, p, now=1000) == 1
        and msgs[0]["speaker"] == "甲"
        and msgs[0]["people"] == {"ou_a": "甲", "ou_b": "乙"}
        and "speaker" not in msgs[1]
    )
    assert any("/members" in c[2] for c in calls) and any("/contact/v3/users/ou_b" in c[2] for c in calls)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw == {
        "ou_a": {"name": "甲", "at": 1000},
        "ou_b": {"name": "乙", "at": 1000},
    }  # 只存姓名与时间，不存手机号、邮箱
    calls.clear()
    names.fill({}, [{"chat_id": "oc_1", "sender_open_id": "ou_a", "mentions": []}], p, now=1000 + 3600)
    assert calls == []  # 命中缓存不再调用
    assert names.load(p, now=1000 + names.TTL + 1) == {}  # 7 天过期


def test_lark_errors_leave_unknown(tmp_path, monkeypatch):
    def boom(cfg, *a, **k):
        raise names.larkcli.LarkError("x")

    monkeypatch.setattr(names.larkcli, "call", boom)
    m = [{"chat_id": "oc", "sender_open_id": "ou_z"}]
    assert names.fill({}, m, tmp_path / "c.json") == 0 and "speaker" not in m[0]


def test_cache_gitignored():
    r = subprocess.run(
        ["git", "check-ignore", "data/name_cache.json"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0


def test_departments_read_only_and_cached(tmp_path, monkeypatch):
    calls = []
    dept_items = [
        {"department_id": "od_demo_root", "name": "示例总部", "parent_department_id": "0"},
        {"department_id": "od_demo_1", "name": "示例部", "parent_department_id": "od_demo_root"},
    ]

    def call(cfg, *a, **k):
        calls.append(a)
        assert (
            a[:2] == ("api", "GET") and "/contact/v3/departments/" in a[2] and a[a.index("--as") + 1] == "bot"
        )  # 应用身份（用户身份查不到部门）
        return [{"code": 0, "data": {"items": dept_items, "has_more": False}}]

    monkeypatch.setattr(names.larkcli, "call", call)
    p = tmp_path / "dept_names.json"
    assert names.departments({}, p, now=10) == ["示例总部", "示例部"] and json.loads(p.read_text(encoding="utf-8")) == {
        "names": ["示例总部", "示例部"],
        "at": 10,
    }
    assert names.departments({}, p, now=20) == ["示例总部", "示例部"] and len(calls) == 1
