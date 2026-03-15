"""Send reimbursement emails with receipt attachments."""

import mimetypes
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import config
from receipt_processor import ReceiptData


def send_reimbursement_email(
    receipts: list[tuple[ReceiptData, str, int]],
) -> None:
    """Send reimbursement email with one or more receipts attached.

    Args:
        receipts: list of (receipt_data, image_path, seq_number) tuples.
    """
    msg = MIMEMultipart()
    msg["From"] = config.smtp_user
    recipients = [e.strip() for e in config.reimbursement_email.split(",")]
    msg["To"] = ", ".join(recipients)

    if len(receipts) == 1:
        data, _, seq = receipts[0]
        msg["Subject"] = f"Reimbursement #{seq}: {data.merchant} - {data.amount} {data.currency}"
    else:
        seq_numbers = [str(r[2]) for r in receipts]
        msg["Subject"] = f"Reimbursements #{', #'.join(seq_numbers)} ({len(receipts)} receipts)"

    # Build body with all receipt details
    body_parts = []
    for data, _, seq in receipts:
        body_parts.append(
            f"Reimbursement Request #{seq}\n"
            f"{'=' * 40}\n\n"
            f"Date:         {data.date}\n"
            f"Merchant:     {data.merchant}\n"
            f"Expense Type: {data.expense_type}\n"
            f"Amount:       {data.amount} {data.currency}\n"
            f"Description:  {data.description}\n"
        )
    body = "\n\n".join(body_parts) + f"\n\n{len(receipts)} receipt image(s) attached.\n"
    msg.attach(MIMEText(body, "plain"))

    # Attach all receipt images (skip missing files)
    for _, image_path, _ in receipts:
        if not image_path:
            continue
        path = Path(image_path)
        if not path.exists():
            continue
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        with open(path, "rb") as f:
            attachment = MIMEBase(maintype, subtype)
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header("Content-Disposition", "attachment", filename=path.name)
            msg.attach(attachment)

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.smtp_host not in ("localhost", "127.0.0.1"):
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)


def send_summary_email(
    subject: str,
    body: str,
    to: str | None = None,
    attachments: list[str] | None = None,
) -> None:
    """Send a custom summary/report email.

    Args:
        subject: Email subject line.
        body: Plain text email body.
        to: Recipient email(s), comma-separated. Defaults to REIMBURSEMENT_EMAIL.
        attachments: Optional list of file paths to attach.
    """
    msg = MIMEMultipart()
    msg["From"] = config.smtp_user
    recipients = [e.strip() for e in (to or config.reimbursement_email).split(",")]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    for file_path in attachments or []:
        path = Path(file_path)
        if not path.exists():
            continue
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        with open(path, "rb") as f:
            attachment = MIMEBase(maintype, subtype)
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header("Content-Disposition", "attachment", filename=path.name)
            msg.attach(attachment)

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.smtp_host not in ("localhost", "127.0.0.1"):
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)
