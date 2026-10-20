"""org depts 建议：根部门、暂缓部门最接近名字（或无匹配）、群→部门按成员重合；只读、写本地文件。虚构数据。"""

from pathlib import Path

from quanttide_academy.org import depts as D
from tests.org.test_plan import fake_big


def test_suggestions(tmp_path):
    f = fake_big()
    f.data["tree"] += [
        {"id": "od_s", "name": "秘书处（筹）", "parent": "od_root"},
        {"id": "od_y", "name": "运营中心", "parent": "od_root"},
    ]
    s = D.suggest({}, f)
    assert (
        s["root"]["id"] == "od_root"
        and s["holds"]["创始人部"]["id"] == "od_f"
        and s["holds"]["秘书处"]["id"] == "od_s"
        and s["holds"]["游戏部"] is None
    )
    m = {x["chat"]["chat_id"]: (x["dept"]["id"], x["overlap"]) for x in s["mappings"]}
    assert (
        m["oc_a"][0] == "od_a" and m["oc_a"][1] == 7 and m["oc_f"] == ("od_f", 1)
    )  # od_a 含子部门成员；按 Jaccard 不会选到根部门
    p = D.write({"paths": {"data_dir": str(tmp_path)}}, s)
    t = Path(p).read_text(encoding="utf-8")
    assert "建议勾选" in t and "无匹配" in t and "重合 7/" in t and "od_root" in t


def test_root_ambiguous_or_missing():
    f = fake_big()
    f.data["tree"].append({"id": "od_r2", "name": "二号实训基地", "parent": "0"})
    s = D.suggest({}, f)
    assert s["root"] is None and s["root_candidates"] == 2
    assert D.closest([], "x") is None
