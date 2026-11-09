import pytest

from name_audit.keys import read_key


def test_reads_only_the_named_line(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OTHER_SECRET=nope\nOPENAI_API_KEY=sk-test-123\nexport GEMINI_API_KEY='g-456'\n")
    assert read_key("openai", env) == "sk-test-123"
    assert read_key("gemini", env) == "g-456"


def test_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert read_key("openai", None) == "from-env"


def test_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY_OLD=x\n")
    with pytest.raises(SystemExit):
        read_key("openai", env)
