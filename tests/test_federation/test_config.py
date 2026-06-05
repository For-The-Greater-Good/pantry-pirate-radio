from app.core.config import Settings


def test_federation_settings_have_safe_defaults():
    s = Settings()
    assert s.FEDERATION_ENABLED is True  # on by default (driver 3)
    assert s.FEDERATION_DATE_SKEW_SECONDS == 300  # §8.3 replay window
    assert s.FEDERATION_RETENTION_DAYS == 365  # OPR SLA
    assert s.FEDERATION_INGEST_MAX_RECORDS_PER_PEER_PER_DAY > 0  # §11.3 budget
    assert s.FEDERATION_DID is None or s.FEDERATION_DID.startswith(
        ("did:web:", "https://")
    )
