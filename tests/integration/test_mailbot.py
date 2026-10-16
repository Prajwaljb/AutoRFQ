"""mailbot.py with Gmail mocked: replies, holds, failures and the poison-email fix."""
import email
import email.policy
import json
import subprocess

import pytest

from conftest import EMAILS, run_build

import mailbot


class FakeImap:
    def __init__(self, messages):
        self.messages = messages  # uid -> raw bytes
        self.seen = []

    def __call__(self, host):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        pass

    def select(self, box):
        pass

    def uid(self, command, *args):
        if command == "SEARCH":
            self.search = args
            return "OK", [b" ".join(self.messages)]
        if command == "FETCH":
            return "OK", [(b"", self.messages[args[0]])]
        if command == "STORE":
            self.seen.append(args[0])
            return "OK", [b""]
        raise AssertionError(command)


class FakeSmtp:
    sent = []
    fail = False

    def __init__(self, host, port):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if FakeSmtp.fail:
            raise OSError("smtp down")
        FakeSmtp.sent.append(msg)


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setattr(mailbot, "OUT", tmp_path)
    monkeypatch.setattr(mailbot, "BOT_EMAIL", "bot@example.com")
    monkeypatch.setattr(mailbot, "BOT_PASSWORD", "x")
    monkeypatch.setattr(mailbot, "REVIEW_NOTIFY_EMAIL", "")
    monkeypatch.setattr(mailbot.smtplib, "SMTP_SSL", FakeSmtp)
    monkeypatch.setattr(mailbot.time, "strftime", lambda fmt, *a: "20261016-120000" if "%H" in fmt
                        else "16-Oct-2026")
    FakeSmtp.sent, FakeSmtp.fail = [], False

    def run(messages):
        imap = FakeImap(messages)
        monkeypatch.setattr(mailbot.imaplib, "IMAP4_SSL", imap)
        mailbot.check_inbox(["--offline"])
        return imap
    return run


def offline_base(tmp_path):
    def base(eml, extra_args):
        assert run_build(eml, tmp_path, *extra_args).returncode == 0
        return tmp_path / eml.stem
    return base


def test_ready_rfq_is_answered_in_thread(bot, tmp_path, monkeypatch):
    monkeypatch.setattr(mailbot, "run_base", offline_base(tmp_path))
    imap = bot({b"1": (EMAILS / "email-1-ids-in-body.eml").read_bytes()})
    assert imap.seen == [b"1"]
    [reply] = FakeSmtp.sent
    assert reply["In-Reply-To"] == "<rfq-sample-1@sourcing.example.com>"
    assert [p.get_filename() for p in reply.iter_attachments()] == ["RFQ.xlsx"]
    run = json.loads((tmp_path / "rfq-20261016-120000-1" / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "sent"


def test_failed_build_sends_follow_up_and_moves_on(bot, tmp_path, monkeypatch):
    calls = []

    def flaky(eml, extra_args):
        calls.append(eml)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, "build.py")
        return offline_base(tmp_path)(eml, extra_args)
    monkeypatch.setattr(mailbot, "run_base", flaky)
    raw = (EMAILS / "email-1-ids-in-body.eml").read_bytes()
    imap = bot({b"1": raw, b"2": raw})
    assert imap.seen == [b"1", b"2"]
    assert len(FakeSmtp.sent) == 2
    assert "a person from our team will follow up" in FakeSmtp.sent[0].get_body(("plain",)).get_content()
    assert [p.get_filename() for p in FakeSmtp.sent[1].iter_attachments()] == ["RFQ.xlsx"]


def test_needs_review_is_held(bot, tmp_path, monkeypatch):
    def held(eml, extra_args):
        folder = offline_base(tmp_path)(eml, extra_args)
        run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        run["status"] = "needs_review"
        (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
        return folder
    monkeypatch.setattr(mailbot, "run_base", held)
    imap = bot({b"7": (EMAILS / "email-4-messy-forward.eml").read_bytes()})
    assert imap.seen == [b"7"]
    assert FakeSmtp.sent == []


def test_smtp_failure_still_marks_read(bot, tmp_path, monkeypatch):
    monkeypatch.setattr(mailbot, "run_base", offline_base(tmp_path))
    FakeSmtp.fail = True
    imap = bot({b"3": (EMAILS / "email-1-ids-in-body.eml").read_bytes()})
    assert imap.seen == [b"3"]


def test_own_emails_are_skipped(bot, monkeypatch):
    monkeypatch.setattr(mailbot, "run_base", lambda *a: pytest.fail("should not build"))
    raw = (EMAILS / "email-1-ids-in-body.eml").read_bytes().replace(
        b"priya.nair@sourcing.example.com", b"bot@example.com")
    imap = bot({b"4": raw})
    assert imap.seen == [b"4"] and FakeSmtp.sent == []


def test_search_matches_rfq_in_subject_or_text(bot, monkeypatch):
    """Real RFQs often have a blank or "Fwd:" subject and say "prepare the RFQ" in the text."""
    imap = bot({})
    assert imap.search[1:5] == ("UNSEEN", "SINCE", "16-Oct-2026", "OR")
    assert imap.search[5:] == ("SUBJECT", '"RFQ"', "BODY", '"RFQ"')
