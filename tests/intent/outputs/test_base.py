import pytest

from quanttide_academy.intent.outputs.base import Adapter


def test_degrade_moves_unsupported_fields_to_note(tmp_path):
    a = Adapter({}, {"paths": {"data_dir": str(tmp_path)}})
    note = a.degrade({"note": "n", "priority": "P1", "labels": ["x", "y"], "ddl": "2026-10-21"})
    assert note.splitlines() == ["n", "优先级：P1", "标签：x、y", "截止：2026-10-21"]
    with pytest.raises(NotImplementedError):
        a.create({})
