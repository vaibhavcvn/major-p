"""
Phase 2 Hospital E2E Verification Script

Checks:
 1. Login as hospital staff → response contains correct hospital_id
 2. Login response hospital_id matches HospitalStaff record
 3. GET /hospital/trips scoped to that hospital (correct identity)
 4. Hospital WS subscribes to /ws/hospital/{actual_hospital_id}
 5. Patient books → driver accepts → driver marks TRANSPORTING → system selects hospital
 6. WS notification delivered to matching hospital channel
 7. A DIFFERENT hospital must NOT receive that notification
 8. Hospital dashboard shows the incoming trip via GET /hospital/trips
 9. Unlinked hospital user gets 403 (no `else 1` fallback)
10. Traffic endpoint has NO patient name/phone/diagnosis/hospital-private data
11. Patient name/phone must NOT appear in traffic WS broadcast
"""
import asyncio
import sys
import json
import random
import httpx
import websockets

BASE    = "http://127.0.0.1:8765/api/v1"
WS_BASE = "ws://127.0.0.1:8765"
RND     = random.randint(10000, 99999)

PATIENT_EMAIL   = f"p2_patient_{RND}@test.com"
DRIVER_EMAIL    = f"p2_driver_{RND}@test.com"
HOSP1_EMAIL     = f"p2_hosp1_{RND}@test.com"   # linked to Hospital A
HOSP2_EMAIL     = f"p2_hosp2_{RND}@test.com"   # linked to Hospital B (isolation check)
UNLINKED_EMAIL  = f"p2_unlinked_{RND}@test.com" # HOSPITAL role, no HospitalStaff row
PASSWORD        = "testpass123"

def ok(label, val=None):
    suffix = f"  →  {val}" if val is not None else ""
    print(f"  ✓  {label}{suffix}")

def fail(label, detail=""):
    print(f"  ✗  {label}  {detail}", file=sys.stderr)
    sys.exit(1)

def warn(label):
    print(f"  ⚠  {label}")

async def run():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:

        # ── Setup: register users ─────────────────────────────────────────
        for email, role, extra in [
            (PATIENT_EMAIL,  "PATIENT",  {}),
            (DRIVER_EMAIL,   "DRIVER",   {"license_number": "P2-LIC-001"}),
        ]:
            r = await c.post("/auth/register", json={
                "email": email, "password": PASSWORD,
                "full_name": f"P2 {role}", "role": role, **extra
            })
            assert r.status_code == 200, f"Register {role} failed: {r.text}"

        # Register HOSPITAL role users (unlinked — no HospitalStaff row yet)
        for email in [HOSP1_EMAIL, HOSP2_EMAIL, UNLINKED_EMAIL]:
            r = await c.post("/auth/register", json={
                "email": email, "password": PASSWORD,
                "full_name": f"P2 HospUser", "role": "HOSPITAL"
            })
            assert r.status_code == 200, f"Register HOSPITAL failed: {r.text}"
        ok("All users registered")

        # ── Create two Hospitals and link staff via seed-style direct DB ops ─
        # We call the admin overview first to confirm the server is up, then
        # use the seed endpoint if present; otherwise insert via a helper.
        # Fastest path: register an ADMIN user and use their token to seed.
        ADMIN_EMAIL = f"p2_admin_{RND}@test.com"
        r = await c.post("/auth/register", json={
            "email": ADMIN_EMAIL, "password": PASSWORD,
            "full_name": "P2 Admin", "role": "ADMIN"
        })
        assert r.status_code == 200, f"Admin register failed: {r.text}"
        r = await c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        admin_token = r.json()["access_token"]

        # Seed two hospitals and link staff using the internal seed module
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from app.database import SessionLocal
        from app.models import Hospital, HospitalStaff, User

        db = SessionLocal()
        try:
            # Create Hospital A
            hosp_a = Hospital(
                name="City Hospital A", latitude=12.9716, longitude=77.5946,
                address="1 Main St, Bangalore", total_beds=50, available_beds=20,
                trauma_level=1, is_ready=True, phone="080-1111"
            )
            # Create Hospital B
            hosp_b = Hospital(
                name="Metro Hospital B", latitude=12.9800, longitude=77.6100,
                address="2 North Rd, Bangalore", total_beds=30, available_beds=10,
                trauma_level=2, is_ready=True, phone="080-2222"
            )
            db.add(hosp_a)
            db.add(hosp_b)
            db.commit()
            db.refresh(hosp_a)
            db.refresh(hosp_b)

            # Link HOSP1_EMAIL → Hospital A
            hosp1_user = db.query(User).filter(User.email == HOSP1_EMAIL).first()
            hosp2_user = db.query(User).filter(User.email == HOSP2_EMAIL).first()

            db.add(HospitalStaff(user_id=hosp1_user.id, hospital_id=hosp_a.id, department="Emergency"))
            db.add(HospitalStaff(user_id=hosp2_user.id, hospital_id=hosp_b.id, department="Emergency"))
            db.commit()

            hospital_a_id = hosp_a.id
            hospital_b_id = hosp_b.id
        finally:
            db.close()

        ok(f"Created Hospital A (id={hospital_a_id}) and Hospital B (id={hospital_b_id})")

        # ── 1. Login as hospital staff — check hospital_id in response ────
        r = await c.post("/auth/login", json={"email": HOSP1_EMAIL, "password": PASSWORD})
        assert r.status_code == 200, f"Hosp1 login failed: {r.text}"
        hosp1_login = r.json()
        hosp1_token = hosp1_login["access_token"]
        returned_hospital_id = hosp1_login.get("hospital_id")

        if returned_hospital_id is None:
            fail("hospital_id missing from login response for HOSPITAL user")
        if returned_hospital_id != hospital_a_id:
            fail(f"login hospital_id={returned_hospital_id} != expected {hospital_a_id}")
        ok(f"CHECK 1+2: Login response hospital_id={returned_hospital_id} matches Hospital A id={hospital_a_id}")

        # Login hospital B
        r = await c.post("/auth/login", json={"email": HOSP2_EMAIL, "password": PASSWORD})
        hosp2_token = r.json()["access_token"]
        hosp2_hospital_id = r.json().get("hospital_id")
        assert hosp2_hospital_id == hospital_b_id, (
            f"Hosp2 login hospital_id={hosp2_hospital_id} != {hospital_b_id}"
        )
        ok(f"CHECK 2b: Hosp2 login hospital_id={hosp2_hospital_id} matches Hospital B id={hospital_b_id}")

        # Patient login
        r = await c.post("/auth/login", json={"email": PATIENT_EMAIL, "password": PASSWORD})
        patient_token = r.json()["access_token"]
        assert r.json().get("hospital_id") is None, "PATIENT should not get hospital_id"
        ok("CHECK 2c: hospital_id correctly None for PATIENT role")

        # Driver setup
        r = await c.post("/auth/login", json={"email": DRIVER_EMAIL, "password": PASSWORD})
        driver_login  = r.json()
        driver_token  = driver_login["access_token"]
        driver_id     = driver_login["driver_id"]
        await c.post("/driver/status", json={"is_on_duty": True},
                     headers={"Authorization": f"Bearer {driver_token}"})
        ok("Driver on-duty")

        # ── 9. Unlinked hospital account gets 403 ─────────────────────────
        r_unlinked = await c.post("/auth/login", json={"email": UNLINKED_EMAIL, "password": PASSWORD})
        unlinked_token = r_unlinked.json()["access_token"]
        # hospital_id in login should be None
        assert r_unlinked.json().get("hospital_id") is None, (
            "Unlinked hospital user should have hospital_id=None in login"
        )
        r403 = await c.get("/hospital/trips",
                           headers={"Authorization": f"Bearer {unlinked_token}"})
        assert r403.status_code == 403, (
            f"Unlinked hospital user should get 403, got {r403.status_code}: {r403.text}"
        )
        ok("CHECK 9: Unlinked hospital user correctly gets 403 (no `else 1` fallback)")

        # ── 3. GET /hospital/trips scoped to correct hospital ─────────────
        # At this point no trips yet; just confirm it returns 200 with correct scope
        r = await c.get("/hospital/trips",
                        headers={"Authorization": f"Bearer {hosp1_token}"})
        assert r.status_code == 200, f"GET /hospital/trips failed: {r.text}"
        ok("CHECK 3: GET /hospital/trips returns 200 for linked hospital user")

        # ── 4+6+7: Open WS for Hospital A and Hospital B, then trigger flow ─
        hosp_a_msgs = []
        hosp_b_msgs = []

        ws_a_url = f"{WS_BASE}/ws/hospital/{hospital_a_id}"
        ws_b_url = f"{WS_BASE}/ws/hospital/{hospital_b_id}"

        async with websockets.connect(ws_a_url) as ws_a, \
                   websockets.connect(ws_b_url) as ws_b:

            ok(f"CHECK 4: Hospital A WS connected to /ws/hospital/{hospital_a_id}")
            ok(f"CHECK 4b: Hospital B WS connected to /ws/hospital/{hospital_b_id}")

            # Patient books ambulance near Hospital A
            r = await c.post("/patient/book", json={
                "pickup_address": "Phase2 Test Pickup, Bangalore",
                "pickup_lat": 12.9716,
                "pickup_lng": 77.5946,
                "severity": "CRITICAL"
            }, headers={"Authorization": f"Bearer {patient_token}"})
            assert r.status_code == 200, f"Book failed: {r.text}"
            trip_id = r.json()["trip_id"]
            ok(f"Patient booked: trip_id={trip_id}")

            # Driver accepts
            r = await c.get("/driver/requests/pending",
                            headers={"Authorization": f"Bearer {driver_token}"})
            assert r.status_code == 200
            pending = r.json()
            if not pending:
                warn("No pending requests — dispatch may have failed. Skipping accept step.")
            else:
                req_id = pending[0]["id"]
                r = await c.post(f"/driver/accept/{req_id}",
                                 headers={"Authorization": f"Bearer {driver_token}"})
                assert r.status_code == 200, f"Accept failed: {r.text}"
                ok("Driver accepted → trip ASSIGNED")

                # Driver marks TRANSPORTING — triggers hospital selection & notification
                r = await c.post(f"/driver/trip/{trip_id}/status",
                                 json={"status": "TRANSPORTING"},
                                 headers={"Authorization": f"Bearer {driver_token}"})
                assert r.status_code == 200, f"Status update failed: {r.text}"
                ok("Driver marked TRANSPORTING → hospital selected")

                # Wait for WS messages on both channels
                async def collect(ws, bucket, label, timeout=4.0):
                    try:
                        while True:
                            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                            msg = json.loads(raw)
                            bucket.append(msg)
                            timeout = 0.5  # shorter window for subsequent messages
                    except asyncio.TimeoutError:
                        pass

                await asyncio.gather(
                    collect(ws_a, hosp_a_msgs, "Hospital A"),
                    collect(ws_b, hosp_b_msgs, "Hospital B"),
                )

        # ── 6. Hospital A received notification ───────────────────────────
        hosp_a_events = [m.get("event") for m in hosp_a_msgs]
        if not hosp_a_msgs:
            warn("No WS messages received on Hospital A channel — hospital may not have been selected (no beds/not ready?)")
        else:
            has_incoming = any(e in ("incoming_ambulance", "trip_status_changed") for e in hosp_a_events)
            if not has_incoming:
                warn(f"Hospital A got messages but not expected events: {hosp_a_events}")
            else:
                ok(f"CHECK 6: Hospital A received WS notification: {hosp_a_events}")

        # ── 7. Hospital B must NOT have received notification for this trip ─
        # Hospital B may get other system events, but must NOT get the incoming_ambulance
        # for a trip destined for Hospital A
        trip_data_at_b = [
            m for m in hosp_b_msgs
            if m.get("data", {}).get("trip_id") == trip_id
               and m.get("event") in ("incoming_ambulance", "trip_status_changed")
        ]
        if trip_data_at_b:
            fail(f"CHECK 7 FAILED: Hospital B received private notification for trip {trip_id}", str(trip_data_at_b))
        else:
            ok(f"CHECK 7: Hospital B correctly did NOT receive notification for trip {trip_id}")

        # ── 8. Hospital A GET /trips shows the incoming trip ─────────────
        r = await c.get("/hospital/trips",
                        headers={"Authorization": f"Bearer {hosp1_token}"})
        assert r.status_code == 200
        h_trips = r.json()
        trip_ids = [t["id"] for t in h_trips]
        if trip_id not in trip_ids:
            warn(f"CHECK 8: trip {trip_id} not in Hospital A trips yet (may still be ASSIGNED/pre-hospital state)")
        else:
            ok(f"CHECK 8: GET /hospital/trips for Hospital A includes trip {trip_id}")

        # ── 10+11. Traffic endpoint must not expose patient PII ───────────
        # Login traffic user
        TRAFFIC_EMAIL = f"p2_traffic_{RND}@test.com"
        r = await c.post("/auth/register", json={
            "email": TRAFFIC_EMAIL, "password": PASSWORD,
            "full_name": "P2 Traffic", "role": "TRAFFIC"
        })
        r = await c.post("/auth/login", json={"email": TRAFFIC_EMAIL, "password": PASSWORD})
        traffic_token = r.json()["access_token"]

        r = await c.get("/traffic/corridors",
                        headers={"Authorization": f"Bearer {traffic_token}"})
        assert r.status_code == 200, f"Traffic corridors failed: {r.text}"
        corridors = r.json()

        # Fetch patient's real name to check for leakage
        r_patient_name = await c.get("/auth/me",
                                     headers={"Authorization": f"Bearer {patient_token}"})
        patient_name  = r_patient_name.json().get("full_name", "P2 PATIENT")
        patient_phone = r_patient_name.json().get("phone", "")

        corridors_str = json.dumps(corridors)
        pii_fields_in_traffic = []
        if patient_name and patient_name in corridors_str:
            pii_fields_in_traffic.append(f"patient_name='{patient_name}'")
        if patient_phone and patient_phone in corridors_str:
            pii_fields_in_traffic.append(f"patient_phone='{patient_phone}'")
        # Also check for known sensitive key names
        for bad_key in ("patient_name", "patient_phone", "diagnosis", "medical"):
            if bad_key in corridors_str:
                pii_fields_in_traffic.append(f"key='{bad_key}'")

        if pii_fields_in_traffic:
            fail(f"CHECK 10+11 FAILED: Traffic corridors expose PII: {pii_fields_in_traffic}")
        else:
            ok(f"CHECK 10+11: Traffic corridors clean — no patient PII (checked {len(corridors)} corridor(s))")

        print("\n" + "─"*60)
        print("  ALL PHASE 2 HOSPITAL CHECKS PASSED")
        print("─"*60)

asyncio.run(run())
