import os
import re
import smtplib
import time
import traceback
import uuid
from email.message import EmailMessage

import database


EMAIL_PATTERN = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match((email or "").strip()))


def _debug_log(message: str, fallback: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(fallback)


def send_prediction_report_email(
    to_email: str,
    prediction_id: str,
    pdf_bytes: bytes,
    smtp_user: str | None = None,
    smtp_app_password: str | None = None,
) -> None:
    _debug_log("🚀 send_prediction_report_email() CALLED", "send_prediction_report_email() CALLED")
    clean_to_email = (to_email or "").strip()
    if not is_valid_email(clean_to_email):
        raise ValueError(f"Invalid recipient email format: {clean_to_email}")

    sender_email = (smtp_user or os.getenv("SMTP_GMAIL_USER", "")).strip()
    app_password = (smtp_app_password or os.getenv("SMTP_GMAIL_APP_PASSWORD", "")).replace(" ", "").strip()

    if not sender_email:
        _debug_log("❌ Missing environment variable: SMTP_GMAIL_USER", "Missing environment variable: SMTP_GMAIL_USER")
        raise ValueError("Missing required environment variable: SMTP_GMAIL_USER")
    if not app_password:
        _debug_log(
            "❌ Missing environment variable: SMTP_GMAIL_APP_PASSWORD",
            "Missing environment variable: SMTP_GMAIL_APP_PASSWORD",
        )
        raise ValueError("Missing required environment variable: SMTP_GMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["Subject"] = f"🚗 Car Price Prediction Report | ID: {prediction_id}"
    msg["From"] = sender_email
    msg["To"] = clean_to_email
    msg["Reply-To"] = sender_email

    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF"):
        raise ValueError("Invalid PDF attachment generated. Please regenerate report and try again.")

    body = f"""Hello,

Your Car Price Prediction Report has been successfully generated.

Prediction ID: {prediction_id}

The attached report includes:
- vehicle details
- predicted price
- recommendation analysis
- negotiation range

If not found in Inbox, kindly check Spam or Promotions.

Regards,
Car Price Prediction System
"""
    msg.set_content(body)
    msg.add_alternative(
        f"""
        <html>
            <body>
                <h2>🚗 Car Price Prediction Report</h2>
                <p>Your report has been generated successfully.</p>
                <p><b>Prediction ID:</b> {prediction_id}</p>
                <p>The attached PDF contains:</p>
                <ul>
                    <li>Vehicle details</li>
                    <li>Predicted market value</li>
                    <li>Recommendation analysis</li>
                    <li>Negotiation range</li>
                </ul>
                <p>Please find the attached report.</p>
                <p>If not found in Inbox, kindly check Spam or Promotions.</p>
                <p>Regards,<br/>Car Price Prediction System</p>
            </body>
        </html>
        """,
        subtype="html",
    )
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"Car_Price_Report_{prediction_id}.pdf",
    )

    email_id = str(uuid.uuid4())[:8]
    try:
        _debug_log("🔌 Connecting...", "Connecting...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.set_debuglevel(1)
            _debug_log("🔑 Logging in...", "Logging in...")
            smtp.login(sender_email, app_password)
            _debug_log("📤 Sending...", "Sending...")
            time.sleep(1)
            smtp.send_message(msg)
        _debug_log("✅ EMAIL SENT Successfully !!", "EMAIL SENT Successfully !!")
        database.save_email_history(
            email_id=email_id,
            prediction_id=prediction_id,
            recipient_email=clean_to_email,
            status="SUCCESS",
            delivery_status="SENT",
        )
        _debug_log("🤝 Email history saved to the database", "Email history saved to the database")
    except Exception as exc:
        _debug_log("❌ EMAIL FAILED", "EMAIL FAILED")
        print(exc)
        traceback.print_exc()
        try:
            database.save_email_history(
                email_id=email_id,
                prediction_id=prediction_id,
                recipient_email=clean_to_email,
                status="FAILED",
                delivery_status="FAILED",
            )
            _debug_log("🤝 Email history saved to the database", "Email history saved to the database")
        except Exception as save_exc:
            _debug_log("❌ Failed to save email history", "Failed to save email history")
            print(save_exc)
        raise
