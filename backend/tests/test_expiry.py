"""
Phase 3 — Focused tests for dispatch request expiry, redispatch, and race safety.

All tests call expire_pending_requests(db) directly (injected db session) so they
work with the in-memory SQLite test database used by conftest.py.

with_for_update() is a no-op on SQLite but does not raise — state assertions
verify the same outcomes that row locking enforces on PostgreSQL.
"""
import datetime
import pytest
import asyncio

from app.models import (
    User, Driver, Ambulance, Hospital, Trip, DispatchRequest,
    TripStatus, DispatchStatus,
)
from app.auth import get_password_hash
from app.dispatch import expire_pending_requests, dispatch_next_driver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash():
    return get_password_hash("pass")


def _make_patient(db, suffix=""):
    """Creates a patient user; email = patient_{suffix}@test.com"""
    email = f"patient_{suffix}@test.com"
    u = User(email=email, password_hash=_hash(), role="PATIENT", full_name="Test Patient")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_driver(db, suffix="", on_duty=True, lat=12.97, lng=77.59):
    """Creates a driver user + Driver profile + Ambulance; email = driver_{suffix}@test.com"""
    email = f"driver_{suffix}@test.com"
    u = User(email=email, password_hash=_hash(), role="DRIVER", full_name=f"Driver {suffix}")
    db.add(u)
    db.commit()
    db.refresh(u)
    d = Driver(user_id=u.id, license_number=f"LIC-{suffix}", is_on_duty=on_duty,
               current_lat=lat, current_lng=lng)
    db.add(d)
    db.commit()
    db.refresh(d)
    a = Ambulance(driver_id=d.id, vehicle_number=f"AMB-EXP-{suffix}",
                  type="ALS", is_active=True, current_lat=lat, current_lng=lng)
    db.add(a)
    db.commit()
    db.refresh(a)
    return d


def _make_hospital(db):
    h = Hospital(name="Expiry Test Hospital", latitude=12.98, longitude=77.60,
                 address="Test Rd", total_beds=50, available_beds=20,
                 trauma_level=1, is_ready=True)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _make_trip(db, patient, status=TripStatus.DRIVER_REQUESTED):
    t = Trip(patient_id=patient.id, status=status, severity="HIGH",
             pickup_address="Test Pickup", pickup_lat=12.97, pickup_lng=77.59)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_dispatch_req(db, trip, driver, *, already_expired=False, offset_seconds=-1):
    """
    Create a DispatchRequest.
    already_expired=True  → expires_at in the past (will be caught by worker).
    offset_seconds        → seconds relative to now (negative = already expired).
    """
    if already_expired:
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=offset_seconds)
    else:
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=45)

    req = DispatchRequest(
        trip_id=trip.id, driver_id=driver.id,
        status=DispatchStatus.PENDING, distance_km=1.0,
        expires_at=expires_at,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def run(coro):
    """Run an async coroutine synchronously inside a sync test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# TEST 1 — Pending request is marked EXPIRED by the worker
# ---------------------------------------------------------------------------
def test_pending_request_becomes_expired(db_session):
    patient = _make_patient(db_session, "t1")
    driver  = _make_driver(db_session, "t1")
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient, TripStatus.DRIVER_REQUESTED)
    req  = _make_dispatch_req(db_session, trip, driver, already_expired=True)

    run(expire_pending_requests(db_session))

    db_session.refresh(req)
    assert req.status == DispatchStatus.EXPIRED
    assert req.responded_at is not None


# ---------------------------------------------------------------------------
# TEST 2 — Expired request cannot be accepted afterwards
# ---------------------------------------------------------------------------
def test_expired_request_cannot_be_accepted(client, db_session):
    patient_user = _make_patient(db_session, "t2p")
    _make_driver(db_session, "t2d")
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient_user, TripStatus.DRIVER_REQUESTED)

    driver_obj = db_session.query(Driver).join(User).filter(
        User.email == "driver_t2d@test.com"
    ).first()
    req = _make_dispatch_req(db_session, trip, driver_obj, already_expired=True)

    run(expire_pending_requests(db_session))

    db_session.refresh(req)
    assert req.status == DispatchStatus.EXPIRED

    # Log in as driver and try to accept the now-expired request
    d_login = client.post("/api/v1/auth/login",
                          json={"email": "driver_t2d@test.com", "password": "pass"}).json()
    assert "access_token" in d_login, f"Login failed: {d_login}"

    res = client.post(f"/api/v1/driver/accept/{req.id}",
                      headers={"Authorization": f"Bearer {d_login['access_token']}"})
    assert res.status_code == 400
    assert "no longer pending" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 3 — Expiry triggers redispatch to the next eligible driver
# ---------------------------------------------------------------------------
def test_expiry_triggers_redispatch(db_session):
    patient = _make_patient(db_session, "t3")
    driver1 = _make_driver(db_session, "t3a")
    driver2 = _make_driver(db_session, "t3b")
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient, TripStatus.DRIVER_REQUESTED)
    req1 = _make_dispatch_req(db_session, trip, driver1, already_expired=True)

    run(expire_pending_requests(db_session))

    db_session.refresh(req1)
    db_session.refresh(trip)

    # Original request expired
    assert req1.status == DispatchStatus.EXPIRED

    # Trip should have a new PENDING dispatch request for driver2
    new_reqs = db_session.query(DispatchRequest).filter(
        DispatchRequest.trip_id == trip.id,
        DispatchRequest.status == DispatchStatus.PENDING,
    ).all()
    assert len(new_reqs) == 1, "Expected exactly one new PENDING dispatch request"
    assert new_reqs[0].driver_id == driver2.id, "New request must go to driver2"

    # Trip must still be DRIVER_REQUESTED, NOT ASSIGNED
    assert trip.status == TripStatus.DRIVER_REQUESTED


# ---------------------------------------------------------------------------
# TEST 4 — Next eligible driver sees the new request via pending endpoint
# ---------------------------------------------------------------------------
def test_next_driver_sees_new_request(client, db_session):
    patient_user = _make_patient(db_session, "t4p")
    driver1 = _make_driver(db_session, "t4a")  # gets expired request
    _make_driver(db_session, "t4b")             # should get new request
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient_user, TripStatus.DRIVER_REQUESTED)
    _make_dispatch_req(db_session, trip, driver1, already_expired=True)

    run(expire_pending_requests(db_session))

    # Driver2 should now see a pending request
    d2_login = client.post("/api/v1/auth/login",
                           json={"email": "driver_t4b@test.com", "password": "pass"}).json()
    assert "access_token" in d2_login, f"Driver2 login failed: {d2_login}"
    reqs = client.get("/api/v1/driver/requests/pending",
                      headers={"Authorization": f"Bearer {d2_login['access_token']}"}).json()
    assert len(reqs) == 1
    assert reqs[0]["trip_id"] == trip.id

    # Driver1 should no longer see anything pending
    d1_login = client.post("/api/v1/auth/login",
                           json={"email": "driver_t4a@test.com", "password": "pass"}).json()
    assert "access_token" in d1_login, f"Driver1 login failed: {d1_login}"
    reqs1 = client.get("/api/v1/driver/requests/pending",
                       headers={"Authorization": f"Bearer {d1_login['access_token']}"}).json()
    assert len(reqs1) == 0


# ---------------------------------------------------------------------------
# TEST 5 — Rejected request triggers next driver (now with locking)
# ---------------------------------------------------------------------------
def test_reject_triggers_next_driver(client, db_session):
    patient_user = _make_patient(db_session, "t5p")
    _make_driver(db_session, "t5a")
    _make_driver(db_session, "t5b")
    _make_hospital(db_session)

    p_login = client.post("/api/v1/auth/login",
                          json={"email": "patient_t5p@test.com", "password": "pass"}).json()
    assert "access_token" in p_login, f"Patient login failed: {p_login}"

    d1_login = client.post("/api/v1/auth/login",
                           json={"email": "driver_t5a@test.com", "password": "pass"}).json()
    assert "access_token" in d1_login, f"Driver1 login failed: {d1_login}"

    d2_login = client.post("/api/v1/auth/login",
                           json={"email": "driver_t5b@test.com", "password": "pass"}).json()
    assert "access_token" in d2_login, f"Driver2 login failed: {d2_login}"

    # Patient books
    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Test", "pickup_lat": 12.97, "pickup_lng": 77.59, "severity": "HIGH"
    }, headers={"Authorization": f"Bearer {p_login['access_token']}"})
    assert book.status_code == 200

    # Driver1 rejects
    reqs1 = client.get("/api/v1/driver/requests/pending",
                       headers={"Authorization": f"Bearer {d1_login['access_token']}"}).json()
    assert len(reqs1) == 1
    req_id = reqs1[0]["id"]

    rej = client.post(f"/api/v1/driver/reject/{req_id}",
                      headers={"Authorization": f"Bearer {d1_login['access_token']}"})
    assert rej.status_code == 200

    # Driver2 should now have the pending request
    reqs2 = client.get("/api/v1/driver/requests/pending",
                       headers={"Authorization": f"Bearer {d2_login['access_token']}"}).json()
    assert len(reqs2) == 1
    assert reqs2[0]["trip_id"] == book.json()["trip_id"]


# ---------------------------------------------------------------------------
# TEST 6 — No eligible drivers → trip becomes FAILED
# ---------------------------------------------------------------------------
def test_no_eligible_drivers_results_in_failed(db_session):
    patient = _make_patient(db_session, "t6")
    driver  = _make_driver(db_session, "t6a")
    # No second driver — only one, and they'll be excluded after expiry
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient, TripStatus.DRIVER_REQUESTED)
    _make_dispatch_req(db_session, trip, driver, already_expired=True)

    run(expire_pending_requests(db_session))

    db_session.refresh(trip)
    assert trip.status == TripStatus.FAILED


# ---------------------------------------------------------------------------
# TEST 7 — Expired driver/ambulance NOT reserved → available for other trips
# ---------------------------------------------------------------------------
def test_expired_driver_eligible_for_other_trip(db_session):
    """
    No pre-reservation happens, so after expiry the driver can be dispatched to
    a brand-new different trip immediately.
    """
    patient1 = _make_patient(db_session, "t7p1")
    patient2 = _make_patient(db_session, "t7p2")
    driver   = _make_driver(db_session, "t7d")
    _make_hospital(db_session)

    # Trip1 gets an expired request for driver
    trip1 = _make_trip(db_session, patient1, TripStatus.DRIVER_REQUESTED)
    req1  = _make_dispatch_req(db_session, trip1, driver, already_expired=True)

    run(expire_pending_requests(db_session))

    db_session.refresh(req1)
    assert req1.status == DispatchStatus.EXPIRED

    # Trip2 is a brand-new trip — driver must be eligible again
    trip2 = _make_trip(db_session, patient2, TripStatus.SEARCHING)
    dispatched = run(dispatch_next_driver(db_session, trip2))
    assert dispatched is True, "Driver should be eligible for a second trip after first expired"

    new_req = db_session.query(DispatchRequest).filter(
        DispatchRequest.trip_id == trip2.id,
        DispatchRequest.status == DispatchStatus.PENDING,
    ).first()
    assert new_req is not None
    assert new_req.driver_id == driver.id


# ---------------------------------------------------------------------------
# TEST 8 — ACCEPT wins the race → expiry worker skips the request
# ---------------------------------------------------------------------------
def test_accept_wins_race_expiry_skips(client, db_session):
    patient_user = _make_patient(db_session, "t8p")
    _make_driver(db_session, "t8d")
    _make_hospital(db_session)

    p_login = client.post("/api/v1/auth/login",
                          json={"email": "patient_t8p@test.com", "password": "pass"}).json()
    assert "access_token" in p_login, f"Patient login failed: {p_login}"

    d_login = client.post("/api/v1/auth/login",
                          json={"email": "driver_t8d@test.com", "password": "pass"}).json()
    assert "access_token" in d_login, f"Driver login failed: {d_login}"

    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Race Test", "pickup_lat": 12.97, "pickup_lng": 77.59, "severity": "HIGH"
    }, headers={"Authorization": f"Bearer {p_login['access_token']}"})
    trip_id = book.json()["trip_id"]

    reqs = client.get("/api/v1/driver/requests/pending",
                      headers={"Authorization": f"Bearer {d_login['access_token']}"}).json()
    req_id = reqs[0]["id"]

    # Driver accepts FIRST
    acc = client.post(f"/api/v1/driver/accept/{req_id}",
                      headers={"Authorization": f"Bearer {d_login['access_token']}"})
    assert acc.status_code == 200

    # Now manually backdate the request so expiry worker would normally process it
    req_obj = db_session.query(DispatchRequest).filter(DispatchRequest.id == req_id).first()
    req_obj.expires_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
    db_session.commit()

    # Run the expiry worker — it must NOT touch the already-ACCEPTED request
    run(expire_pending_requests(db_session))

    db_session.refresh(req_obj)
    # Must still be ACCEPTED, not EXPIRED
    assert req_obj.status == DispatchStatus.ACCEPTED

    # Trip must still be ASSIGNED
    trip = db_session.query(Trip).filter(Trip.id == trip_id).first()
    assert trip.status == TripStatus.ASSIGNED


# ---------------------------------------------------------------------------
# TEST 9 — Already ACCEPTED request cannot be expired by worker
# ---------------------------------------------------------------------------
def test_accepted_request_not_expired_by_worker(db_session):
    patient = _make_patient(db_session, "t9")
    driver  = _make_driver(db_session, "t9d")
    _make_hospital(db_session)
    trip = _make_trip(db_session, patient, TripStatus.ASSIGNED)  # already assigned

    # Manually create an ACCEPTED request with a past expires_at
    req = DispatchRequest(
        trip_id=trip.id, driver_id=driver.id,
        status=DispatchStatus.ACCEPTED, distance_km=1.0,
        expires_at=datetime.datetime.utcnow() - datetime.timedelta(seconds=5),
        responded_at=datetime.datetime.utcnow(),
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    run(expire_pending_requests(db_session))

    db_session.refresh(req)
    # Must remain ACCEPTED — worker only processes PENDING
    assert req.status == DispatchStatus.ACCEPTED


# ---------------------------------------------------------------------------
# TEST 10 — Patient REST trip status = FAILED after no-driver expiry
# ---------------------------------------------------------------------------
def test_patient_trip_status_after_failed_dispatch(client, db_session):
    """
    After expiry with no eligible drivers the trip must be FAILED and
    GET /patient/trip/{id} must reflect that.
    """
    patient_user = _make_patient(db_session, "t10p")
    _make_driver(db_session, "t10d")  # only one driver — will be excluded after expiry
    _make_hospital(db_session)

    p_login = client.post("/api/v1/auth/login",
                          json={"email": "patient_t10p@test.com", "password": "pass"}).json()
    assert "access_token" in p_login, f"Patient login failed: {p_login}"

    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Notify Test", "pickup_lat": 12.97, "pickup_lng": 77.59, "severity": "HIGH"
    }, headers={"Authorization": f"Bearer {p_login['access_token']}"})
    assert book.status_code == 200
    trip_id = book.json()["trip_id"]

    # Back-date the pending request so expiry fires
    req_obj = db_session.query(DispatchRequest).filter(
        DispatchRequest.trip_id == trip_id,
        DispatchRequest.status == DispatchStatus.PENDING,
    ).first()
    if req_obj:
        req_obj.expires_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
        db_session.commit()

    # Only one driver exists → after expiry no eligible drivers remain → FAILED
    run(expire_pending_requests(db_session))

    trip_res = client.get(f"/api/v1/patient/trip/{trip_id}",
                          headers={"Authorization": f"Bearer {p_login['access_token']}"})
    assert trip_res.status_code == 200
    assert trip_res.json()["status"] == TripStatus.FAILED
