import sqlite3

from quanttide_academy.core import migrations
from quanttide_academy.watch import cursors as C
from quanttide_academy.watch.targets import Target


def db(tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    return d


def test_start_points_min_over_targets(tmp_path):
    d = db(tmp_path)
    ts = [Target("ou_a", "甲", {"ou_a": "x"}), Target("ou_b", "乙", {"ou_b": "x"})]
    assert C.start_points(d, ts, ["oc_1"], init=100) == {"oc_1": {"start": 100, "targets": {"ou_a": 100, "ou_b": 100}}}
    C.stage(d, "b1", {("ou_a", "oc_1"): 500})
    C.commit(d, "b1")
    assert C.start_points(d, ts, ["oc_1"], init=100)["oc_1"]["start"] == 100  # 乙还没有游标：从 init 起
    C.stage(d, "b2", {("ou_b", "oc_1"): 300})
    C.commit(d, "b2")
    sp = C.start_points(d, ts, ["oc_1"], init=100)["oc_1"]
    assert sp["start"] == 300 and sp["targets"] == {"ou_a": 500, "ou_b": 300}
    d.close()


def test_stage_abort_does_not_advance(tmp_path):
    d = db(tmp_path)
    C.stage(d, "b1", {("ou_a", "oc_1"): 500})
    C.abort(d, "b1")
    assert (
        d.execute("select count(*) from watch_cursors").fetchone()[0] == 0
        and d.execute("select count(*) from watch_pending_cursors").fetchone()[0] == 0
    )
    d.close()


def test_commit_never_moves_backwards(tmp_path):
    d = db(tmp_path)
    C.stage(d, "b1", {("ou_a", "oc_1"): 500})
    C.commit(d, "b1")
    C.stage(d, "b2", {("ou_a", "oc_1"): 400})
    C.commit(d, "b2")
    assert d.execute("select last_ts from watch_cursors").fetchone()[0] == 500
    d.close()


def test_sync_targets(tmp_path):
    d = db(tmp_path)
    C.sync_targets(d, [Target("ou_a", "甲", {"ou_a": "x"})])
    C.sync_targets(d, [Target("ou_b", "乙", {"ou_b": "x"})])
    assert dict(d.execute("select key,active from watch_targets").fetchall()) == {"ou_a": 0, "ou_b": 1}
    d.close()
