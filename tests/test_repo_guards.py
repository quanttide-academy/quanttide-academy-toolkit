import hashlib
import hmac
import re

from quanttide_academy import settings
from quanttide_academy.core import lark as larkcli
from quanttide_academy.org import writer
from tests.helpers import *

SRC = ROOT / "src" / "quanttide_academy"
SPLIT_FILES = set(
    "cli/__init__.py cli/common.py cli/doctor.py cli/next_step.py setup/__init__.py setup/questions.py setup/apply.py intent/reply_parse.py intent/reply_handle.py intent/reply_assign.py intent/item_text.py intent/item_people.py intent/item_render.py".split()
)


def tracked():
    r = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [ROOT / x for x in r.stdout.splitlines() if (ROOT / x).is_file()]


def _tokens(t):
    base = set(re.findall(r"\b(?:oc|ou|om|on)_[0-9A-Za-z]{16,}\b", t)) | set(re.findall(r"[A-Za-z]{2,}", t))
    return base | {
        run[i : i + n]
        for run in re.findall(r"[\u4e00-\u9fff]+", t)
        for n in range(2, 9)
        for i in range(len(run) - n + 1)
    }


def test_no_recall_or_member_write_calls():
    pats = (
        r"DELETE[^\n]*/im/v1/messages",
        r"(?i)recall",
        r"chatMembers_(create|delete)",
        r"(POST|DELETE|PATCH|PUT)[^\n]*/chats/[^\n]*/members",
        r"/chats/[^\n]*/members[^\n]*(POST|DELETE)",
    )
    bad = [re.compile(p) for p in pats]
    hits = [
        f"{p.name}:{i}"
        for p in ROOT.rglob("*.py")
        if not ({"tests", "integrated_tests", ".venv"} & set(p.relative_to(ROOT).parts))
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if any(b.search(l) for b in (bad[:2] if p == SRC / "org" / "writer.py" else bad))
    ]
    assert hits == []


def test_feishu_client_read_only():
    for a in (
        ("api", "POST", "/open-apis/im/v1/messages"),
        ("api", "DELETE", "/x"),
        ("im", "+message-send"),
        ("api", "POST", "/open-apis/im/v1/chats/oc/members"),
    ):
        with pytest.raises(larkcli.WriteBlocked):
            larkcli.guard(a)
    larkcli.guard(("api", "GET", "/open-apis/im/v1/messages"))
    larkcli.guard(("im", "+chat-list", "--as", "user"))
    src = (SRC / "intent" / "names.py").read_text(encoding="utf-8")
    assert "core import lark" in src and "subprocess" not in src and "mobile" not in src and "email" not in src
    bots = [q.name for q in SRC.rglob("*.py") for _ in re.findall(r'"--as",\s*"bot"', q.read_text(encoding="utf-8"))]
    assert sorted(bots) == ["names.py", "read.py", "read.py", "read.py"]
    bad = re.compile(
        r"(?i)\"(POST|DELETE|PATCH|PUT)\"|recall|chatMembers|chatManagers|message_create|\+message-send|/members[^\n]*(POST|DELETE)|/managers|batch_delete"
    )
    ro_files = [q for q in SRC.rglob("*.py") if "outputs" not in q.parts and "org" not in q.relative_to(SRC).parts]
    assert SPLIT_FILES <= {q.relative_to(SRC).as_posix() for q in ro_files}
    assert [
        f"{p.name}:{i}"
        for p in ro_files
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if bad.search(l)
    ] == []


def test_no_sensitive_values_in_repo():
    key, hf = settings.sensitive_hmac_key(), settings.sensitive_hashes_path()
    if not key or not hf.exists():
        pytest.skip("未配置本地 HMAC 密钥或 sensitive_hashes.txt，跳过敏感词守卫")
    hs = {l.strip() for l in hf.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    assert len(hs) >= 4
    hits = [
        f"{p.relative_to(ROOT)}:{mac[:12]}"
        for p in tracked()
        if p != hf and p.suffix not in (".db", ".gz", ".lock", ".png", ".jpg")
        for x in _tokens(p.read_text(encoding="utf-8", errors="ignore"))
        for mac in [hmac.new(key, x.encode("utf-8"), hashlib.sha256).hexdigest()]
        if mac in hs
    ]
    assert hits == []


def test_sensitive_hmac_skip_and_detect(tmp_path, monkeypatch):
    monkeypatch.delenv(settings.SENSITIVE_HMAC_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception):
        test_no_sensitive_values_in_repo()
    monkeypatch.setenv(settings.SENSITIVE_HMAC_ENV, "test-hmac-secret-key")
    monkeypatch.setenv(settings.SENSITIVE_HASHES_ENV, str(tmp_path / "missing.txt"))
    with pytest.raises(pytest.skip.Exception):
        test_no_sensitive_values_in_repo()
    hf = tmp_path / "sensitive_hashes.txt"
    hf.write_text(
        "\n".join(
            hmac.new(b"test-hmac-secret-key", w.encode("utf-8"), hashlib.sha256).hexdigest()
            for w in ("虚构敏感词甲", "虚构敏感词乙", "虚构敏感词丙", "pyproject")
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(settings.SENSITIVE_HASHES_ENV, str(hf))
    with pytest.raises(AssertionError):
        test_no_sensitive_values_in_repo()


def test_files_under_300_lines_and_code_guards():
    assert [
        f"{p.relative_to(ROOT)}:{n}"
        for p in tracked()
        if p.suffix == ".py"
        for n in [len(p.read_text(encoding="utf-8").splitlines())]
        if n >= 300
    ] == []
    assert [
        str(p.relative_to(ROOT))
        for p in [*SRC.rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]
        if p.name != "settings.py"
        and ("os.environ" in p.read_text(encoding="utf-8") or "getenv(" in p.read_text(encoding="utf-8"))
    ] == []
    assert [
        str(p.relative_to(ROOT))
        for p in tracked()
        if p.suffix == ".py"
        and "except ImportError" in p.read_text(encoding="utf-8")
        and p.name != "test_repo_guards.py"
    ] == []
    assert [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if p.name != "__init__.py" and not (ROOT / "tests" / p.relative_to(SRC).parent / f"test_{p.name}").exists()
    ] == []


def test_packaging_and_entry_points():
    assert (
        not (ROOT / "run.py").exists()
        and not (ROOT / "setup.py").exists()
        and not (ROOT / "src" / "__init__.py").exists()
    )
    pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        'feishu-workflows = "quanttide_academy.cli:entry"' in pp
        and 'where = ["src"]' in pp
        and '"*.db"' in pp
        and '"config.yaml"' in pp
        and '"data/*"' in pp
    )
    assert all(
        "run.py" not in p.read_text(encoding="utf-8")
        for p in [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            *(ROOT / "manifests").rglob("*.*"),
            *(ROOT / "integrated_tests").rglob("*.md"),
        ]
    )
    assert {"data/", "config.yaml", "*.db", "local/"} <= set(
        (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    )


def test_org_writer_not_imported_by_intent_and_no_silent_except():
    assert [
        str(p.relative_to(ROOT))
        for p in (SRC / "intent").rglob("*.py")
        if "quanttide_academy.org" in p.read_text(encoding="utf-8") or "lark_writer" in p.read_text(encoding="utf-8")
    ] == []
    bad = [
        f"{p.name}:{i}"
        for p in SRC.rglob("*.py")
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"except\s*(Exception\b[^:]*)?:\s*pass\b", l.strip())
        or l.strip() == "except:"
        or (re.match(r"except\b.*:\s*pass\b", l.strip()) and "仅清理" not in l)
    ]
    assert bad == []


def test_dm_reads_only_in_dm_module_and_gated():
    pat = re.compile(r"dm_chat|p2p")
    scanned = [p for p in SRC.rglob("*.py") if p.name != "dm.py" and "outputs" not in p.parts]
    assert SPLIT_FILES <= {p.relative_to(SRC).as_posix() for p in scanned}
    assert [
        f"{p.relative_to(ROOT)}:{i}"
        for p in scanned
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pat.search(l) and "larkcli" in l
    ] == []
    poll, src = (
        (SRC / "watch" / "poll.py").read_text(encoding="utf-8"),
        (SRC / "watch" / "dm.py").read_text(encoding="utf-8"),
    )
    assert (
        "dm.fetch(" in poll
        and "if t.dm]" in poll
        and "if not t.dm or not t.dm_chat" in src
        and src.index("verify(cfg", src.index("def fetch")) > 0
        and '"POST"' not in src
    )


def test_feishu_writes_only_in_org_writer_and_only_via_approved_plan():
    feishu_write = re.compile(r"\"(POST|DELETE|PATCH|PUT)\",f?\"/open-apis|add_managers|delete_managers|subprocess")
    all_src = {p.relative_to(SRC).as_posix(): p for p in SRC.rglob("*.py")}
    assert SPLIT_FILES <= set(all_src)
    hits = [
        rel
        for rel, p in all_src.items()
        if rel not in ("org/writer.py", "core/lark.py")
        for t in [p.read_text(encoding="utf-8")]
        if feishu_write.search(t)
        or (
            re.search(r"org(\.| import )writer|from quanttide_academy\.org\.writer|import writer", t)
            and rel != "org/apply.py"
        )
    ]
    assert hits == [], hits
    w, plan = (
        (SRC / "org" / "writer.py").read_text(encoding="utf-8"),
        (SRC / "org" / "plan.py").read_text(encoding="utf-8"),
    )
    assert (
        "def execute(" in w
        and w.index("计划未批准") < w.rindex("run(req)")
        and w.index("未获批准") < w.rindex("run(req)")
        and "WriterDisabled" in w
    )
    assert "writer" not in plan and "core.lark" not in plan


def test_no_message_sending_and_coverage_and_commit_guards():
    send = re.compile(
        r"(?i)\"(POST|PUT|PATCH)\"[^\n]*/im/v1/messages|/im/v1/messages/[^\n\"]*/(reply|forward|urgent)|\+(send|reply|message-send|messages-send|messages-reply)\b|message_create|messages?_reply|send_message|batch_message"
    )
    assert [
        f"{p.relative_to(ROOT)}:{i}"
        for p in [*SRC.rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]
        for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if send.search(l)
    ] == []
    assert not any(
        "/messages" in writer.request({"kind": k, "chat_id": "oc", "person": "ou", "name": "n"})[1]
        for k in ("add_member", "remove_member", "set_admin", "unset_admin", "rename", "transfer", "create", "disband")
    )
    pp, cs = (
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        (ROOT / "scripts" / "commit.sh").read_text(encoding="utf-8"),
    )
    assert (
        'source = ["src/quanttide_academy"]' in pp
        and "fail_under = 80" in pp
        and "omit" not in pp
        and "git status --short" in cs
        and "exit 1" in cs
    )
    assert [
        str(p.relative_to(ROOT)) for p in SRC.rglob("*.py") if "pragma: no cover" in p.read_text(encoding="utf-8")
    ] == []
