"""Tests for the check_queue Lambda handler."""

from unittest.mock import MagicMock, patch

from app.submarine.check_queue import handler


class TestCheckQueueHandler:
    """Tests for the SQS queue depth check Lambda."""

    @patch("app.submarine.check_queue.boto3")
    def test_empty_queue_returns_true(self, mock_boto3):
        """Empty queue returns is_empty=True."""
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "0",
                "ApproximateNumberOfMessagesNotVisible": "0",
            }
        }

        result = handler({"queue_url": "https://sqs.example.com/test.fifo"}, None)

        assert result["is_empty"] is True
        assert result["visible"] == 0
        assert result["in_flight"] == 0

    @patch("app.submarine.check_queue.boto3")
    def test_non_empty_queue_returns_false(self, mock_boto3):
        """Queue with visible messages returns is_empty=False."""
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "42",
                "ApproximateNumberOfMessagesNotVisible": "3",
            }
        }

        result = handler({"queue_url": "https://sqs.example.com/test.fifo"}, None)

        assert result["is_empty"] is False
        assert result["visible"] == 42
        assert result["in_flight"] == 3

    @patch("app.submarine.check_queue.boto3")
    def test_in_flight_only_returns_false(self, mock_boto3):
        """Queue with only in-flight messages returns is_empty=False."""
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "0",
                "ApproximateNumberOfMessagesNotVisible": "5",
            }
        }

        result = handler({"queue_url": "https://sqs.example.com/test.fifo"}, None)

        assert result["is_empty"] is False

    def test_no_url_returns_empty_with_error(self):
        """Missing queue URL returns is_empty=True with error."""
        result = handler({}, None)

        assert result["is_empty"] is True
        assert "error" in result

    @patch.dict("os.environ", {"SUBMARINE_QUEUE_URL": "https://sqs.example.com/sub.fifo"})
    @patch("app.submarine.check_queue.boto3")
    def test_uses_env_var_fallback(self, mock_boto3):
        """Falls back to SUBMARINE_QUEUE_URL env var when not in event."""
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs
        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "0",
                "ApproximateNumberOfMessagesNotVisible": "0",
            }
        }

        result = handler({}, None)

        assert result["is_empty"] is True
        mock_sqs.get_queue_attributes.assert_called_once()
        call_kwargs = mock_sqs.get_queue_attributes.call_args
        assert call_kwargs.kwargs["QueueUrl"] == "https://sqs.example.com/sub.fifo"
