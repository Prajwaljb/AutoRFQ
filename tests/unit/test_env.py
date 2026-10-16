import os

from rfq.infra import env


def test_parse_env_file():
    values = env.parse('# comment\nBOT_EMAIL=team@example.com\nBOT_PASSWORD="abcd efgh ijkl mnop"\n'
                       "export OPENAI_MODEL=gpt-4o-mini  # inline comment\nEMPTY=\nnot a line\n")
    assert values == {"BOT_EMAIL": "team@example.com", "BOT_PASSWORD": "abcd efgh ijkl mnop",
                      "OPENAI_MODEL": "gpt-4o-mini", "EMPTY": ""}


def test_load_never_overrides_and_skips_blanks(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("RFQ_TEST_A=from-file\nRFQ_TEST_B=from-file\nRFQ_TEST_C=\n", encoding="utf-8")
    monkeypatch.setenv("RFQ_TEST_A", "already-set")
    monkeypatch.delenv("RFQ_TEST_B", raising=False)
    monkeypatch.delenv("RFQ_TEST_C", raising=False)
    env.load(f)
    assert os.environ["RFQ_TEST_A"] == "already-set" and os.environ["RFQ_TEST_B"] == "from-file"
    assert "RFQ_TEST_C" not in os.environ
    monkeypatch.delenv("RFQ_TEST_B")


def test_example_file_lists_every_known_key():
    example = (env.ROOT / ".env.example").read_text(encoding="utf-8")
    for group in ("mail", "ai", "search"):
        for name in env.KNOWN[group]:
            assert name in example
