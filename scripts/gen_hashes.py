"""从本地（不入库）的配置和数据里收集真实姓名、群名、chat_id、open_id，只把 HMAC-SHA256 写进 data/sensitive_hashes.txt。
来源：config.yaml、data/*.json、data/sensitive-names.txt（每行一个名字）、data/work/**/messages.json 的发言人。密钥经 settings 读环境变量。"""

import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from feishu_workflows import settings

ID = re.compile(r"\b(?:oc|ou|om|on)_[0-9A-Za-z]{16,}\b")


def digest(key: bytes, val: str) -> str:
    return hmac.new(key, val.encode("utf-8"), hashlib.sha256).hexdigest()


def collect():
    vals = set()
    texts = []
    for p in [ROOT / "config.yaml", *sorted((ROOT / "data").glob("*.json"))]:
        if p.exists():
            texts.append(p.read_text(encoding="utf-8"))
    for t in texts:
        vals |= set(ID.findall(t))
        vals |= set(re.findall(r'"name":\s*"([^"]+)"', t)) | set(re.findall(r"name:\s*(\S+)", t))
    n = ROOT / "data" / "sensitive-names.txt"
    if n.exists():
        vals |= {
            line.strip()
            for line in n.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    for m in (ROOT / "data" / "work").rglob("messages.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for x in data.get("messages", data if isinstance(data, list) else []):
            if isinstance(x, dict):
                for k in ("sender", "sender_name", "speaker", "chat", "chat_name"):
                    v = x.get(k)
                    if isinstance(v, str) and v.strip():
                        vals.add(v.strip())
                vals |= set(ID.findall(json.dumps(x, ensure_ascii=False)))
    return {v for v in vals if len(v) >= 2}


def main():
    key = settings.sensitive_hmac_key()
    if not key:
        print(f"未设置环境变量 {settings.SENSITIVE_HMAC_ENV}，拒绝生成敏感哈希", file=sys.stderr)
        return 1
    hs = sorted({digest(key, v) for v in collect()})
    out = settings.sensitive_hashes_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# 真实姓名/群名/ID 的 HMAC-SHA256（明文与哈希均不入库），由 scripts/gen_hashes.py 生成\n"
        + "\n".join(hs)
        + "\n",
        encoding="utf-8",
    )
    print(f"写入 {len(hs)} 条 HMAC 哈希：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
