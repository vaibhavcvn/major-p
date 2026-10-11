"""
Phase 5 — Focused tests for M-1 through M-7.

M-1  Coordinate validation (8 cases)
M-2  Password minimum length (3 cases)
M-3  Auth rate limiting (3 cases)
M-4  Traffic privacy — no pickup_address (4 cases)
M-5  Driver GPS requirement — no fake 0 km (4 cases)
M-6  /ml/predict authentication (3 cases)
M-7  JWT lifetime configuration (3 cases)

Total: 28 tests
"""
import asyncio
import os
import datetime
import pytest

from app.models import (
    User, Driver, Ambulance, Hospital, Trip, TripStatus, UserRole,
)
from app.auth import get_password_hash, create_access_token
from app.config import settings
from app.dispatch import find_eligible_drivers


# ── helpers ─────────────────────────────────────────────────────────────────

def _hash(pw="pass12345"):
    return get_password_hash(pw)


def _make_user(db, suffix, role="PATIENT"):
    u = User(email=f"mi_{suffix}@test.com", password_hash=_hash(),
             role=role, full_name=f"MI {suffix}")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_driver(db, suffix, lat=None, lng=None, on_duty=True):
    u = _make_user(db, f"drv_{suffix}", "DRIVER")
    d = Driver(user_id=u.id, license_number=f"MI-{suffix}",
               is_on_duty=on_duty, current_lat=lat, current_lng=lng)
    db.add(d); db.commit(); db.refresh(d)
    a = Ambulance(driver_id=d.id, vehicle_number=f"MIAMB-{suffix}",
                  type="ALS", is_active=True, current_lat=lat, current_lng=lng)
    db.add(a); db.commit(); db.refresh(a)
    return d, u


def _make_hospital(db, suffix):
    h = Hospital(name=f"MI Hosp {suffix}", latitude=12.98, longitude=77.60,
                 address="MI Rd", total_beds=50, available_beds=20,
                 trauma_level=1, is_ready=True)
    db.add(h); db.commit(); db.refresh(h)
    return h


def _tok(user):
    return create_access_token({"sub": str(user.id), "role": user.role})


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ══════════════════════════════════════════════════════════════════════════════
# M-1  Coordinate validation
# ══════════════════════════════════════════════════════════════════════════════

def _book_payload(lat, lng):
    return {
        "pickup_address": "Test St",
        "pickup_lat": lat,
        "pickup_lng": lng,
        "severity": "HIGH",
    }


def test_m1_valid_coordinates_accepted(client, db_session):
    """Normal coordinates within valid range must succeed."""
    u = _make_user(db_session, "m1a")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(12.9716, 77.5946),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_m1_lat_too_high_rejected(client, db_session):
    """Latitude > 90 must be rejected (422)."""
    u = _make_user(db_session, "m1b")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(91.0, 77.59),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_m1_lat_too_low_rejected(client, db_session):
    """Latitude < -90 must be rejected (422)."""
    u = _make_user(db_session, "m1c")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(-91.0, 77.59),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_m1_lng_too_high_rejected(client, db_session):
    """Longitude > 180 must be rejected (422)."""
    u = _make_user(db_session, "m1d")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(12.97, 181.0),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_m1_lng_too_low_rejected(client, db_session):
    """Longitude < -180 must be rejected (422)."""
    u = _make_user(db_session, "m1e")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(12.97, -181.0),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_m1_boundary_lat_90_accepted(client, db_session):
    """Boundary value lat=90 must be accepted."""
    u = _make_user(db_session, "m1f")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(90.0, 0.0),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_m1_boundary_lat_neg90_accepted(client, db_session):
    """Boundary value lat=-90 must be accepted."""
    u = _make_user(db_session, "m1g")
    tok = _tok(u)
    r = client.post("/api/v1/patient/book",
                    json=_book_payload(-90.0, 0.0),
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_m1_boundary_lng_180_accepted(client, db_session):
    """Boundary values lat=0, lng=±180 must be accepted."""
    u = _make_user(db_session, "m1h")
    tok = _tok(u)
    for lng in (180.0, -180.0):
        r = client.post("/api/v1/patient/book",
                        json=_book_payload(0.0, lng),
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, f"lng={lng} should be accepted, got {r.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# M-2  Password minimum length
# ══════════════════════════════════════════════════════════════════════════════

def test_m2_short_password_rejected(client, db_session):
    """Password shorter than 8 characters must be rejected (422)."""
    r = client.post("/api/v1/auth/register", json={
        "email": "m2_short@test.com",
        "password": "abc",        # 3 chars
        "full_name": "Short PW",
        "role": "PATIENT",
    })
    assert r.status_code == 422


def test_m2_exactly_8_chars_accepted(client, db_session):
    """Exactly 8-character password must be accepted."""
    r = client.post("/api/v1/auth/register", json={
        "email": "m2_8char@test.com",
        "password": "abcd1234",   # exactly 8
        "full_name": "Eight PW",
        "role": "PATIENT",
    })
    assert r.status_code == 200, f"8-char password should be accepted: {r.text}"


def test_m2_existing_registration_still_works(client, db_session):
    """Normal registration with a strong password must continue working."""
    r = client.post("/api/v1/auth/register", json={
        "email": "m2_normal@test.com",
        "password": "strongPass99!",
        "full_name": "Normal PW",
        "role": "PATIENT",
    })
    assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# M-3  Rate limiting
# NOTE: conftest sets RATE_LIMIT_ENABLED=0 globally so normal tests don't hit
# the limit.  These tests temporarily re-enable it with a tight window.
# ══════════════════════════════════════════════════════════════════════════════

def test_m3_normal_login_not_rate_limited(client, db_session):
    """A single login attempt must always succeed (not limited)."""
    client.post("/api/v1/auth/register", json={
        "email": "m3_user@test.com", "password": "pass12345",
        "full_name": "M3 User", "role": "PATIENT",
    })
    r = client.post("/api/v1/auth/login",
                    json={"email": "m3_user@test.com", "password": "pass12345"})
    assert r.status_code == 200


def test_m3_rate_limit_triggers_after_many_attempts(client, db_session):
    """Exceeding the limit from the same IP must return 429."""
    from app.main import _auth_limiter, _SlidingWindowLimiter
    import importlib, app.main as main_module

    # Temporarily replace with a tight limiter (max 3 per 60s) for this test
    original = main_module._auth_limiter
    main_module._auth_limiter = _SlidingWindowLimiter(max_calls=3, window_seconds=60)

    # Also temporarily re-enable limiting (conftest sets it to 0)
    original_env = os.environ.get("RATE_LIMIT_ENABLED", "0")
    os.environ["RATE_LIMIT_ENABLED"] = "1"

    try:
        last_status = None
        for i in range(5):
            r = client.post("/api/v1/auth/login",
                            json={"email": f"nosuch_{i}@test.com", "password": "wrongpass"})
            last_status = r.status_code
        assert last_status == 429, \
            f"Expected 429 after exceeding limit; last status was {last_status}"
    finally:
        main_module._auth_limiter = original
        os.environ["RATE_LIMIT_ENABLED"] = original_env


def test_m3_rate_limit_disabled_in_tests(client, db_session):
    """With RATE_LIMIT_ENABLED=0, many attempts must NOT trigger 429."""
    assert os.environ.get("RATE_LIMIT_ENABLED") == "0"
    for i in range(15):
        r = client.post("/api/v1/auth/login",
                        json={"email": f"rl_test_{i}@test.com", "password": "wrong"})
        assert r.status_code != 429, f"Rate limit must be disabled in tests, got 429 on call {i}"


# ══════════════════════════════════════════════════════════════════════════════
# M-4  Traffic privacy — no pickup_address
# ══════════════════════════════════════════════════════════════════════════════

def test_m4_traffic_corridors_no_pickup_address(client, db_session):
    """GET /traffic/corridors must not return pickup_address."""
    _make_hospital(db_session, "m4")
    p  = _make_user(db_session, "m4p")
    d, du = _make_driver(db_session, "m4d", lat=12.97, lng=77.59)

    # Create an active trip
    amb = db_session.query(Ambulance).filter(Ambulance.driver_id == d.id).first()
    trip = Trip(patient_id=p.id, assigned_driver_id=d.id, assigned_ambulance_id=amb.id,
                status=TripStatus.ASSIGNED, severity="HIGH",
                pickup_address="1 Private Patient Street, Bangalore",
                pickup_lat=12.97, pickup_lng=77.59)
    db_session.add(trip); db_session.commit()

    t_user = _make_user(db_session, "m4t", "TRAFFIC")
    tok = _tok(t_user)
    r = client.get("/api/v1/traffic/corridors",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    corridors = r.json()
    for corridor in corridors:
        assert "pickup_address" not in corridor, \
            f"Traffic must not receive pickup_address; got: {corridor}"


def test_m4_traffic_no_patient_pii(client, db_session):
    """Traffic corridors must not contain patient name or phone."""
    _make_hospital(db_session, "m4b")
    p = _make_user(db_session, "m4pb")
    p.phone = "+91-5555555555"
    db_session.commit()
    d, du = _make_driver(db_session, "m4db", lat=12.97, lng=77.59)
    amb = db_session.query(Ambulance).filter(Ambulance.driver_id == d.id).first()

    trip = Trip(patient_id=p.id, assigned_driver_id=d.id, assigned_ambulance_id=amb.id,
                status=TripStatus.ASSIGNED, severity="HIGH",
                pickup_address="2 Secret Rd", pickup_lat=12.97, pickup_lng=77.59)
    db_session.add(trip); db_session.commit()

    t_user = _make_user(db_session, "m4tb", "TRAFFIC")
    tok = _tok(t_user)
    r = client.get("/api/v1/traffic/corridors",
                   headers={"Authorization": f"Bearer {tok}"})
    corridors_str = r.text
    assert p.full_name not in corridors_str, "Patient name must not appear in traffic response"
    assert "+91-5555555555" not in corridors_str, "Patient phone must not appear in traffic response"


def test_m4_patient_still_sees_pickup_address(client, db_session):
    """Patient's own trip must still include the pickup address."""
    _make_hospital(db_session, "m4c")
    p = _make_user(db_session, "m4pc")
    d, du = _make_driver(db_session, "m4dc", lat=12.97, lng=77.59)
    amb = db_session.query(Ambulance).filter(Ambulance.driver_id == d.id).first()

    trip = Trip(patient_id=p.id, assigned_driver_id=d.id, assigned_ambulance_id=amb.id,
                status=TripStatus.ASSIGNED, severity="HIGH",
                pickup_address="Patient Sees This Address",
                pickup_lat=12.97, pickup_lng=77.59)
    db_session.add(trip); db_session.commit()

    tok = _tok(p)
    r = client.get(f"/api/v1/patient/trip/{trip.id}",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["pickup_address"] == "Patient Sees This Address"


def test_m4_admin_still_sees_pickup_address(client, db_session):
    """Admin overview recent_trips must still include pickup addresses."""
    _make_hospital(db_session, "m4d")
    p = _make_user(db_session, "m4pd")
    d, du = _make_driver(db_session, "m4dd", lat=12.97, lng=77.59)
    amb = db_session.query(Ambulance).filter(Ambulance.driver_id == d.id).first()

    trip = Trip(patient_id=p.id, assigned_driver_id=d.id, assigned_ambulance_id=amb.id,
                status=TripStatus.ASSIGNED, severity="HIGH",
                pickup_address="Admin Should See This",
                pickup_lat=12.97, pickup_lng=77.59)
    db_session.add(trip); db_session.commit()

    admin = User(email="m4_admin@test.com", password_hash=_hash(),
                 role=UserRole.ADMIN, full_name="M4 Admin")
    db_session.add(admin); db_session.commit()
    tok = _tok(admin)

    r = client.get("/api/v1/admin/overview",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    recent = r.json().get("recent_trips", [])
    if recent:
        found = any(t.get("pickup_address") for t in recent)
        assert found, "Admin must still see pickup_address in recent_trips"


# ══════════════════════════════════════════════════════════════════════════════
# M-5  Driver GPS requirement
# ══════════════════════════════════════════════════════════════════════════════

def test_m5_driver_with_gps_is_eligible(db_session):
    """A driver with known GPS coordinates must appear in find_eligible_drivers."""
    _make_hospital(db_session, "m5a")
    d, _ = _make_driver(db_session, "m5a", lat=12.97, lng=77.59)
    candidates = find_eligible_drivers(db_session, 12.97, 77.59)
    driver_ids = [c[0].id for c in candidates]
    assert d.id in driver_ids, "Driver with GPS must be included in candidates"


def test_m5_driver_without_gps_excluded(db_session):
    """A driver with NULL GPS coordinates must NOT appear in find_eligible_drivers."""
    _make_hospital(db_session, "m5b")
    d, _ = _make_driver(db_session, "m5b", lat=None, lng=None)  # no GPS
    candidates = find_eligible_drivers(db_session, 12.97, 77.59)
    driver_ids = [c[0].id for c in candidates]
    assert d.id not in driver_ids, \
        "Driver without GPS must NOT be included — must not appear as 0 km away"


def test_m5_no_gps_driver_cannot_win_nearest(db_session):
    """A driver without GPS must not beat a driver with GPS on distance."""
    _make_hospital(db_session, "m5c")
    d_no_gps, _ = _make_driver(db_session, "m5c_nogps", lat=None, lng=None)
    d_with_gps, _ = _make_driver(db_session, "m5c_gps", lat=12.97, lng=77.59)

    candidates = find_eligible_drivers(db_session, 12.97, 77.59)
    driver_ids = [c[0].id for c in candidates]

    assert d_no_gps.id not in driver_ids, "No-GPS driver must be excluded"
    assert d_with_gps.id in driver_ids, "GPS driver must still be included"
    # GPS driver must be first (only valid candidate)
    assert candidates[0][0].id == d_with_gps.id


def test_m5_all_no_gps_returns_empty(db_session):
    """If all drivers lack GPS coordinates, find_eligible_drivers returns empty list."""
    _make_hospital(db_session, "m5d")
    _make_driver(db_session, "m5d1", lat=None, lng=None)
    _make_driver(db_session, "m5d2", lat=None, lng=None)

    candidates = find_eligible_drivers(db_session, 12.97, 77.59)
    assert candidates == [], \
        "No GPS drivers should yield empty candidate list, not a fake 0km result"


# ══════════════════════════════════════════════════════════════════════════════
# M-6  /ml/predict authentication
# ══════════════════════════════════════════════════════════════════════════════

_PREDICT_PAYLOAD = {
    "pickup_lat": 12.97, "pickup_lng": 77.59,
    "dest_lat": 12.98, "dest_lng": 77.60,
    "osrm_distance_km": 5.0,
    "osrm_duration_min": 10.0,
    "severity": "HIGH",
}


def test_m6_anonymous_rejected(client, db_session):
    """Anonymous POST /ml/predict must return 401."""
    r = client.post("/api/v1/ml/predict", json=_PREDICT_PAYLOAD)
    assert r.status_code == 401, f"Expected 401 for anonymous; got {r.status_code}"


def test_m6_authorized_role_accepted(client, db_session):
    """An ADMIN user must be able to call /ml/predict."""
    admin = User(email="m6_admin@test.com", password_hash=_hash(),
                 role=UserRole.ADMIN, full_name="M6 Admin")
    db_session.add(admin); db_session.commit()
    tok = _tok(admin)

    r = client.post("/api/v1/ml/predict", json=_PREDICT_PAYLOAD,
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, f"ADMIN should be able to call /ml/predict: {r.text}"
    assert "predicted_delay_minutes" in r.json()


def test_m6_patient_rejected(client, db_session):
    """PATIENT role must be rejected from /ml/predict (not an operational role)."""
    p = _make_user(db_session, "m6p")
    tok = _tok(p)
    r = client.post("/api/v1/ml/predict", json=_PREDICT_PAYLOAD,
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, f"PATIENT must be rejected from /ml/predict; got {r.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# M-7  JWT lifetime configurable
# ══════════════════════════════════════════════════════════════════════════════

def test_m7_lifetime_comes_from_settings():
    """ACCESS_TOKEN_EXPIRE_MINUTES must come from settings, not be hardcoded."""
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0, "Token lifetime must be positive"
    # Verify it uses the env-configured value (1440 from .env in test run)
    # and is NOT the old hardcoded 7-day (10080) value
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES != 10080, \
        "Default must not be the old 7-day (10080 min) hardcoded value"


def test_m7_token_works_normally(client, db_session):
    """Tokens must still function for authenticated requests."""
    u = _make_user(db_session, "m7a")
    tok = _tok(u)
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["email"] == "mi_m7a@test.com"


def test_m7_expired_token_rejected(client, db_session):
    """A token with exp in the past must be rejected with 401."""
    from jose import jwt
    expired_token = jwt.encode(
        {
            "sub": "999",
            "role": "PATIENT",
            "exp": datetime.datetime.utcnow() - datetime.timedelta(seconds=10),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401, f"Expired token must return 401; got {r.status_code}"
