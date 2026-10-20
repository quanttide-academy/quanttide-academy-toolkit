import contextlib
import sqlite3

from feishu_workflows.core import db
from tests import conftest
from tests.helpers import *


def test_lock(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path)}}
    with contextlib.closing(db.connect(cfg)) as d:
        db.acquire(d, "A")
        with contextlib.closing(db.connect(cfg)) as d2, pytest.raises(db.Locked):
            db.acquire(d2, "B")
        db.require(d, "A")
        with pytest.raises(db.Locked):
            db.require(d, "B")
        db.release(d, "A")
        db.acquire(d, "B")


def test_orphan_cleanup_and_dedup(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path)}}
    with contextlib.closing(db.connect(cfg)) as d:
        d.execute("insert into messages(message_id,batch,pushed) values('m1','old',0),('m2','old',1)")
        d.execute("insert into watch_pending_cursors(batch,target_key,chat_id,last_ts) values('old','ou_a','oc',1)")
        db.cleanup_orphans(d, keep="new")
        assert [r[0] for r in d.execute("select message_id from messages")] == ["m2"]
        assert d.execute("select count(*) from watch_pending_cursors").fetchone()[0] == 0


def test_conftest_guard_fails_on_unclosed_connection():
    mp = pytest.MonkeyPatch()
    g = conftest._guard_unclosed_sqlite.__wrapped__(mp)
    next(g)
    try:
        _leaked = sqlite3.connect(":memory:")
        with pytest.raises(pytest.fail.Exception, match="发现未关闭的 sqlite3 连接.*test_db.py"):
            next(g, None)
    finally:
        mp.undo()
