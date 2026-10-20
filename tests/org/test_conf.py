import pytest
import yaml

from quanttide_academy.org import conf as C
from tests.helpers import ROOT
from tests.org.helpers import cfg


def test_defaults_off_and_bounds():
    oc = C.load({})
    assert (
        oc.enabled is False
        and oc.allow == {"create": False, "disband": False, "transfer": False}
        and oc.max_items == 20
        and oc.root is None
        and oc.approval_chat_id is None
    )
    with pytest.raises(C.BadOrgConfig, match="max_items"):
        C.load(cfg(max_items=21))
    with pytest.raises(C.BadOrgConfig, match="一个群"):
        C.load(cfg(mappings=[{"chat_id": "oc_a", "department": "od_a"}, {"chat_id": "oc_a", "department": "od_f"}]))
    with pytest.raises(C.BadOrgConfig, match="oc_"):
        C.load(cfg(mappings=[{"chat_id": "x", "department": "od_a"}]))
    with pytest.raises(C.BadOrgConfig, match="protected"):
        C.load(cfg(protected=["bad"]))


def test_hold_needs_reason_and_old_keys_rejected():
    with pytest.raises(C.BadOrgConfig, match="hold_reason"):
        C.load(cfg(mappings=[{"chat_id": "oc_a", "department": "od_a", "hold": True}]))
    with pytest.raises(C.BadOrgConfig, match="hold"):
        C.load(cfg(mappings=[{"chat_id": "oc_a", "department": "od_a", "hold": "yes", "hold_reason": "r"}]))
    with pytest.raises(C.BadOrgConfig, match="废弃"):
        C.load(cfg(on_hold=["od_f"]))
    with pytest.raises(C.BadOrgConfig, match="废弃"):
        C.load(cfg(root_name="实训基地"))
    m = C.load(cfg(mappings=[{"chat_id": "oc_a", "department": "od_a", "hold": True, "hold_reason": "r"}])).mappings[0]
    assert m["hold"] and m["hold_reason"] == "r"


def test_example_config_holds_four_groups_not_congress():
    t = (ROOT / "src" / "quanttide_academy" / "core" / "config.example.yaml").read_text(encoding="utf-8")
    oc = C.load(yaml.safe_load(t))
    held = [m for m in oc.mappings if m["hold"]]
    assert len(held) == 4 and all(m["hold_reason"] for m in held) and oc.enabled is False
    for n in ("创始人部", "秘书处", "运营部", "游戏部"):
        assert n in t
    assert "代表大会" not in t and oc.approval_chat_id is None
