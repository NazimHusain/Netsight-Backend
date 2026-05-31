# utils/excel_sanitizer.py
import re
from typing import Any
import unicodedata
import smtplib
import logging

# from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.conf import settings
from .models import ConfigExecutionRequest
from django.shortcuts import render

import smtplib,re,requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from email.mime.base import MIMEBase

import html


signer = TimestampSigner()

# Excel illegal control characters
EXCEL_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0E-\x1F]")

# Vertical tab & form feed
VT_FF_RE = re.compile(r"[\x0B\x0C]")

# ANSI escape sequences (CLI colors, cursor movement)
ANSI_ESCAPE_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
)



def sanitize_for_excel(value: Any) -> str:
    """
    Make router output safe for Excel (.xlsx)
    WITHOUT losing meaningful data.
    """
    if value is None:
        return ""

    text = str(value)

    # ✅ Convert HTML entities
    text = html.unescape(text)

    # ✅ Remove ANSI escape sequences
    text = ANSI_ESCAPE_RE.sub("", text)

    # ✅ Remove NULL chars (critical)
    text = text.replace("\x00", "")

    # ✅ Convert VT / FF to newline
    text = VT_FF_RE.sub("\n", text)

    # ✅ Remove Excel-breaking control chars
    text = EXCEL_CONTROL_CHARS_RE.sub(" ", text)

    # ✅ Normalize spaces (preserve newlines)
    text = re.sub(r"[ \t]+", " ", text)

    text = text.strip()

    # ✅ Excel FORMULA PROTECTION (CRITICAL FIX)
    if text.startswith(("=", "+", "-", "@")):
        text = "'" + text

    # ✅ Excel max cell limit
    MAX_LEN = 32000
    text = text[:MAX_LEN]

    return text




def sanitize_command(cmd):
    # Normalize unicode (fix Excel weird chars)
    cmd = unicodedata.normalize("NFKC", cmd)
    # Replace non-breaking space with normal space
    cmd = cmd.replace("\u00a0", " ")
    # Collapse multiple spaces inside the command
    cmd = re.sub(r"\s+", " ", cmd)
    # Strip leading/trailing whitespace
    return cmd.strip()



def send_email(html_content, sender, receivers, title, Cc):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = title
    msg['From'] = sender
    msg['To'] = ', '.join(receivers)
 
    if Cc:
        msg['Cc'] = ','.join(Cc)
 
    msg.attach(MIMEText(html_content, 'html'))
 
    smtp = smtplib.SMTP('10.56.131.8')
    try:
        recipients = receivers + (Cc if Cc else [])
        smtp.sendmail(sender, recipients, msg.as_string())
    finally:
        smtp.quit()


# def send_mail(sender, receiver, message):
#     logging.info("Inside send mail")
#     sender = sender
#     receivers = [receiver]
#     message = message
#     smtpObj = smtplib.SMTP("10.56.131.8")
#     smtpObj.sendmail(sender, receivers, message)
#     logging.info("SMTP send mail")
#     print(f"Successfully sent email  to {receiver}")





def send_config_request_email(request_id):
    req = ConfigExecutionRequest.objects.get(id=request_id)
    token = signer.sign(request_id)
    approval_link = f"http://10.227.244.108:9033/approve/{token}/"

    html_content = f"""
                        <div style="font-family: Arial, sans-serif; line-height: 1.6;">

                        <h2 style="color:#2c3e50;">🔐 Config Access Request</h2>

                        <p><b>User:</b> {req.user.username}</p>
                        <p><b>Email:</b> {req.user.email}</p>
                        <p><b>Reason:</b> {req.reason}</p>
                        <p><b>Requested Duration:</b> {req.duration_hours} hours</p>

                        <p><b>Action:</b></p>

                        <a href="{approval_link}" 
                            style="display:inline-block;padding:10px 18px;margin-top:5px;
                            background-color:#28a745;color:white;text-decoration:none;
                            border-radius:6px;font-weight:bold;">
                            Approve / Reject
                        </a>

                        <p style="margin-top:20px;font-size:12px;color:gray;">
                            If button doesn't work, copy below link:
                        </p>

                        <p style="font-size:12px;color:#555;">
                            {approval_link}
                        </p>

                        </div>
                        """
    send_email(
    html_content=html_content,
    sender="mop_tool_automation@airtel.com",
    receivers=[" Ritesh1.Srivastava@airtel.com","pankaj.chaudhary@airtel.com"],
    title="Config Access Request",
    Cc=["nazim.husain@airtel.com","Deepak.Miglani@airtel.com"]
)




