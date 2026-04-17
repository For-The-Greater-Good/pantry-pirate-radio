"""Tests for app.reconciler.drift_events.

Covers the SNS publisher in isolation — the merge-strategy call-site
integration is exercised indirectly via test_merge_strategy.py.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from app.reconciler import drift_events
from app.reconciler.drift_events import publish_drift_event


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Each test starts with no cached boto3 client so env-var mutations
    take effect."""
    drift_events._sns_client = None
    yield
    drift_events._sns_client = None


def test_skips_when_topic_arn_unset(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    monkeypatch.delenv("LIGHTHOUSE_EVENTS_TOPIC_ARN", raising=False)
    spy = mocker.patch("boto3.client")

    sent = publish_drift_event(
        location_id="loc-1",
        scraper_name="vivery",
        field_name="name",
        scraper_value="x",
        canonical_value="y",
    )

    assert sent is False
    spy.assert_not_called()


def test_publishes_when_topic_arn_is_set(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    monkeypatch.setenv(
        "LIGHTHOUSE_EVENTS_TOPIC_ARN",
        "arn:aws:sns:us-east-1:123456789012:outreach-events",
    )
    sns = MagicMock()
    mocker.patch("boto3.client", return_value=sns)

    sent = publish_drift_event(
        location_id="loc-42",
        scraper_name="feeding_america_nc",
        field_name="name",
        scraper_value="Food Bank of Wake",
        canonical_value="Food Bank of Wake County",
    )

    assert sent is True
    sns.publish.assert_called_once()
    kwargs = sns.publish.call_args.kwargs
    assert kwargs["TopicArn"].endswith(":outreach-events")
    payload = json.loads(kwargs["Message"])
    assert payload["event_type"] == "source_drift_detected"
    assert payload["location_id"] == "loc-42"
    assert payload["scraper_name"] == "feeding_america_nc"
    assert payload["field_name"] == "name"
    assert payload["scraper_value"] == "Food Bank of Wake"
    assert payload["canonical_value"] == "Food Bank of Wake County"
    assert "event_id" in payload
    assert "detected_at" in payload
    assert (
        kwargs["MessageAttributes"]["event_type"]["StringValue"]
        == "source_drift_detected"
    )


def test_swallows_boto_errors(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    monkeypatch.setenv(
        "LIGHTHOUSE_EVENTS_TOPIC_ARN",
        "arn:aws:sns:us-east-1:123456789012:outreach-events",
    )
    sns = MagicMock()
    sns.publish.side_effect = ClientError(
        {"Error": {"Code": "AuthorizationError", "Message": "no"}},
        "Publish",
    )
    mocker.patch("boto3.client", return_value=sns)

    sent = publish_drift_event(
        location_id="loc-1",
        scraper_name="vivery",
        field_name="description",
        scraper_value="x",
        canonical_value="y",
    )

    assert sent is False  # graceful — no exception propagates
