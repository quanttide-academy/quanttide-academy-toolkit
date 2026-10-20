import contextlib
import io

from quanttide_academy import setup as S
from tests.helpers import *


def test_setup_reexports_and_cli(tmp_path):
    for name in ("QUESTIONS", "SECRET_RE", "apply", "ask", "main", "migrate", "prefill"):
        assert hasattr(S, name), name
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        S.main(["questions", "--json"])
    qs = json.loads(buf.getvalue())["questions"]
    assert len(qs) == len(S.QUESTIONS)
    cp = tmp_path / "config.yaml"
    ans = tmp_path / "a.json"
    ans.write_text(
        json.dumps({"self_open_id": "ou_me", "todo_provider": "markdown", "priority_names": PN}, ensure_ascii=False),
        encoding="utf-8",
    )
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        S.main(["apply", str(ans), "--config", str(cp)])
    assert json.loads(buf2.getvalue())["status"] == "ok" and cp.exists()
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        S.main(["migrate", "--config", str(cp), "--dry-run"])
    assert json.loads(buf3.getvalue())["status"] == "ok"
    lf = tmp_path / "chats.json"
    lf.write_text(json.dumps([{"chat_id": "oc_1", "name": "群1"}]), encoding="utf-8")
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        S.main(["prefill", str(lf), "--config", str(cp)])
    assert json.loads(buf4.getvalue())["include_chats"] == 1
