"""Reads an .eml file: header fields, text parts (HTML stripped), attached emails and attachments."""
import base64
import email
import email.policy
import quopri
from dataclasses import dataclass, field
from email.utils import parseaddr
from html.parser import HTMLParser


@dataclass
class EmailData:
    sender: str = ""
    sender_name: str = ""
    subject: str = ""
    message_id: str = ""
    references: str = ""
    date: str = ""
    texts: list = field(default_factory=list)        # (label, text) in MIME order
    attachments: list = field(default_factory=list)  # (filename, bytes)
    problems: list = field(default_factory=list)     # notes about parts that could not be read
    raw: object = None                               # the parsed message, for building the reply


class _TextFromHtml(HTMLParser):
    BLOCK = {"br", "p", "div", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6",
             "blockquote", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html):
    parser = _TextFromHtml()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    return "".join(parser.parts)


def _decode_text(part):
    """The text of a part, even with a broken charset or transfer encoding. None if unreadable."""
    try:
        return part.get_content()
    except Exception:
        pass
    payload = part.get_payload(decode=True)
    if payload is None:
        return None
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:  # unknown charset name
        return payload.decode("utf-8", errors="replace")


def _is_attachment(part):
    return part.get_content_disposition() == "attachment" or (
        part.get_filename() is not None and part.get_content_maintype() != "text")


def _walk(part, data, label):
    ctype = part.get_content_type()
    cte = str(part.get("Content-Transfer-Encoding", "")).strip().lower()
    if ctype == "message/rfc822" and cte in ("base64", "quoted-printable"):
        # Not allowed by the RFC, but some clients send attached emails encoded: decode, then parse.
        inner = part.get_payload()
        inner = inner[0] if isinstance(inner, list) and inner else inner
        encoded = inner.get_payload() if hasattr(inner, "get_payload") else str(inner)
        try:
            raw = (base64.b64decode(encoded) if cte == "base64"
                   else quopri.decodestring(encoded.encode("latin-1")))
            _walk(email.message_from_bytes(raw, policy=email.policy.default), data,
                  f"{label} > attached email")
        except Exception:
            data.problems.append("An attached email could not be decoded.")
        return
    if part.is_multipart():
        children = part.get_payload()
        if not isinstance(children, list):
            children = [children]
        if ctype == "multipart/alternative":  # the same text twice: prefer the plain version
            plain = [c for c in children if c.get_content_type() == "text/plain"]
            html = [c for c in children if c.get_content_type() == "text/html"]
            others = [c for c in children if c.get_content_type() not in ("text/plain", "text/html")]
            children = (plain[:1] or html[:1]) + others
        for child in children:
            sub_label = f"{label} > attached email" if ctype == "message/rfc822" else label
            _walk(child, data, sub_label)
        return
    if ctype in ("text/plain", "text/html") and not _is_attachment(part):
        text = _decode_text(part)
        if text is None:
            data.problems.append(f"A {ctype} part of the email could not be decoded.")
            return
        data.texts.append((label, html_to_text(text) if ctype == "text/html" else text))
        return
    if part.get_filename() or part.get_content_disposition() == "attachment" or ctype == "message/rfc822":
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        name = part.get_filename() or "attachment"
        if ctype == "message/rfc822" or name.lower().endswith(".eml"):  # an email sent as a file
            if payload:
                inner = email.message_from_bytes(payload, policy=email.policy.default)
                _walk(inner, data, f"{label} > attached email")
            return
        if ctype == "text/plain" and name.lower().endswith(".txt"):
            data.texts.append((f"{label} > {name}", _decode_text(part) or ""))
        else:
            data.attachments.append((name, payload))


def read_email(path):
    """Parses an .eml file. Raises OSError only if the file can't be read at all."""
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    data = EmailData(raw=msg)
    try:
        reply_to = msg.get("Reply-To") or msg.get("From", "")
        name, addr = parseaddr(str(reply_to))
        data.sender, data.sender_name = addr, name
        data.subject = str(msg.get("Subject", "") or "")
        data.message_id = str(msg.get("Message-ID", "") or "")
        data.references = str(msg.get("References", "") or "")
        data.date = str(msg.get("Date", "") or "")
    except Exception:  # a broken header must not stop the run
        data.problems.append("Some email headers could not be read.")
    try:
        _walk(msg, data, "email")
    except Exception as e:
        data.problems.append(f"Part of the email could not be read ({type(e).__name__}).")
    return data
