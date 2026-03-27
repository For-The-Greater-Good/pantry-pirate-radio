"""Tests for submarine batch scanner."""

from unittest.mock import MagicMock, patch

import pytest


class TestScanAndEnqueue:
    """Tests for the scan_and_enqueue function."""

    @patch("app.submarine.scanner.SubmarineDispatcher")
    @patch("app.submarine.scanner.sessionmaker")
    @patch("app.submarine.scanner.create_engine")
    def test_scan_with_no_candidates(
        self, mock_engine, mock_session_factory, mock_disp
    ):
        """Scan returns zero enqueued when no candidates found."""
        from app.submarine.scanner import scan_and_enqueue

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.fetchall.return_value = []
        mock_session_factory.return_value = MagicMock(return_value=mock_session)

        summary = scan_and_enqueue()

        assert summary["total_candidates"] == 0
        assert summary["enqueued"] == 0

    @patch("app.submarine.scanner.SubmarineDispatcher")
    @patch("app.submarine.scanner.sessionmaker")
    @patch("app.submarine.scanner.create_engine")
    def test_scan_enqueues_candidates(
        self, mock_engine, mock_session_factory, mock_disp
    ):
        """Scan enqueues jobs for locations with gaps."""
        from app.submarine.scanner import scan_and_enqueue

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.fetchall.return_value = [
            ("loc-1", "org-1"),
            ("loc-2", "org-2"),
        ]
        mock_session_factory.return_value = MagicMock(return_value=mock_session)

        mock_dispatcher_instance = MagicMock()
        mock_dispatcher_instance.check_and_enqueue.side_effect = ["sub-001", None]
        mock_disp.return_value = mock_dispatcher_instance

        summary = scan_and_enqueue()

        assert summary["total_candidates"] == 2
        assert summary["enqueued"] == 1
        assert summary["skipped"] == 1

    @patch("app.submarine.scanner.SubmarineDispatcher")
    @patch("app.submarine.scanner.sessionmaker")
    @patch("app.submarine.scanner.create_engine")
    def test_scan_uses_force_flag(self, mock_engine, mock_session_factory, mock_disp):
        """Scanner passes force=True to bypass SUBMARINE_ENABLED check."""
        from app.submarine.scanner import scan_and_enqueue

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.fetchall.return_value = [("loc-1", "org-1")]
        mock_session_factory.return_value = MagicMock(return_value=mock_session)

        mock_dispatcher_instance = MagicMock()
        mock_dispatcher_instance.check_and_enqueue.return_value = "sub-001"
        mock_disp.return_value = mock_dispatcher_instance

        scan_and_enqueue()

        # Verify force=True was passed
        call_kwargs = mock_dispatcher_instance.check_and_enqueue.call_args
        assert call_kwargs.kwargs.get("force") is True

    @patch("app.submarine.scanner.SubmarineDispatcher")
    @patch("app.submarine.scanner.sessionmaker")
    @patch("app.submarine.scanner.create_engine")
    def test_scan_handles_errors_gracefully(
        self, mock_engine, mock_session_factory, mock_disp
    ):
        """Scanner doesn't crash on individual location errors."""
        from app.submarine.scanner import scan_and_enqueue

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.fetchall.return_value = [
            ("loc-1", "org-1"),
            ("loc-2", "org-2"),
        ]
        mock_session_factory.return_value = MagicMock(return_value=mock_session)

        mock_dispatcher_instance = MagicMock()
        mock_dispatcher_instance.check_and_enqueue.side_effect = [
            Exception("DB error"),
            "sub-002",
        ]
        mock_disp.return_value = mock_dispatcher_instance

        summary = scan_and_enqueue()

        assert summary["errors"] == 1
        assert summary["enqueued"] == 1
