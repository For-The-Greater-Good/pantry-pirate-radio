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
    loc_id: str | None = None,
    confidence_score: int = 50,
    organization_id: str | None = None,
) -> str:
    loc_id = loc_id or str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO location (
                id, name, alternate_name, description, latitude, longitude,
                location_type, transportation, external_identifier,
                external_identifier_type, confidence_score, organization_id,
                is_canonical, created_at, updated_at
            ) VALUES (
                :id, :name, :alternate_name, :description, :latitude, :longitude,
                :location_type, :transportation, :external_identifier,
                :external_identifier_type, :confidence_score, :organization_id,
                TRUE, NOW(), NOW()
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
            "confidence_score": confidence_score,
            "organization_id": organization_id,
        },
    )
    session.commit()
    return loc_id


def _insert_organization(
    session,
    *,
    name: str = "Fictional Org",
    website: str | None = None,
    email: str | None = None,
) -> str:
    org_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO organization (id, name, description, website, email)
            VALUES (:id, :name, 'A made-up org for tests.', :website, :email)
            """
        ),
        {"id": org_id, "name": name, "website": website, "email": email},
    )
    session.commit()
    return org_id


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


def _insert_address(
    session,
    location_id: str,
    *,
    address_1: str,
    city: str = "Anytown",
    state_province: str = "NY",
    postal_code: str = "10001",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO address (
                id, location_id, address_1, city, state_province, postal_code,
                country, address_type
            ) VALUES (
                :id, :location_id, :address_1, :city, :state_province,
                :postal_code, 'US', 'physical'
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "location_id": location_id,
            "address_1": address_1,
            "city": city,
            "state_province": state_province,
            "postal_code": postal_code,
        },
    )
    session.commit()


def _insert_phone(session, location_id: str, *, number: str) -> None:
    session.execute(
        text("INSERT INTO phone (id, location_id, number) VALUES (:id, :loc, :num)"),
        {"id": str(uuid.uuid4()), "loc": location_id, "num": number},
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


@pytest.mark.interop_pending  # pins the HSDS 3.1.1-curated object field set (INTEROP_PENDING.md row 5)
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


# --- RED-tier Gauntlet AGGREGATE findings: a SourceInfo row must not be
# cartesian-multiplied by satellite address/phone rows, an absent address must
# canonicalize as omitted (not ""), and a non-UUID id must fail with the
# documented ValueError — all in the SIGNED bytes.


def test_multiple_addresses_phones_do_not_inflate_one_scraper(db_session) -> None:
    """One scraper with 2 addresses + 2 phones must yield exactly ONE source and
    source_count 1 — not a 1x2x2=4 cartesian explosion in the signed object."""
    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    _insert_address(db_session, loc_id, address_1="1 First St")
    _insert_address(db_session, loc_id, address_1="2 Second Ave")
    _insert_phone(db_session, loc_id, number="555-0001")
    _insert_phone(db_session, loc_id, number="555-0002")

    obj = build_location_aggregate(db_session, loc_id)
    assert len(obj["sources"]) == 1
    assert obj["sources"][0]["scraper"] == "scraper_a"
    assert obj["source_count"] == 1
    LocationResponse.model_validate(obj)


def test_multiple_satellites_two_scrapers_yield_two_sources(db_session) -> None:
    """Two scrapers, each with multiple addresses/phones, yield exactly two
    sources and source_count 2 (distinct scraper count)."""
    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    _insert_source(db_session, loc_id, scraper_id="scraper_b")
    _insert_address(db_session, loc_id, address_1="1 First St")
    _insert_address(db_session, loc_id, address_1="2 Second Ave")
    _insert_phone(db_session, loc_id, number="555-0001")
    _insert_phone(db_session, loc_id, number="555-0002")

    obj = build_location_aggregate(db_session, loc_id)
    assert {s["scraper"] for s in obj["sources"]} == {"scraper_a", "scraper_b"}
    assert len(obj["sources"]) == 2
    assert obj["source_count"] == 2
    LocationResponse.model_validate(obj)


def test_absent_address_is_omitted_not_empty_string(db_session) -> None:
    """A source with no address rows must omit `address` (exclude_none), never
    serialize an empty string into the signed object."""
    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    obj = build_location_aggregate(db_session, loc_id)
    assert len(obj["sources"]) == 1
    assert obj["sources"][0].get("address", None) in (None,)
    assert "address" not in obj["sources"][0]


def test_present_address_is_assembled(db_session) -> None:
    """A real address is still assembled into the source (regression guard)."""
    loc_id = _insert_location(db_session)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    _insert_address(
        db_session,
        loc_id,
        address_1="100 Main St",
        city="Anytown",
        state_province="NY",
        postal_code="10001",
    )
    obj = build_location_aggregate(db_session, loc_id)
    assert obj["sources"][0]["address"] == "100 Main St, Anytown, NY, 10001"


def test_corrupt_schedule_dropped_emits_event_and_keeps_good_rows(db_session) -> None:
    """OBS-1: the fail-soft schedule branch (a row whose byday the RFC-5545
    normalizer cannot parse) drops ONLY that row, keeps valid rows, and emits the
    runbook event `federation_aggregate_schedule_dropped_invalid` with its
    documented fields. The event name is an operational grep target, so it is
    asserted as a contract — not just the behavior."""
    from structlog.testing import capture_logs

    loc_id = _insert_location(db_session)
    _insert_schedule(
        db_session, loc_id, byday="MO", opens_at="09:00", closes_at="12:00"
    )
    _insert_schedule(
        db_session, loc_id, byday="GARBAGE_DAY", opens_at="09:00", closes_at="12:00"
    )
    with capture_logs() as logs:
        obj = build_location_aggregate(db_session, loc_id)

    # The valid window survives; the corrupt one is dropped.
    assert {s["byday"] for s in obj["schedules"]} == {"MO"}

    dropped = [
        e
        for e in logs
        if e.get("event") == "federation_aggregate_schedule_dropped_invalid"
    ]
    assert len(dropped) == 1, "expected exactly one schedule-dropped event"
    evt = dropped[0]
    assert evt["location_id"] == loc_id
    assert evt["byday"] == "GARBAGE_DAY"
    assert "error" in evt and "freq" in evt and "bymonthday" in evt


def test_confidence_score_zero_is_preserved_not_defaulted(db_session) -> None:
    """A stored confidence_score of 0 must appear as 0 in the signed object — not
    silently become 50 (the `or 50` falsy-fallback bug)."""
    loc_id = _insert_location(db_session, confidence_score=0)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    obj = build_location_aggregate(db_session, loc_id)
    assert obj["sources"][0]["confidence_score"] == 0


def test_empty_org_website_email_omitted_not_empty_string(db_session) -> None:
    """Empty-string org website/email must be omitted, never serialized as "" into
    the signed object (one canonical 'absent' form)."""
    org_id = _insert_organization(db_session, website="", email="")
    loc_id = _insert_location(db_session, organization_id=org_id)
    _insert_source(db_session, loc_id, scraper_id="scraper_a")
    obj = build_location_aggregate(db_session, loc_id)
    src = obj["sources"][0]
    assert "website" not in src and "email" not in src


def test_non_uuid_location_id_raises_value_error(db_session) -> None:
    """A location row whose id is not UUID-shaped must raise the documented
    ValueError — not a raw pydantic ValidationError. (ValidationError is itself a
    ValueError subclass, but it leaks internal construction detail; the
    aggregate's contract is a clean, caller-handleable ValueError naming the id.)"""
    from pydantic import ValidationError

    _insert_location(db_session, loc_id="not-a-uuid")
    with pytest.raises(ValueError) as exc_info:
        build_location_aggregate(db_session, "not-a-uuid")
    assert not isinstance(exc_info.value, ValidationError)
    assert "not-a-uuid" in str(exc_info.value)
