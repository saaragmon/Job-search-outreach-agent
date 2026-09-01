import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=True)
_course_env = _HERE.parents[2] / ".env" if len(_HERE.parents) >= 3 else None
if _course_env is not None and _course_env.exists():
    load_dotenv(_course_env, override=False)
load_dotenv(override=True)

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


def _norm(addr: str) -> str:
    return (addr or "").strip().lower()


def assert_can_send(to_addr: str, allow_external: bool) -> str | None:
    """Return an error string, or None if sending is allowed."""
    to_addr = (to_addr or "").strip()
    if not to_addr:
        return "No contact email."
    mine = _norm(EMAIL_ADDRESS)
    if mine and _norm(to_addr) == mine:
        return None
    if allow_external:
        return None
    if not mine:
        return "Set EMAIL_ADDRESS in .env, or tick “send to this contact on purpose”."
    return (
        f"Portfolio mode: only your inbox ({EMAIL_ADDRESS}) is allowed. "
        "Tick “I typed this address on purpose” to email someone else."
    )


def send_email(to_addr: str, subject: str, body: str) -> str:
    to_addr = (to_addr or "").strip()
    if not to_addr:
        return "No contact email — message saved only."
    if not (EMAIL_ADDRESS and EMAIL_SMTP_SERVER and EMAIL_APP_PASSWORD):
        print(f"[dry-run email to {to_addr}]\n{subject}\n\n{body}")
        return "Email env not fully set — printed to terminal (dry run)."

    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(EMAIL_SMTP_SERVER, 587, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD.replace(" ", ""))
        server.send_message(msg)
    return f"Sent to {to_addr}"
