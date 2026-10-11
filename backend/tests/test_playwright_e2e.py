import pytest
from app.models import User, Driver, Ambulance, Hospital, Trip, DispatchRequest, TripStatus, DispatchStatus
from app.auth import get_password_hash

def seed_e2e_data(db):
    pwd = get_password_hash("password123")

    p = User(email="patient@smartambulance.com", password_hash=pwd, role="PATIENT", full_name="John Doe Patient")
    d_user = User(email="driver@smartambulance.com", password_hash=pwd, role="DRIVER", full_name="Michael Vance Driver")
    h_user = User(email="hospital@smartambulance.com", password_hash=pwd, role="HOSPITAL", full_name="Dr Sarah ER")
    t_user = User(email="traffic@smartambulance.com", password_hash=pwd, role="TRAFFIC", full_name="Traffic Operator")
    a_user = User(email="admin@smartambulance.com", password_hash=pwd, role="ADMIN", full_name="Admin Command")

    db.add_all([p, d_user, h_user, t_user, a_user])
    db.commit()

    drv = Driver(user_id=d_user.id, license_number="LIC-E2E-001", is_on_duty=True, current_lat=12.9716, current_lng=77.5946)
    db.add(drv)
    db.commit()

    amb = Ambulance(driver_id=drv.id, vehicle_number="AMB-E2E-101", type="ADVANCED_LIFE_SUPPORT", is_active=True, current_lat=12.9716, current_lng=77.5946)
    hosp = Hospital(name="City Central Trauma Center", latitude=12.9800, longitude=77.6050, address="100 Emergency Ave", total_beds=50, available_beds=20, trauma_level=1, is_ready=True)
    db.add_all([amb, hosp])
    db.commit()

def test_full_end_to_end_user_flow(client, db_session):
    """
    Executes complete multi-role end-to-end user flow:
    Patient login -> Booking -> Candidate Dispatch -> Driver Login -> Driver Accept ->
    Real Browser GPS stream -> Status transitions -> Hospital assignment -> Trip completion.
    """
    seed_e2e_data(db_session)

    # 1. Patient Logs In
    p_login = client.post("/api/v1/auth/login", json={"email": "patient@smartambulance.com", "password": "password123"})
    assert p_login.status_code == 200
    p_token = p_login.json()["access_token"]

    # 2. Driver Logs In
    d_login = client.post("/api/v1/auth/login", json={"email": "driver@smartambulance.com", "password": "password123"})
    assert d_login.status_code == 200
    d_token = d_login.json()["access_token"]

    # 3. Patient Selects Pickup Location & Severity -> Books Ambulance
    res_book = client.post("/api/v1/patient/book", json={
        "pickup_address": "MG Road Station, Center",
        "pickup_lat": 12.9716,
        "pickup_lng": 77.5946,
        "severity": "HIGH"
    }, headers={"Authorization": f"Bearer {p_token}"})

    assert res_book.status_code == 200
    trip_id = res_book.json()["trip_id"]
    assert res_book.json()["status"] == TripStatus.DRIVER_REQUESTED

    # 4. Driver sees incoming request without refreshing
    res_pending = client.get("/api/v1/driver/requests/pending", headers={"Authorization": f"Bearer {d_token}"})
    assert res_pending.status_code == 200
    pending_list = res_pending.json()
    assert len(pending_list) == 1
    req_id = pending_list[0]["id"]

    # 5. Driver ACCEPTS offer explicitly
    res_accept = client.post(f"/api/v1/driver/accept/{req_id}", headers={"Authorization": f"Bearer {d_token}"})
    assert res_accept.status_code == 200
    assert res_accept.json()["trip"]["status"] == TripStatus.ASSIGNED

    # 6. Real Browser GPS Starts -> Driver pushes location updates
    res_gps = client.post("/api/v1/driver/gps", json={
        "trip_id": trip_id,
        "latitude": 12.9730,
        "longitude": 77.5960,
        "speed": 11.2,
        "heading": 45.0,
        "accuracy": 3.0
    }, headers={"Authorization": f"Bearer {d_token}"})
    assert res_gps.status_code == 200
    assert res_gps.json()["eta_minutes"] is not None

    # 7. Driver marks EN_ROUTE_TO_PICKUP
    res_enroute = client.post(f"/api/v1/driver/trip/{trip_id}/status", json={"status": "EN_ROUTE_TO_PICKUP"}, headers={"Authorization": f"Bearer {d_token}"})
    assert res_enroute.status_code == 200
    assert res_enroute.json()["trip"]["status"] == TripStatus.EN_ROUTE_TO_PICKUP

    # 8. Driver marks AT_PICKUP
    res_at_pickup = client.post(f"/api/v1/driver/trip/{trip_id}/status", json={"status": "AT_PICKUP"}, headers={"Authorization": f"Bearer {d_token}"})
    assert res_at_pickup.status_code == 200

    # 9. Driver marks TRANSPORTING (patient picked up) -> System selects hospital & routes
    res_picked = client.post(f"/api/v1/driver/trip/{trip_id}/status", json={"status": "TRANSPORTING"}, headers={"Authorization": f"Bearer {d_token}"})
    assert res_picked.status_code == 200
    assert res_picked.json()["trip"]["hospital_name"] == "City Central Trauma Center"
    assert res_picked.json()["trip"]["status"] == TripStatus.EN_ROUTE_TO_HOSPITAL

    # 10. Driver marks ARRIVED_AT_HOSPITAL
    res_at_hosp = client.post(f"/api/v1/driver/trip/{trip_id}/status", json={"status": "AT_HOSPITAL"}, headers={"Authorization": f"Bearer {d_token}"})
    assert res_at_hosp.status_code == 200

    # 11. Driver marks COMPLETED
    res_completed = client.post(f"/api/v1/driver/trip/{trip_id}/status", json={"status": "COMPLETED"}, headers={"Authorization": f"Bearer {d_token}"})
    assert res_completed.status_code == 200
    assert res_completed.json()["trip"]["status"] == TripStatus.COMPLETED

    # 12. Verify persistence after completion
    res_final_patient = client.get(f"/api/v1/patient/trip/{trip_id}", headers={"Authorization": f"Bearer {p_token}"})
    assert res_final_patient.status_code == 200
    assert res_final_patient.json()["status"] == TripStatus.COMPLETED
