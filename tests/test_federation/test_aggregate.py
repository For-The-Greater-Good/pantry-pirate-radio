"""Task 3 (PR-B): tests for the §8.2 Location aggregate serializer.

Red-first TDD for ``app.federation.aggregate.build_location_aggregate`` — the
function that produces the HSDS Location object that becomes the ``object`` field
of a federation activity envelope.

DB-backed against the real ``location`` / ``location_source`` / ``schedule``
tables, using the sync ``Session`` access pattern mirrored from
``tests/test_federation/test_log_append.py`` (``create_engine`` on
``DATABASE_URL`` with the ``postgresql+asyncpg://`` -> ``postgresql://`` rewrite;
``sessionmaker``). All data here is fictional — no PII.

Load-bearing correctness properties under test:
  * the object validates against the UNMODIFIED HSDS 3.1.1 ``LocationResponse``
    (Principle II);
  * envelope-only identity fields never leak into the object;
  * two DISTINCT schedule rows are NOT collapsed (spike Proof 2 / the historic
    ``DISTINCT ON`` bug).
"""

import os
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.federation.aggregate import build_location_aggregate
from app.models.hsds.response import LocationResponse

_SEED = bytes(range(32))


def _signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


@pytest.fixture()
def db_session():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)
    maker = sessionmaker(bind=engine)
    session = maker()
    yield session
    session.rollback()
    # Clean only the rows this test inserted (CASCADE clears child rows too).
    session.execute(text("TRUNCATE TABLE location CASCADE"))
    session.commit()
    session.close()
    engine.dispose()


def _insert_location(
    session,
    *,
    name: str = "Fictional Community Pantry",
    description: str | None = "A made-up food pantry for tests.",
    latitude: float = 40.7128,
    longitude: float = -74.0060,
    location_type: str = "physical",
    alternate_name: str | None = "FCP",
    transportation: str | None = "Bus route 12",
    external_identifier: str | None = "EXT-001",
    external_identifier_type: str | None = "internal",
) -> str:
    loc_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO location (
                id, name, alternate_name, description, latitude, longitude,
                location_type, transportation, external_identifier,
                external_identifier_type, is_canonical, created_at, updated_at
            ) VALUES (
                :id, :name, :alternate_name, :description, :latitude, :longitude,
                :location_type, :transportation, :external_identifier,
                :external_identifier_type, TRUE, NOW(), NOW()
            )
            """
        ),
        {
            "id": loc_id,
            "name": name,
            "alternate_name": alternate_name,
            "description": description,
            "latitude": latitude,
            "longitude": longitude,
            "location_type": location_type,
            "transportation": transportation,
            "external_identifier": external_identifier,
            "external_identifier_type": external_identifier_type,
        },
    )
    session.commit()
    return loc_id


def _insert_source(
    session,
    location_id: str,
    *,
    scraper_id: str,
    name: str = "Fictional Community Pantry",
    description: str | None = "Source-specific description.",
    latitude: float = 40.7128,
    longitude: float = -74.0060,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO location_source (
                id, location_id, scraper_id, name, description,
                latitude, longitude, location_type, created_at, updated_at
            ) VALUES (
                :id, :location_id, :scraper_id, :name, :description,
                :latitude, :longitude, 'physical', NOW(), NOW()
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "location_id": location_id,
            "scraper_id": scraper_id,
            "name": name,
            "description": description,
            "latitude": latitude,
            "longitude": longitude,
        },
    )
    session.commit()


def _insert_schedule(
    session,
    location_id: str,
    *,
    freq: str = "WEEKLY",
    byday: str,
    opens_at: str,
    closes_at: str,
    description: str | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO schedule (
                id, location_id, freq, byday, opens_at, closes_at, description
            ) VALUES (
                :id, :location_id, :freq, :byday, :opens_at, :closes_at, :description
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "location_id": location_id,
            "freq": freq,
            "byday": byday,
            "opens_at": opens_at,
            "closes_at": closes_at,
            "description": description,
        },
    )
    session.commit()


def test_object_validates_against_unmodified_hsds_model(db_session) -> None:
    """The aggregate must round-trip through the UNMODIFIED HSDS 3.1.1 model."""
    loc_id = _insert_location(db_session)
    obj = build_location_aggregate(db_session, loc_id)
    # Must not raise — Principle II.
    LocationResponse.model_validate(obj)


def test_object_excludes_envelope_identity_fields(db_session) -> None:
    """Envelope-only fields must NEVER appear inside the object (design m1)."""
    loc_id = _insert_location(db_session)
    obj = build_location_aggregate(db_session, loc_id)
    for forbidden in ("federation_id", "attributedTo", "origin", "license"):
        assert forbidden not in obj, f"{forbidden} leaked into the object"


def test_two_distinct_schedules_not_collapsed(db_session) -> None:
    """Two distinct schedule rows must yield two schedules (spike Proof 2)."""
    loc_id = _insert_location(db_session)
    _insert_schedule(
        db_session,
        loc_id,
        byday="MO",
        opens_at="09:00",
        closes_at="12:00",
        description="Mon morning",
    )
    _insert_schedule(
        db_session,
        loc_id,
        byday="TH",
        opens_at="13:00",
        closes_at="17:00",
        description="Thu afternoon",
    )
    obj = build_location_aggregate(db_session, loc_id)
    schedules = obj["schedules"]
    assert len(schedules) == 2
    bydays = {s["byday"] for s in schedules}
    assert bydays == {"MO", "TH"}
    # opens_at/closes_at are stored as TIME and stringified to HH:MM:SS; assert
    # on the HH:MM prefix so the test is robust to the column's serialized form.
    windows = {(s["opens_at"][:5], s["closes_at"][:5]) for s in schedules}
    assert windows == {("09:00", "12:00"), ("13:00", "17:00")}


def test_scalar_fields_mapped(db_session) -> None:
    """Scalar HSDS fields are mapped from the location row."""
    loc_id = _insert_location(
        db_session,
        name="Harbor Free Pantry",
        description="Weekly groceries, no questions asked.",
        latitude=41.0,
        longitude=-73.5,
        location_type="physical",
        alternate_name="HFP",
        transportation="Near ferry terminal",
        external_identifier="HFP-77",
        external_identifier_type="legacy",
    )
    obj = build_location_aggregate(db_session, loc_id)
    assert obj["name"] == "Harbor Free Pantry"
    assert obj["description"] == "Weekly groceries, no questions asked."
    assert obj["latitude"] == 41.0
    assert obj["longitude"] == -73.5
    assert obj["location_type"] == "physical"
    assert obj["alternate_name"] == "HFP"
    assert obj["transportation"] == "Near ferry terminal"
    assert obj["external_identifier"] == "HFP-77"
    assert obj["external_identifier_type"] == "legacy"


def test_sources_and_source_count(db_session) -> None:
    """Sources come from location_source; source_count == number of sources."""
    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    _insert_source(db_session, loc_id, scraper_id="scraper_b")
    obj = build_location_aggregate(db_session, loc_id)
    assert obj["source_count"] == 2
    scrapers = {s["scraper"] for s in obj["sources"]}
    assert scrapers == {"scraper_a", "scraper_b"}
    # Still conformant with the model.
    LocationResponse.model_validate(obj)


def test_no_sources_yields_source_count_one(db_session) -> None:
    """A location with no source rows reports the model default source_count=1."""
    loc_id = _insert_location(db_session)
    obj = build_location_aggregate(db_session, loc_id)
    assert obj["sources"] == []
    # Model default for source_count is 1 (see LocationResponse).
    assert obj["source_count"] == 1


def test_missing_location_raises(db_session) -> None:
    """Unknown location id raises ValueError (documented contract)."""
    with pytest.raises(ValueError):
        build_location_aggregate(db_session, str(uuid.uuid4()))


def test_end_to_end_envelope_seam(db_session) -> None:
    """The aggregate feeds the envelope; the signed envelope's object still
    validates and the envelope verifies (object-integrity proof)."""
    from app.federation import envelope as envelope_mod

    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    _insert_schedule(
        db_session,
        loc_id,
        byday="MO",
        opens_at="09:00",
        closes_at="12:00",
    )
    obj = build_location_aggregate(db_session, loc_id)

    key = _signing_key()
    preimage = envelope_mod.build_preimage(
        context="https://hsds-federation.pantrypirateradio.org/profile",
        activity_type="Update",
        actor="did:web:example.org",
        attributed_to="did:web:example.org",
        origin="did:web:example.org",
        federation_id="example.org:loc-1",
        obj=obj,
        sequence=1,
        published="2026-06-06T00:00:00Z",
        license="sandia-ftgg-nc-os-1.0",
    )
    envelope = envelope_mod.finalize(preimage, key)

    # The object inside the signed envelope still validates against the model.
    LocationResponse.model_validate(envelope["object"])
    # And the object-integrity proof verifies.
    assert envelope_mod.verify_envelope(envelope, key.public_key()) is True
