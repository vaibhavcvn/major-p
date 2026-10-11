import pytest
from app.models import User, Driver, Ambulance, Hospital, Trip, DispatchRequest, TripStatus, DispatchStatus
from app.auth import get_password_hash

def seed_dispatch_data(db):
    pwd = get_password_hash("password123")

    p = User(email="p@test.com", password_hash=pwd, role="PATIENT", full_name="Patient Test")
    d_user = User(email="d@test.com", password_hash=pwd, role="DRIVER", full_name="Driver Test")
    db.add_all([p, d_user])
    db.commit()

    drv = Driver(user_id=d_user.id, license_number="LIC-123", is_on_duty=True, current_lat=12.9716, current_lng=77.5946)
    db.add(drv)
    db.commit()

    amb = Ambulance(driver_id=drv.id, vehicle_number="AMB-999", type="ALS", is_active=True, current_lat=12.9716, current_lng=77.5946)
    hosp = Hospital(name="Test Hospital", latitude=12.9800, longitude=77.6000, address="Hospital Rd", total_beds=50, available_beds=20, trauma_level=1, is_ready=True)
    db.add_all([amb, hosp])
    db.commit()

def test_booking_and_atomic_acceptance(client, db_session):
    seed_dispatch_data(db_session)

    p_res = client.post("/api/v1/auth/login", json={"email": "p@test.com", "password": "password123"}).json()
    d_res = client.post("/api/v1/auth/login", json={"email": "d@test.com", "password": "password123"}).json()
    p_token, d_token = p_res["access_token"], d_res["access_token"]

    # 1. Patient Books
    res_book = client.post("/api/v1/patient/book", json={
        "pickup_address": "MG Road Metro Station",
        "pickup_lat": 12.9716,
        "pickup_lng": 77.5946,
        "severity": "HIGH"
    }, headers={"Authorization": f"Bearer {p_token}"})

    assert res_book.status_code == 200
    trip_id = res_book.json()["trip_id"]

    # 2. Driver views pending requests
    res_reqs = client.get("/api/v1/driver/requests/pending", headers={"Authorization": f"Bearer {d_token}"})
    assert res_reqs.status_code == 200
    reqs = res_reqs.json()
    assert len(reqs) == 1
    req_id = reqs[0]["id"]

    # 3. Driver ACCEPTS trip
    res_accept = client.post(f"/api/v1/driver/accept/{req_id}", headers={"Authorization": f"Bearer {d_token}"})
    assert res_accept.status_code == 200
    assert res_accept.json()["trip"]["status"] == TripStatus.ASSIGNED

    # 4. Re-accepting should fail
    res_accept_again = client.post(f"/api/v1/driver/accept/{req_id}", headers={"Authorization": f"Bearer {d_token}"})
    assert res_accept_again.status_code == 400
