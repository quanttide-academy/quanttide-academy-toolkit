import sqlite3
import time

from quanttide_academy.core import migrations, paths

TTL = 3600


class NeedsMigration(RuntimeError):
    pass


def connect(cfg):
    path = paths.state_db(cfg)
    d = sqlite3.connect(str(path), timeout=30)
    if migrations.is_legacy(d) or (migrations.applied(d) and max(migrations.applied(d)) < migrations.LATEST):
        d.close()
        raise NeedsMigration(f"state.db 是旧版表结构，先运行：python scripts/migrate.py（会自动备份）。库：{path}")
    if not migrations.applied(d):
        d.close()
        migrations.migrate(path)
        d = sqlite3.connect(str(path), timeout=30)
    return d


class Locked(RuntimeError):
    pass


def holder(d, name="run"):
    r = d.execute("select owner,expires from run_locks where name=?", (name,)).fetchone()
    return r if r and r[1] >= int(time.time()) else None


def cleanup_orphans(d, keep=None):
    """清掉未收尾且锁已过期的批次：只删未推送的消息和暂存游标。"""
    live = holder(d)
    live = live[0] if live else None
    for (b,) in d.execute(
        "select distinct batch from watch_pending_cursors union select distinct batch from messages where pushed=0"
    ).fetchall():
        if b not in (live, keep):
            d.execute("delete from watch_pending_cursors where batch=?", (b,))
            d.execute("delete from messages where batch=? and pushed=0", (b,))


def acquire(d, batch, name="run", ttl=TTL):
    """整轮锁：fetch 时按批次加锁，commit/abort 才释放；已有别的批次未收尾则拒绝。"""
    now = int(time.time())
    with d:
        h = holder(d)
        if h and h[0] != batch:
            raise Locked(f"批次 {h[0]} 尚未收尾，本轮不启动")
        d.execute("delete from run_locks where name=?", (name,))
        d.execute("insert into run_locks(name,owner,expires) values(?,?,?)", (name, batch, now + ttl))


def require(d, batch, name="run"):
    h = holder(d)
    if not h or h[0] != batch:
        raise Locked(f"批次 {batch} 不持有运行锁（可能已超时被清理）")
    with d:
        d.execute("update run_locks set expires=? where name=?", (int(time.time()) + TTL, name))


def release(d, batch, name="run"):
    with d:
        d.execute("delete from run_locks where name=? and owner=?", (name, batch))


def renew(d, batch, name="run", ttl=TTL):
    """续锁：锁空闲或本批持有则续期；被别的批次持有则抛 Locked（退出码 30）。"""
    acquire(d, batch, name, ttl)
