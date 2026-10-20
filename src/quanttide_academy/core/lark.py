"""调用 lark-cli：可注入 Runner、列表形式、不用 shell；Windows 上 shutil.which 会找到 lark-cli.cmd。"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from quanttide_academy import settings


class LarkError(RuntimeError):
    pass


class WriteBlocked(LarkError):
    pass


READ_SHORTCUTS = {"+chat-list"}


def find(cfg) -> str:
    explicit = ((cfg or {}).get("lark_cli") or {}).get("path") or settings.lark_cli_bin()
    if explicit:
        if Path(explicit).exists():
            return str(explicit)
        raise LarkError(f"配置的 lark-cli 路径不存在：{explicit}")
    local = Path.home() / ".local" / "bin"
    found = shutil.which("lark-cli") or shutil.which("lark-cli", path=str(local))
    if not found:
        raise LarkError(
            "找不到 lark-cli：请在自己的电脑上安装 Node.js LTS 和飞书官方 lark-cli，用本人账号登录并授权用户身份；或在 config 的 lark_cli.path 填完整路径"
        )
    return found


def _try_json(s: str):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def extract_json(out: str) -> list:
    """先整段解析；失败再取第一个 { 到最后一个 } 之间的内容（支持多页连续 JSON 对象）。"""
    s = (out or "").strip()
    if not s:
        return []
    v = _try_json(s)
    if isinstance(v, dict):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    a = s.find("{")
    b = s.rfind("}")
    if a == -1 or b == -1 or a >= b:
        return []
    sub = s[a : b + 1]
    v = _try_json(sub)
    if isinstance(v, dict):
        return [v]
    objs = []
    dec = json.JSONDecoder()
    i = 0
    while i != -1 and i < len(sub):
        try:
            o, j = dec.raw_decode(sub, i)
            if isinstance(o, dict):
                objs.append(o)
            i = sub.find("{", j)
        except json.JSONDecodeError:
            i = sub.find("{", i + 1)
    return objs


parse = extract_json


def guard(args):
    """本模块只读：api 只允许 GET；快捷命令只允许白名单里的只读命令。"""
    a = list(args)
    if a[:1] == ["api"]:
        if len(a) < 2 or a[1].upper() != "GET":
            raise WriteBlocked(f"只读客户端拒绝 {a[1] if len(a) > 1 else '?'} 请求")
    elif not any(x in READ_SHORTCUTS for x in a):
        raise WriteBlocked(f"只读客户端拒绝命令：{' '.join(a[:2])}")


class SubprocessRunner:
    """默认子进程 Runner；exe 为 .py 时经 sys.executable 启动（跨 Windows/macOS/Linux）。"""

    def run(self, cfg, args: list, timeout: int = 120) -> str:
        exe = find(cfg)
        cmd = [sys.executable, exe, *args] if str(exe).endswith(".py") else [exe, *args]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as e:
            raise LarkError("lark-cli 超时") from e
        if r.returncode != 0:
            raise LarkError(f"lark-cli 退出码 {r.returncode}：{(r.stderr or r.stdout)[-300:]}")
        return r.stdout


DEFAULT_RUNNER = SubprocessRunner()


def _invoke(runner, cfg, args: list, timeout: int) -> str:
    if hasattr(runner, "run"):
        return runner.run(cfg, args, timeout)
    try:
        return runner(cfg, args, timeout)
    except TypeError:
        return runner(args)


def call(cfg, *args, timeout=120, runner=None) -> list:
    guard(args)
    rn = runner or ((cfg or {}).get("lark_cli") or {}).get("runner") or (cfg or {}).get("_runner") or DEFAULT_RUNNER
    raw = _invoke(rn, cfg, list(args), timeout)
    objs = extract_json(raw) if isinstance(raw, str) else list(raw)
    if not objs:
        raise LarkError("lark-cli 无 JSON 输出（可能令牌过期）")
    for o in objs:
        if o.get("ok") is False or o.get("code") not in (None, 0):
            raise LarkError(f"飞书接口错误 {o.get('code')}：{o.get('msg') or o.get('error') or 'ok=false'}")
    if "--page-all" in args:
        limit = settings.max_pages(cfg)
        last = objs[-1]
        more = bool((last.get("data") or {}).get("has_more") or last.get("has_more"))
        if len(objs) > limit or more:
            raise LarkError(f"lark-cli 翻页超过上限 max_pages={limit} 或未拉完（has_more=true），拒绝截断")
    return objs
