"""Tests for the --force-reextract path in queue_for_processing.

Issue #1 backfill needs to bypass the content-store dedup short-circuit
so previously-seen content is re-submitted to the LLM. These tests lock
both branches of the dedup decision.
"""

from unittest.mock import MagicMock, patch

from app.scraper.utils import ScraperUtils


def _make_utils() -> ScraperUtils:
    """Build a ScraperUtils without running __init__ (which needs Redis,
    files, etc.) — like test_job_id_format does."""
    utils = ScraperUtils.__new__(ScraperUtils)
    utils.scraper_id = "test-scraper"
    utils.system_prompt = "test prompt"
    utils.hsds_schema = {}
    utils.schema_converter = MagicMock()
    return utils


class TestForceReextract:
    def test_dedup_short_circuit_when_force_reextract_false(self) -> None:
        """Default behavior: content already in store with a job_id returns
        the existing id WITHOUT submitting a new LLM job."""
        existing_job_id = "existing-job-123"
        content_entry = MagicMock(hash="hash-abc", job_id=existing_job_id)
        content_store = MagicMock()
        content_store.store_content.return_value = content_entry
        mock_backend = MagicMock()

        with (
            patch(
                "app.content_store.config.get_content_store",
                return_value=content_store,
            ),
            patch(
                "app.llm.queue.backend.get_queue_backend",
                return_value=mock_backend,
            ),
        ):
            utils = _make_utils()
            result = utils.queue_for_processing("payload")

        assert result == existing_job_id
        # No new LLM job enqueued — that's the whole point of dedup.
        mock_backend.enqueue.assert_not_called()

    def test_force_reextract_bypasses_dedup_and_enqueues(self) -> None:
        """force_reextract=True must re-enqueue even when the content
        store already has this hash with a job_id. Without this, backfill
        runs (./bouy scraper --aws NAME --force-reextract) would silently
        no-op for every previously-seen record."""
        existing_job_id = "existing-job-123"
        content_entry = MagicMock(hash="hash-abc", job_id=existing_job_id)
        content_store = MagicMock()
        content_store.store_content.return_value = content_entry
        mock_backend = MagicMock()
        mock_backend.enqueue.return_value = "new-job-456"

        with (
            patch(
                "app.content_store.config.get_content_store",
                return_value=content_store,
            ),
            patch(
                "app.llm.queue.backend.get_queue_backend",
                return_value=mock_backend,
            ),
            patch("app.core.events.get_setting") as mock_setting,
            patch.dict("os.environ", {"QUEUE_BACKEND": "sqs"}),
        ):
            mock_setting.side_effect = lambda key, type_, *a, **_kw: {
                "llm_provider": "openai",
                "llm_model_name": "test",
                "llm_temperature": 0.7,
                "llm_max_tokens": 100,
            }.get(key)

            utils = _make_utils()
            result = utils.queue_for_processing("payload", force_reextract=True)

        # A new LLM job must have been submitted, not the cached id
        mock_backend.enqueue.assert_called_once()
        assert result != existing_job_id

    def test_force_reextract_default_is_false(self) -> None:
        """Calling queue_for_processing without force_reextract preserves
        the safe (dedup-honoring) default. Guards against an accidental
        signature change that flips the default."""
        existing_job_id = "existing-job-789"
        content_entry = MagicMock(hash="hash-xyz", job_id=existing_job_id)
        content_store = MagicMock()
        content_store.store_content.return_value = content_entry
        mock_backend = MagicMock()

        with (
            patch(
                "app.content_store.config.get_content_store",
                return_value=content_store,
            ),
            patch(
                "app.llm.queue.backend.get_queue_backend",
                return_value=mock_backend,
            ),
        ):
            utils = _make_utils()
            # No force_reextract kwarg — must dedup
            result = utils.queue_for_processing("payload")

        assert result == existing_job_id
        mock_backend.enqueue.assert_not_called()
