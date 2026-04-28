"""Gmail alert sender used to notify when the pump runs over the alarm threshold."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailSender:
    """Sends alert emails via Gmail using an App Password."""

    def __init__(self, sender_email: str, gmail_app_password: str) -> None:
        """Store sender credentials for use when sending emails.

        Args:
            sender_email: The Gmail address emails are sent from.
            gmail_app_password: Gmail App Password (not the account password).
        """
        self.sender_email = sender_email
        self.password = gmail_app_password

    def send(self, receiver_email: str, subject: str, text: str,
             html: str | None = None) -> None:
        """Send an email via Gmail SSL, optionally with an HTML alternative.

        When html is provided the message is sent as multipart/alternative so
        email clients that support HTML render the rich version while others
        fall back to the plain-text body.

        Args:
            receiver_email: Destination email address.
            subject: Email subject line.
            text: Plain-text body (always included).
            html: Optional HTML body for rich-text clients.
        """
        if html:
            msg: MIMEMultipart | MIMEText = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = receiver_email
            msg.attach(MIMEText(text, 'plain'))
            msg.attach(MIMEText(html, 'html'))
        else:
            msg = MIMEText(text)
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = receiver_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(self.sender_email, self.password)
            server.send_message(msg)
