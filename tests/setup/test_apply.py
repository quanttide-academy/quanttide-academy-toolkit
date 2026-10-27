from quanttide_academy_toolkit.setup.apply import apply, migrate, prefill
from tests.helpers import *


def test_apply_rejects_secrets_and_writes_config(tmp_path):
    cp = tmp_path / "config.yaml"
    with pytest.raises(SystemExit):
        apply({"todo_provider": "todoist", "todo_token": "abc"}, str(cp))
    assert not cp.exists()
    with pytest.raises(SystemExit):
        apply({"todo_provider": "todoist", "todo_token_env": "0123456789abcdef0123456789abcdef0123"}, str(cp))
    out = apply(
        {
            "self_open_id": "ou_me",
            "watch": [{"name": "示例", "accounts": {"ou_x": "内部"}}],
            "todo_provider": "todoist",
            "todo_token_env": "FI_NOT_SET_ENV",
            "priority_names": PN,
        },
        str(cp),
    )
    assert out["self_check"]["todoist_token"] == "unset" and "FI_NOT_SET_ENV" not in os.environ
    c = yaml.safe_load(cp.read_text(encoding="utf-8"))
    assert c["todo"]["token_env"] == "FI_NOT_SET_ENV" and "follow_label" not in c["labels"]


def test_migrate_and_prefill(tmp_path):
    cp = tmp_path / "config.yaml"
    cp.write_text(yaml.safe_dump({"labels": {"priority_names": PN}}, allow_unicode=True), encoding="utf-8")
    migrate(str(cp), state_chats=[{"chat_id": "oc_syn_base", "name": "示例基地群"}])
    c = yaml.safe_load(cp.read_text(encoding="utf-8"))
    assert c["scope"] == {
        "include_chats": [],
        "pending_chats": [{"chat_id": "oc_syn_base", "name": "示例基地群", "external": False}],
    }
    assert migrate(str(cp), state_chats=[])["changed"] is False
    lf = tmp_path / "local.json"
    lf.write_text(
        json.dumps([{"chat_id": "oc_syn_base", "name": "示例基地群", "external": True}], ensure_ascii=False),
        encoding="utf-8",
    )
    prefill(str(lf), str(cp))
    c = yaml.safe_load(cp.read_text(encoding="utf-8"))
    assert c["scope"]["include_chats"][0]["confirmed"] is True and c["scope"]["pending_chats"] == []
