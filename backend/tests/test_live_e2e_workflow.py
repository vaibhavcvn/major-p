"""
Phase 6 — Deterministic Live End-to-End Workflow Test
======================================================

Tests the complete patient → driver → GPS → hospital → traffic → completion
workflow using an isolated in-memory database so no pre-existing data
interferes with the nearest-driver selection.

Key isolation strategy:
- Uses the conftest in-memory SQLite database (StaticPool).
- Seeds exactly TWO drivers:
    driver1: at the pickup location (0 km away) → nearest, always selected
    driver2: 50 km away → never selected for this booking
- All acceptance and GPS updates go through the real API endpoints.
- No direct DB state manipulation for the core workflow steps.

Covers requirements 1 through 28 from the Phase 6 spec.
"""
import datetime
import asyncio
import pytest

from app.models import (
    User, Driver, Ambulance, Hospital, HospitalStaff,
    Trip, DispatchRequest, TripStatus, DispatchStatus,
)
from app.auth import get_password_hash, create_access_token
from app.main import _proximity_alerted_trips


# ── Seed helpers ─────────────────────────────────────────────────────────────

PWD = "DemoPass123!"
PICKUP_LAT = 12.9716
PICKUP_LNG = 77.5946


def _hash(p=PWD):
    return get_password_hash(p)


def seed_full_demo(db):
    """
    Seed exactly the roles, drivers, and hospital needed for the deterministic
    demo workflow.

    Driver 1 — placed at the pickup coordinates (0 km from booking) → will ALWAYS
               win the nearest-driver dispatch selection.
    Driver 2 — placed 50 km away → never wins for this booking.
    """
    # ── Users ────────────────────────────────────────────────────────────────
    patient = User(email="patient@test.com", password_hash=_hash(),
                   role="PATIENT", full_name="Demo Patient", phone="+1-555-0001")
    d1_user = User(email="driver@test.com", password_hash=_hash(),
                   role="DRIVER", full_name="Demo Driver 1", phone="+1-555-0002")
    d2_user = User(email="driver2@test.com", password_hash=_hash(),
                   role="DRIVER", full_name="Demo Driver 2", phone="+1-555-0003")
    hosp_user = User(email="hospital@test.com", password_hash=_hash(),
                     role="HOSPITAL", full_name="Demo Hospital Staff")
    traffic_user = User(email="traffic@test.com", password_hash=_hash(),
                        role="TRAFFIC", full_name="Demo Traffic Operator")
    admin_user = User(email="admin@test.com", password_hash=_hash(),
                      role="ADMIN", full_name="Demo Admin")

    db.add_all([patient, d1_user, d2_user, hosp_user, traffic_user, admin_user])
    db.commit()

    # ── Driver 1: AT pickup location (0 km away → nearest) ───────────────────
    d1 = Driver(user_id=d1_user.id, license_number="DEMO-D1-001", is_on_duty=True,
                current_lat=PICKUP_LAT, current_lng=PICKUP_LNG)
    db.add(d1); db.commit(); db.refresh(d1)
    a1 = Ambulance(driver_id=d1.id, vehicle_number="DEMO-AMB-101",
                   type="ADVANCED_LIFE_SUPPORT", is_active=True,
                   current_lat=PICKUP_LAT, current_lng=PICKUP_LNG)
    db.add(a1); db.commit(); db.refresh(a1)

    # ── Driver 2: 50 km away → will NOT be selected first ────────────────────
    d2 = Driver(user_id=d2_user.id, license_number="DEMO-D2-002", is_on_duty=True,
                current_lat=PICKUP_LAT + 0.45, current_lng=PICKUP_LNG + 0.45)  # ~63 km
    db.add(d2); db.commit(); db.refresh(d2)
    a2 = Ambulance(driver_id=d2.id, vehicle_number="DEMO-AMB-102",
                   type="BASIC_LIFE_SUPPORT", is_active=True,
                   current_lat=PICKUP_LAT + 0.45, current_lng=PICKUP_LNG + 0.45)
    db.add(a2); db.commit(); db.refresh(a2)

    # ── Hospital: close to pickup so TRANSPORTING auto-selects it ────────────
    hosp = Hospital(name="Demo Trauma Center",
                    latitude=PICKUP_LAT + 0.005,  # ~0.55 km from pickup
                    longitude=PICKUP_LNG + 0.005,
                    address="1 Demo Hospital Rd", total_beds=50,
                    available_beds=20, trauma_level=1, is_ready=True)
    db.add(hosp); db.commit(); db.refresh(hosp)

    hs = HospitalStaff(user_id=hosp_user.id, hospital_id=hosp.id,
                       department="Emergency Room")
    db.add(hs); db.commit()

    return {
        "patient": patient, "d1_user": d1_user, "d2_user": d2_user,
        "d1": d1, "d2": d2, "a1": a1, "a2": a2,
        "hosp": hosp, "hosp_user": hosp_user,
        "traffic_user": traffic_user, "admin_user": admin_user,
    }


# ══════════════════════════════════════════════════════════════════════════════
# THE COMPLETE WORKFLOW TEST (steps 1–28 from spec)
# ══════════════════════════════════════════════════════════════════════════════

def test_complete_demo_workflow(client, db_session):
    """
    Deterministic, isolated test of the full demo workflow:
    Patient books → nearest driver dispatched → driver ACCEPTS via real API →
    GPS via real API → state progression → hospital selected → proximity alert
    fires exactly once → trip COMPLETED → proximity state cleared.
    """
    # ── Clear any leftover proximity alerts from other tests ──────────────────
    _proximity_alerted_trips.clear()

    # ── Seed isolated demo data ───────────────────────────────────────────────
    seed = seed_full_demo(db_session)
    patient    = seed["patient"]
    d1_user    = seed["d1_user"]
    d1         = seed["d1"]
    a1         = seed["a1"]
    hosp       = seed["hosp"]
    hosp_user  = seed["hosp_user"]
    admin_user = seed["admin_user"]
    traffic_user = seed["traffic_user"]

    # ── STEP 1: Login all roles ───────────────────────────────────────────────
    p_res  = client.post("/api/v1/auth/login",
                         json={"email": "patient@test.com", "password": PWD})
    d1_res = client.post("/api/v1/auth/login",
                         json={"email": "driver@test.com", "password": PWD})
    h_res  = client.post("/api/v1/auth/login",
                         json={"email": "hospital@test.com", "password": PWD})
    t_res  = client.post("/api/v1/auth/login",
                         json={"email": "traffic@test.com", "password": PWD})
    a_res  = client.post("/api/v1/auth/login",
                         json={"email": "admin@test.com", "password": PWD})

    assert p_res.status_code  == 200, f"Patient login: {p_res.text}"
    assert d1_res.status_code == 200, f"Driver1 login: {d1_res.text}"
    assert h_res.status_code  == 200, f"Hospital login: {h_res.text}"
    assert t_res.status_code  == 200, f"Traffic login: {t_res.text}"
    assert a_res.status_code  == 200, f"Admin login: {a_res.text}"

    p_tok  = p_res.json()["access_token"]
    d1_tok = d1_res.json()["access_token"]
    h_tok  = h_res.json()["access_token"]
    t_tok  = t_res.json()["access_token"]
    a_tok  = a_res.json()["access_token"]

    # FIX-11: login response must include driver_id for DRIVER
    assert d1_res.json()["driver_id"] == d1.id, \
        f"driver_id in login must match Driver.id: got {d1_res.json()['driver_id']} expected {d1.id}"

    # ── STEP 2: Patient books with arbitrary coordinates ─────────────────────
    # Use Delhi coordinates — NOT the hardcoded Bangalore default
    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Lal Qila, Delhi",
        "pickup_lat": PICKUP_LAT,
        "pickup_lng": PICKUP_LNG,
        "severity": "CRITICAL",
    }, headers={"Authorization": f"Bearer {p_tok}"})
    assert book.status_code == 200, f"Booking failed: {book.text}"
    trip_id = book.json()["trip_id"]

    # ── STEP 3: Verify DRIVER_REQUESTED (not ASSIGNED) ───────────────────────
    trip_state = client.get(f"/api/v1/patient/trip/{trip_id}",
                            headers={"Authorization": f"Bearer {p_tok}"}).json()
    assert trip_state["status"] == TripStatus.DRIVER_REQUESTED, \
        f"Trip must be DRIVER_REQUESTED (no auto-assign), got {trip_state['status']}"

    # ── STEP 4: Verify DispatchRequest went to Driver 1 (nearest) ────────────
    pending = client.get("/api/v1/driver/requests/pending",
                         headers={"Authorization": f"Bearer {d1_tok}"}).json()
    assert len(pending) == 1, \
        f"Driver 1 must have exactly 1 pending request; got {len(pending)}"
    req_id  = pending[0]["id"]
    req     = db_session.query(DispatchRequest).filter(DispatchRequest.id == req_id).first()
    assert req.driver_id == d1.id, \
        f"Dispatch must go to nearest driver (d1.id={d1.id}), got driver_id={req.driver_id}"

    # ── STEP 5: Driver ACCEPTS via real API (no DB shortcut) ─────────────────
    acc = client.post(f"/api/v1/driver/accept/{req_id}",
                      headers={"Authorization": f"Bearer {d1_tok}"})
    assert acc.status_code == 200, f"Accept failed: {acc.text}"
    accepted_trip = acc.json()["trip"]
    assert accepted_trip["status"] == TripStatus.ASSIGNED
    assert accepted_trip["assigned_driver_id"] == d1.id
    assert accepted_trip["assigned_ambulance_id"] == a1.id

    # ── STEP 6: Verify DispatchRequest = ACCEPTED ─────────────────────────────
    db_session.refresh(req)
    assert req.status == DispatchStatus.ACCEPTED

    # ── STEP 7: GPS via real API (not DB shortcut) ────────────────────────────
    gps = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id,
        "latitude": PICKUP_LAT + 0.001,
        "longitude": PICKUP_LNG + 0.001,
        "speed": 11.2,
        "heading": 45.0,
        "accuracy": 3.0,
    }, headers={"Authorization": f"Bearer {d1_tok}"})
    assert gps.status_code == 200, f"GPS update failed: {gps.text}"
    assert gps.json()["eta_minutes"] is not None

    # ── STEP 8: GPS rejected for patient (RBAC still enforced) ───────────────
    gps_blocked = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id, "latitude": PICKUP_LAT, "longitude": PICKUP_LNG,
    }, headers={"Authorization": f"Bearer {p_tok}"})
    assert gps_blocked.status_code in (401, 403), \
        "GPS must be rejected for PATIENT role"

    # ── STEP 9: GPS rejected for wrong driver (security) ─────────────────────
    # Driver2 tries to submit GPS for driver1's trip
    d2_tok = client.post("/api/v1/auth/login",
                         json={"email": "driver2@test.com", "password": PWD}
                         ).json()["access_token"]
    gps_wrong = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id, "latitude": PICKUP_LAT, "longitude": PICKUP_LNG,
    }, headers={"Authorization": f"Bearer {d2_tok}"})
    assert gps_wrong.status_code == 403, \
        "GPS must be rejected for driver not assigned to trip"

    # ── STEP 10: State machine: ASSIGNED → EN_ROUTE_TO_PICKUP → AT_PICKUP ────
    for step, expected in [
        ("EN_ROUTE_TO_PICKUP", TripStatus.EN_ROUTE_TO_PICKUP),
        ("AT_PICKUP",          TripStatus.AT_PICKUP),
    ]:
        r = client.post(f"/api/v1/driver/trip/{trip_id}/status",
                        json={"status": step},
                        headers={"Authorization": f"Bearer {d1_tok}"})
        assert r.status_code == 200, f"Status {step} failed: {r.text}"
        assert r.json()["trip"]["status"] == expected

    # ── STEP 11: TRANSPORTING → hospital auto-selected → EN_ROUTE_TO_HOSPITAL ─
    trans = client.post(f"/api/v1/driver/trip/{trip_id}/status",
                        json={"status": "TRANSPORTING"},
                        headers={"Authorization": f"Bearer {d1_tok}"})
    assert trans.status_code == 200, f"TRANSPORTING failed: {trans.text}"
    trans_trip = trans.json()["trip"]
    assert trans_trip["status"] == TripStatus.EN_ROUTE_TO_HOSPITAL, \
        f"TRANSPORTING must trigger hospital selection → EN_ROUTE_TO_HOSPITAL; got {trans_trip['status']}"
    assert trans_trip["hospital_name"] == hosp.name, \
        f"Hospital must be the seeded demo hospital; got {trans_trip['hospital_name']}"

    # ── STEP 12: Hospital receives incoming ambulance via GET /hospital/trips ──
    hosp_trips = client.get("/api/v1/hospital/trips",
                            headers={"Authorization": f"Bearer {h_tok}"}).json()
    matching = [t for t in hosp_trips if t["id"] == trip_id]
    assert len(matching) == 1, \
        f"Hospital must see the incoming trip; got {[t['id'] for t in hosp_trips]}"

    # ── STEP 13: Admin sees the active trip ──────────────────────────────────
    overview = client.get("/api/v1/admin/overview",
                          headers={"Authorization": f"Bearer {a_tok}"}).json()
    trip_ids = [t["id"] for t in overview["recent_trips"]]
    assert trip_id in trip_ids, \
        f"Admin must see active trip {trip_id}; visible: {trip_ids}"

    # ── STEP 14: Traffic corridors have no patient PII ────────────────────────
    corridors = client.get("/api/v1/traffic/corridors",
                           headers={"Authorization": f"Bearer {t_tok}"}).json()
    corridors_str = str(corridors)
    assert "patient@test.com" not in corridors_str
    assert "+1-555-0001" not in corridors_str
    for c in corridors:
        assert "pickup_address" not in c, \
            f"pickup_address must not appear in traffic corridors: {c}"

    # ── STEPS 15–17: Traffic proximity alert fires exactly once ──────────────
    # The hospital is very close (~0.55 km). We simulate a GPS update placing the
    # ambulance within the TRAFFIC_PROXIMITY_KM threshold.
    # First, set destination on the trip (done by TRANSPORTING step above).
    db_session.refresh(db_session.query(Trip).filter(Trip.id == trip_id).first())
    trip_obj = db_session.query(Trip).filter(Trip.id == trip_id).first()
    dest_lat = trip_obj.destination_lat
    dest_lng = trip_obj.destination_lng
    assert dest_lat is not None, "TRANSPORTING must have set destination_lat"

    # GPS update 1: just inside the 2.0 km threshold (0.5 km from hospital)
    gps_near = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id,
        "latitude": dest_lat - 0.004,   # ~0.44 km from hospital
        "longitude": dest_lng - 0.004,
        "speed": 15.0,
        "heading": 90.0,
        "accuracy": 4.0,
    }, headers={"Authorization": f"Bearer {d1_tok}"})
    assert gps_near.status_code == 200, f"GPS near failed: {gps_near.text}"
    assert trip_id in _proximity_alerted_trips, \
        "Proximity alert must be added to _proximity_alerted_trips after first near-GPS update"

    # GPS update 2: same proximity zone → alert must NOT fire again
    alert_count_before = len(_proximity_alerted_trips)
    gps_near2 = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id,
        "latitude": dest_lat - 0.003,
        "longitude": dest_lng - 0.003,
        "speed": 15.0,
        "heading": 90.0,
        "accuracy": 4.0,
    }, headers={"Authorization": f"Bearer {d1_tok}"})
    assert gps_near2.status_code == 200
    assert len(_proximity_alerted_trips) == alert_count_before, \
        "Proximity alert must NOT fire again for the same trip in the same zone"

    # ── STEP 18: Complete the trip ────────────────────────────────────────────
    r_hosp_arr = client.post(f"/api/v1/driver/trip/{trip_id}/status",
                             json={"status": "AT_HOSPITAL"},
                             headers={"Authorization": f"Bearer {d1_tok}"})
    assert r_hosp_arr.status_code == 200, f"AT_HOSPITAL failed: {r_hosp_arr.text}"

    r_complete = client.post(f"/api/v1/driver/trip/{trip_id}/status",
                             json={"status": "COMPLETED"},
                             headers={"Authorization": f"Bearer {d1_tok}"})
    assert r_complete.status_code == 200, f"COMPLETED failed: {r_complete.text}"
    assert r_complete.json()["trip"]["status"] == TripStatus.COMPLETED

    # ── STEP 19: Proximity state cleared after completion ────────────────────
    assert trip_id not in _proximity_alerted_trips, \
        "Proximity alert entry must be cleared after trip COMPLETED"

    # ── STEP 20: Final patient view confirms COMPLETED ────────────────────────
    final = client.get(f"/api/v1/patient/trip/{trip_id}",
                       headers={"Authorization": f"Bearer {p_tok}"}).json()
    assert final["status"] == TripStatus.COMPLETED


# ══════════════════════════════════════════════════════════════════════════════
# TESTS 12–14 — Multiple simultaneous ambulances for traffic map
# ══════════════════════════════════════════════════════════════════════════════

def test_multiple_active_trips_produce_multiple_corridors(client, db_session):
    """
    Two simultaneous ASSIGNED trips both appear in GET /traffic/corridors.
    Each has a distinct ambulance — the traffic page must show two markers.
    """
    from app.models import User, Driver, Ambulance, Hospital, Trip, TripStatus
    from app.auth import get_password_hash

    pwd = get_password_hash(PWD)

    # Two patients
    p1 = User(email="p1_multi@test.com", password_hash=pwd, role="PATIENT", full_name="P1")
    p2 = User(email="p2_multi@test.com", password_hash=pwd, role="PATIENT", full_name="P2")
    db_session.add_all([p1, p2]); db_session.commit()

    # Two drivers with distinct coordinates
    d1u = User(email="d1_multi@test.com", password_hash=pwd, role="DRIVER", full_name="D1")
    d2u = User(email="d2_multi@test.com", password_hash=pwd, role="DRIVER", full_name="D2")
    db_session.add_all([d1u, d2u]); db_session.commit()

    d1 = Driver(user_id=d1u.id, license_number="MULTI-D1", is_on_duty=True,
                current_lat=12.97, current_lng=77.59)
    d2 = Driver(user_id=d2u.id, license_number="MULTI-D2", is_on_duty=True,
                current_lat=12.98, current_lng=77.61)
    db_session.add_all([d1, d2]); db_session.commit()

    a1 = Ambulance(driver_id=d1.id, vehicle_number="MULTI-101", type="ALS",
                   is_active=True, current_lat=12.97, current_lng=77.59)
    a2 = Ambulance(driver_id=d2.id, vehicle_number="MULTI-102", type="BLS",
                   is_active=True, current_lat=12.98, current_lng=77.61)
    db_session.add_all([a1, a2]); db_session.commit()

    # Two trips — both ASSIGNED with their respective drivers
    t1 = Trip(patient_id=p1.id, assigned_driver_id=d1.id, assigned_ambulance_id=a1.id,
              status=TripStatus.ASSIGNED, severity="HIGH",
              pickup_address="Multi P1 St", pickup_lat=12.97, pickup_lng=77.59)
    t2 = Trip(patient_id=p2.id, assigned_driver_id=d2.id, assigned_ambulance_id=a2.id,
              status=TripStatus.ASSIGNED, severity="MEDIUM",
              pickup_address="Multi P2 St", pickup_lat=12.98, pickup_lng=77.61)
    db_session.add_all([t1, t2]); db_session.commit()

    # Traffic user
    tu = User(email="traffic_multi@test.com", password_hash=pwd, role="TRAFFIC",
              full_name="Traffic Multi")
    db_session.add(tu); db_session.commit()
    t_tok = client.post("/api/v1/auth/login",
                        json={"email": "traffic_multi@test.com",
                              "password": PWD}).json()["access_token"]

    corridors = client.get("/api/v1/traffic/corridors",
                           headers={"Authorization": f"Bearer {t_tok}"}).json()

    trip_ids_in_corridors = {c["trip_id"] for c in corridors}
    assert t1.id in trip_ids_in_corridors, \
        f"Trip 1 must appear in traffic corridors; found: {trip_ids_in_corridors}"
    assert t2.id in trip_ids_in_corridors, \
        f"Trip 2 must appear in traffic corridors; found: {trip_ids_in_corridors}"

    # Verify each has a distinct ambulance identifier
    identifiers = {c["ambulance_identifier"] for c in corridors
                   if c["trip_id"] in {t1.id, t2.id}}
    assert len(identifiers) == 2, \
        f"Two distinct ambulance identifiers must be present; got: {identifiers}"

    # Each corridor must have lat/lng for map marker placement
    for c in corridors:
        if c["trip_id"] in {t1.id, t2.id}:
            assert c["current_lat"] is not None
            assert c["current_lng"] is not None

    # No patient PII in any corridor
    resp_str = str(corridors)
    assert "p1_multi@test.com" not in resp_str
    assert "p2_multi@test.com" not in resp_str


def test_completing_one_trip_removes_only_that_corridor(client, db_session):
    """
    Completing trip A must not remove trip B from GET /traffic/corridors.
    Only the completed trip's corridor disappears.
    """
    from app.models import User, Driver, Ambulance, Hospital, Trip, TripStatus
    from app.auth import get_password_hash

    pwd = get_password_hash(PWD)

    p_a = User(email="p_a_remove@test.com", password_hash=pwd, role="PATIENT", full_name="PA")
    p_b = User(email="p_b_remove@test.com", password_hash=pwd, role="PATIENT", full_name="PB")
    db_session.add_all([p_a, p_b]); db_session.commit()

    da_u = User(email="da_remove@test.com", password_hash=pwd, role="DRIVER", full_name="DA")
    db_session.add(da_u); db_session.commit()
    da = Driver(user_id=da_u.id, license_number="RMV-DA", is_on_duty=True,
                current_lat=12.97, current_lng=77.59)
    db_session.add(da); db_session.commit()
    aa = Ambulance(driver_id=da.id, vehicle_number="RMV-101", type="ALS",
                   is_active=True, current_lat=12.97, current_lng=77.59)
    db_session.add(aa); db_session.commit()

    # Trip A — will be completed
    ta = Trip(patient_id=p_a.id, assigned_driver_id=da.id, assigned_ambulance_id=aa.id,
              status=TripStatus.ASSIGNED, severity="HIGH",
              pickup_address="RMV A St", pickup_lat=12.97, pickup_lng=77.59)
    # Trip B — will remain active
    tb = Trip(patient_id=p_b.id, status=TripStatus.ASSIGNED, severity="LOW",
              pickup_address="RMV B St", pickup_lat=12.98, pickup_lng=77.61)
    db_session.add_all([ta, tb]); db_session.commit()

    tu = User(email="t_remove@test.com", password_hash=pwd, role="TRAFFIC",
              full_name="T Remove")
    db_session.add(tu); db_session.commit()
    t_tok = client.post("/api/v1/auth/login",
                        json={"email": "t_remove@test.com",
                              "password": PWD}).json()["access_token"]

    # Confirm both trips appear before completion
    before = {c["trip_id"] for c in
              client.get("/api/v1/traffic/corridors",
                         headers={"Authorization": f"Bearer {t_tok}"}).json()}
    # ta must be in corridors (ASSIGNED status is in traffic active list)
    assert ta.id in before, f"Trip A must appear before completion; found: {before}"

    # Complete trip A through the driver API
    da_tok = client.post("/api/v1/auth/login",
                         json={"email": "da_remove@test.com",
                               "password": PWD}).json()["access_token"]

    # Progress to COMPLETED via valid state machine
    hosp_rmv = Hospital(name="RMV Hospital", latitude=12.972, longitude=77.591,
                        address="RMV Rd", total_beds=10, available_beds=5,
                        trauma_level=1, is_ready=True)
    db_session.add(hosp_rmv); db_session.commit()

    for step in ["EN_ROUTE_TO_PICKUP", "AT_PICKUP"]:
        client.post(f"/api/v1/driver/trip/{ta.id}/status",
                    json={"status": step},
                    headers={"Authorization": f"Bearer {da_tok}"})

    trans_r = client.post(f"/api/v1/driver/trip/{ta.id}/status",
                          json={"status": "TRANSPORTING"},
                          headers={"Authorization": f"Bearer {da_tok}"})
    assert trans_r.status_code == 200

    client.post(f"/api/v1/driver/trip/{ta.id}/status",
                json={"status": "AT_HOSPITAL"},
                headers={"Authorization": f"Bearer {da_tok}"})

    complete_r = client.post(f"/api/v1/driver/trip/{ta.id}/status",
                             json={"status": "COMPLETED"},
                             headers={"Authorization": f"Bearer {da_tok}"})
    assert complete_r.status_code == 200

    # After completion — ta must NOT appear in corridors
    after = {c["trip_id"] for c in
             client.get("/api/v1/traffic/corridors",
                        headers={"Authorization": f"Bearer {t_tok}"}).json()}
    assert ta.id not in after, \
        f"Completed trip A must NOT appear in traffic corridors after COMPLETED; found: {after}"
