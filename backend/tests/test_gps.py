import pytest
from app.models import User, Driver, Ambulance, Trip, TripStatus
from app.auth import get_password_hash

def seed_gps_data(db):
    pwd = get_password_hash("password123")

    p = User(email="p_gps@test.com", password_hash=pwd, role="PATIENT", full_name="Patient GPS")
    d_user = User(email="d_gps@test.com", password_hash=pwd, role="DRIVER", full_name="Driver GPS")
    db.add_all([p, d_user])
    db.commit()

    drv = Driver(user_id=d_user.id, license_number="LIC-GPS", is_on_duty=True, current_lat=12.97, current_lng=77.59)
    db.add(drv)
    db.commit()

    amb = Ambulance(driver_id=drv.id, vehicle_number="AMB-GPS", type="ALS", is_active=True, current_lat=12.97, current_lng=77.59)
    db.add(amb)
    db.commit()

    trip = Trip(patient_id=p.id, assigned_driver_id=drv.id, assigned_ambulance_id=amb.id, status=TripStatus.ASSIGNED, pickup_address="Point A", pickup_lat=12.97, pickup_lng=77.59)
    db.add(trip)
    db.commit()

def test_gps_authorization(client, db_session):
    seed_gps_data(db_session)

    p_res = client.post("/api/v1/auth/login", json={"email": "p_gps@test.com", "password": "password123"}).json()
    d_res = client.post("/api/v1/auth/login", json={"email": "d_gps@test.com", "password": "password123"}).json()
    p_token, d_token = p_res["access_token"], d_res["access_token"]

    # Patient trying to push GPS should be rejected (403 Forbidden - Role check)
    res_patient_gps = client.post("/api/v1/driver/gps", json={
        "trip_id": 1,
        "latitude": 12.972,
        "longitude": 77.595,
        "speed": 10.0,
        "heading": 90.0,
        "accuracy": 5.0
    }, headers={"Authorization": f"Bearer {p_token}"})
    assert res_patient_gps.status_code == 403

    # Assigned Driver pushing GPS should succeed
    res_driver_gps = client.post("/api/v1/driver/gps", json={
        "trip_id": 1,
        "latitude": 12.972,
        "longitude": 77.595,
        "speed": 12.5,
        "heading": 90.0,
        "accuracy": 3.0
    }, headers={"Authorization": f"Bearer {d_token}"})
    assert res_driver_gps.status_code == 200
    assert "eta_minutes" in res_driver_gps.json()
