import pytest
from unittest.mock import patch, MagicMock, ANY
from monitor.email_sender import EmailSender


@pytest.fixture
def sender():
    return EmailSender("sender@gmail.com", "test_password")


def test_connects_to_gmail_ssl(sender):
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = MagicMock()
        sender.send("recv@gmail.com", "Subject", "Body")
        mock_smtp.assert_called_once_with("smtp.gmail.com", 465, context=ANY)


def test_logs_in_with_sender_credentials(sender):
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        sender.send("recv@gmail.com", "Subject", "Body")
        mock_server.login.assert_called_once_with("sender@gmail.com", "test_password")


def test_message_has_correct_subject(sender):
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        sender.send("recv@gmail.com", "Test Subject", "Body")
        msg = mock_server.send_message.call_args[0][0]
        assert msg["Subject"] == "Test Subject"


def test_message_has_correct_from_and_to(sender):
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        sender.send("recv@gmail.com", "Subject", "Body")
        msg = mock_server.send_message.call_args[0][0]
        assert msg["From"] == "sender@gmail.com"
        assert msg["To"] == "recv@gmail.com"


def test_message_body_is_included(sender):
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        sender.send("recv@gmail.com", "Subject", "Hello body text")
        msg = mock_server.send_message.call_args[0][0]
        assert msg.get_payload() == "Hello body text"
