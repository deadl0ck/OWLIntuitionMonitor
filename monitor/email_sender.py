"""Gmail alert sender used to notify when the pump runs over the alarm threshold."""

import smtplib
import ssl
from email.mime.text import MIMEText


class EmailSender:
    """Sends plain-text alert emails via Gmail using an App Password."""

    def __init__(self, sender_email: str, gmail_app_password: str) -> None:
        """Store sender credentials for use when sending emails.

        Args:
            sender_email: The Gmail address emails are sent from.
            gmail_app_password: Gmail App Password (not the account password).
        """
        self.sender_email = sender_email
        self.password = gmail_app_password

    def send(self, receiver_email: str, subject: str, text: str) -> None:
        """Send a plain-text email via Gmail SSL.

        Args:
            receiver_email: Destination email address.
            subject: Email subject line.
            text: Plain-text body of the email.
        """
        msg = MIMEText(text)
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = receiver_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(self.sender_email, self.password)
            server.send_message(msg)
