"""scripts/migrate.py：sqlite3 backup() 在线备份，备份能打开且 integrity_check=ok 才迁移。"""

import importlib.util
import sqlite3

import pytest

from feishu_workflows.core import migrations
from tests.helpers import ROOT

spec = importlib.util.spec_from_file_location("mig", ROOT / "scripts" / "migrate.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def v2db(p, lock=False):
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=2)
    migrations._record(d, 1, "b")
    migrations._record(d, 2, "x")
    d.execute("insert into topics(fingerprint,title) values('f','t')")
    if lock:
        d.execute("insert into run_locks(name,owner,expires) values('run','b1',9999999999)")
    d.close()


def test_backup_uses_sqlite_backup_and_verifies(tmp_path):
    p = tmp_path / "s.db"
    v2db(p)
    bak = M.backup(p, tmp_path / "bk")
    d = sqlite3.connect(str(bak))
    assert (
        d.execute("pragma integrity_check").fetchone()[0] == "ok"
        and d.execute("select count(*) from topics").fetchone()[0] == 1
    )
    d.close()
    assert bak != M.backup(p, tmp_path / "bk")  # 不覆盖已有备份
    assert "copy2" not in (ROOT / "scripts" / "migrate.py").read_text(encoding="utf-8")


def test_backup_rejects_corrupt(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"not a database" * 100)
    with pytest.raises(M.BackupFailed):
        M.backup(p, tmp_path / "bk")


def test_main_backs_up_then_migrates_or_refuses_lock(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(M, "default_data_dir", lambda: tmp_path / "bk")
    p = tmp_path / "s.db"
    v2db(p)
    assert M.main(["x", str(p)]) == 0
    d = sqlite3.connect(str(p))
    assert migrations.applied(d) == set(migrations.NAMES)
    d.close()
    q = tmp_path / "l.db"
    v2db(q, lock=True)
    assert M.main(["x", str(q)]) == 1 and "拒绝迁移" in capsys.readouterr().out
