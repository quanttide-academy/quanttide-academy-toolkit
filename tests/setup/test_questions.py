from quanttide_academy.setup.questions import QUESTIONS, SECRET_RE
from tests.helpers import *


def test_questions_structure_and_secret_re():
    assert all({"key", "question", "explanation", "options", "default"} <= set(x) for x in QUESTIONS)
    assert not any("follow_label" in json.dumps(x, ensure_ascii=False) for x in QUESTIONS)
    assert any(x["key"] == "display_name" and "称呼" in x["question"] for x in QUESTIONS)
    assert any(x["key"] == "include_chats" and x["default"] == [] for x in QUESTIONS)
    assert SECRET_RE.search("0123456789abcdef0123456789abcdef0123")
    assert "__import__" not in (ROOT / "src" / "quanttide_academy" / "setup" / "questions.py").read_text(
        encoding="utf-8"
    )
