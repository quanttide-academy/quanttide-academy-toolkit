"""把 state.db 迁到最新表结构。先用 sqlite3 backup() 在线备份到 data/backup-state-<时间>.db，备份须能打开且 integrity_check=ok 才迁；运行锁非空则拒绝（migrate() 内检查）。可重复执行。
用法：python scripts/migrate.py [state.db 路径]（省略则按 config.yaml 的 paths.state_db）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quanttide_academy_toolkit.core import config, migrations, paths
from quanttide_academy_toolkit.settings import default_data_dir

BackupFailed = migrations.BackupFailed
backup = migrations.backup


def main(argv):
    cfg = config.load() if config.config_path().exists() else {}
    db = Path(argv[1]) if len(argv) > 1 else paths.state_db(cfg)
    if not db.exists():
        print(f"没有库：{db}（新库会在首次运行时按最新结构创建）")
        return 0
    try:
        bak = backup(db, default_data_dir())
    except BackupFailed as e:
        print(f"拒绝迁移：{e}")
        return 1
    print(f"已备份并校验：{bak}")
    try:
        done = migrations.migrate(db, cfg=cfg or None, backup_path=bak)
    except (migrations.LockHeld, BackupFailed) as e:
        print(f"拒绝迁移：{e}")
        return 1
    print("已应用版本：" + (",".join(map(str, done)) if done else "无（已是最新）"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
