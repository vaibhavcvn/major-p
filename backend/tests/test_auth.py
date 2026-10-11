import pytest

def test_register_and_login_patient(client):
    res = client.post("/api/v1/auth/register", json={
        "email": "testpatient@example.com",
        "password": "password123",
        "full_name": "Test Patient",
        "role": "PATIENT"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "PATIENT"

    res_login = client.post("/api/v1/auth/login", json={
        "email": "testpatient@example.com",
        "password": "password123"
    })
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()

def test_invalid_login(client):
    res = client.post("/api/v1/auth/login", json={
        "email": "wrong@example.com",
        "password": "wrongpassword"
    })
    assert res.status_code == 401
