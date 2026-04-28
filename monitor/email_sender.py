import smtplib
import ssl
from email.mime.text import MIMEText


class EmailSender:
    def __init__(self, sender_email: str, gmail_app_password: str):
        self.sender_email = sender_email
        self.password = gmail_app_password

    def send(self, receiver_email: str, subject: str, text: str):
        msg = MIMEText(text)
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = receiver_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(self.sender_email, self.password)
            server.send_message(msg)
