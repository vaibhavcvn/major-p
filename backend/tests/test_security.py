"""
Phase 4A — Focused security tests for C-1, C-2, C-3, C-4 fixes.

Tests:
  C-2  Config / SECRET_KEY
    1.  SECRET_KEY is loaded from environment (not a hardcoded fallback)
    2.  JWT login still works with environment-loaded key

  C-1  CORS
    3.  CORS origins list comes from settings (not wildcard)
    4.  Allowed origin produces correct Access-Control-Allow-Origin header

  C-4  ADMIN self-registration blocked
    5.  role=ADMIN registration is rejected (400)
    6.  role=TRAFFIC registration succeeds
    7.  Normal PATIENT registration still works
    8.  Normal DRIVER registration still works

  C-3  WebSocket authentication
    9.  /ws/tracking — no token rejected (close before data)
   10.  /ws/tracking — wrong patient (Patient B cannot watch Patient A trip)
   11.  /ws/tracking — correct patient can connect
   12.  /ws/driver  — no token rejected
   13.  /ws/driver  — Driver A cannot connect to Driver B channel
   14.  /ws/driver  — correct driver can connect
   15.  /ws/admin   — unauthenticated rejected
   16.  /ws/admin   — non-admin (PATIENT) rejected
   17.  /ws/admin   — ADMIN can connect  (bonus — ensures admin WS works)
"""
import os
import pytest
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.models import (
    User, Driver, Ambulance, Hospital, HospitalStaff,
    Trip, TripStatus, UserRole,
)
from app.auth import get_password_hash, create_access_token
from app.config import settings


# ── helpers ─────────────────────────────────────────────────────────────────

def _hash():
    return get_password_hash("pass123!")


def _register(client, email, role, **extra):
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "pass123!",
        "full_name": f"Test {role}", "role": role, **extra,
    })
    return r


def _login(client, email):
    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": "pass123!"})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


def _ws_url(path, token=None):
    """Build a WS path with optional ?token= query param."""
    if token:
        return f"{path}?token={token}"
    return path


def _ws_rejected(client, url):
    """
    Assert that the server closes the WebSocket immediately after accept.
    Starlette TestClient raises WebSocketDisconnect when the server closes.
    """
    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect(url) as ws:
            # If we reach here the server accepted — try to receive;
            # the server should send a close frame promptly.
            ws.receive_text()


# ── C-2 Config / SECRET_KEY ──────────────────────────────────────────────────

def test_secret_key_not_hardcoded():
    """SECRET_KEY must be a non-empty string loaded from the environment, not a
    well-known default value."""
    key = settings.SECRET_KEY
    assert key, "SECRET_KEY must not be empty"
    # Ensure it is NOT the old hardcoded value that was in the source code
    assert key != "smart_ambulance_super_secret_jwt_key_2026_x89!_secure", (
        "SECRET_KEY must not be the old hardcoded value — it must come from .env"
    )


def test_jwt_login_works_with_env_key(client, db_session):
    """JWT login must produce a valid token using the env-loaded SECRET_KEY."""
    _register(client, "sec_c2_patient@test.com", "PATIENT")
    token = _login(client, "sec_c2_patient@test.com")
    assert token and len(token) > 20

    # The token must be accepted by /auth/me
    me = client.get("/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "sec_c2_patient@test.com"


# ── C-1 CORS ─────────────────────────────────────────────────────────────────

def test_cors_origins_not_wildcard():
    """CORS allowed origins must NOT be ['*']."""
    origins = settings.cors_origins
    assert origins, "cors_origins must not be empty"
    assert "*" not in origins, (
        "allow_origins must not contain '*' — use explicit origin list"
    )


def test_cors_header_for_allowed_origin(client):
    """A preflight from an allowed origin should return that origin in the header."""
    allowed = settings.cors_origins[0]  # e.g. "http://localhost:3000"
    r = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": allowed,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Accept any 2xx or 204 — CORS preflight can be handled differently per framework version
    assert r.status_code in (200, 204), f"Preflight returned {r.status_code}"
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == allowed, (
        f"Expected Access-Control-Allow-Origin: {allowed}, got: '{acao}'"
    )


# ── C-4 ADMIN self-registration ───────────────────────────────────────────────

def test_admin_registration_rejected(client, db_session):
    """Attempting to register with role=ADMIN must be rejected with HTTP 400."""
    r = _register(client, "sec_c4_admin@test.com", "ADMIN")
    assert r.status_code == 400, (
        f"Expected 400 for ADMIN self-registration, got {r.status_code}: {r.text}"
    )
    assert "ADMIN" in r.json().get("detail", "").upper() or "role" in r.json().get("detail", "").lower()


def test_traffic_registration_allowed(client, db_session):
    """TRAFFIC role must still be registerable via the public endpoint."""
    r = _register(client, "sec_c4_traffic@test.com", "TRAFFIC")
    assert r.status_code == 200, f"TRAFFIC registration failed: {r.text}"
    assert r.json()["role"] == "TRAFFIC"


def test_patient_registration_still_works(client, db_session):
    """Normal PATIENT registration must not be broken by the C-4 fix."""
    r = _register(client, "sec_c4_patient@test.com", "PATIENT")
    assert r.status_code == 200, f"PATIENT registration failed: {r.text}"
    assert r.json()["role"] == "PATIENT"


def test_driver_registration_still_works(client, db_session):
    """Normal DRIVER registration must not be broken by the C-4 fix."""
    r = _register(client, "sec_c4_driver@test.com", "DRIVER",
                  license_number="C4-LIC-001")
    assert r.status_code == 200, f"DRIVER registration failed: {r.text}"
    assert r.json()["role"] == "DRIVER"


# ── C-3 WebSocket authentication ─────────────────────────────────────────────

# ── /ws/tracking ──────────────────────────────────────────────────────────────

def test_ws_tracking_no_token_rejected(client, db_session):
    """/ws/tracking/{id} with no token must be rejected."""
    _ws_rejected(client, "/ws/tracking/999")


def test_ws_tracking_wrong_patient_rejected(client, db_session):
    """Patient B must not be able to subscribe to Patient A's trip."""
    # Create Patient A and a trip
    _register(client, "ws_p_a@test.com", "PATIENT")
    token_a = _login(client, "ws_p_a@test.com")

    # Create driver so booking succeeds
    _register(client, "ws_d_a@test.com", "DRIVER", license_number="WS-D-A-001")

    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Test", "pickup_lat": 12.97, "pickup_lng": 77.59,
        "severity": "HIGH",
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert book.status_code == 200
    trip_id = book.json()["trip_id"]

    # Create Patient B
    _register(client, "ws_p_b@test.com", "PATIENT")
    token_b = _login(client, "ws_p_b@test.com")

    # Patient B tries to connect to Patient A's trip tracking channel
    _ws_rejected(client, _ws_url(f"/ws/tracking/{trip_id}", token_b))


def test_ws_tracking_correct_patient_accepted(client, db_session):
    """Patient A must be able to subscribe to their own trip's tracking channel."""
    _register(client, "ws_p_own@test.com", "PATIENT")
    token = _login(client, "ws_p_own@test.com")

    _register(client, "ws_d_own@test.com", "DRIVER", license_number="WS-D-OWN-001")

    book = client.post("/api/v1/patient/book", json={
        "pickup_address": "Test", "pickup_lat": 12.97, "pickup_lng": 77.59,
        "severity": "HIGH",
    }, headers={"Authorization": f"Bearer {token}"})
    assert book.status_code == 200
    trip_id = book.json()["trip_id"]

    # Patient A should be able to connect to their own tracking channel
    with client.websocket_connect(_ws_url(f"/ws/tracking/{trip_id}", token)) as ws:
        # Connection is open — that's all we need to verify
        pass  # clean disconnect


# ── /ws/driver ────────────────────────────────────────────────────────────────

def test_ws_driver_no_token_rejected(client, db_session):
    """/ws/driver/{id} with no token must be rejected."""
    _ws_rejected(client, "/ws/driver/999")


def test_ws_driver_wrong_driver_rejected(client, db_session):
    """Driver A must not be able to subscribe to Driver B's channel."""
    _register(client, "ws_da@test.com", "DRIVER", license_number="WS-DA-001")
    _register(client, "ws_db@test.com", "DRIVER", license_number="WS-DB-002")

    token_a = _login(client, "ws_da@test.com")
    login_b = client.post("/api/v1/auth/login",
                          json={"email": "ws_db@test.com", "password": "pass123!"}).json()
    driver_b_id = login_b["driver_id"]

    # Driver A tries to subscribe to Driver B's channel
    _ws_rejected(client, _ws_url(f"/ws/driver/{driver_b_id}", token_a))


def test_ws_driver_correct_driver_accepted(client, db_session):
    """A driver must be able to subscribe to their own channel."""
    _register(client, "ws_d_self@test.com", "DRIVER", license_number="WS-D-SELF-001")
    login_data = client.post("/api/v1/auth/login",
                             json={"email": "ws_d_self@test.com", "password": "pass123!"}).json()
    token = login_data["access_token"]
    driver_id = login_data["driver_id"]

    with client.websocket_connect(_ws_url(f"/ws/driver/{driver_id}", token)) as ws:
        pass  # connection accepted and cleanly closed


# ── /ws/admin ────────────────────────────────────────────────────────────────

def test_ws_admin_no_token_rejected(client, db_session):
    """/ws/admin with no token must be rejected."""
    _ws_rejected(client, "/ws/admin")


def test_ws_admin_non_admin_rejected(client, db_session):
    """A PATIENT user must not be able to connect to the admin channel."""
    _register(client, "ws_nonadmin@test.com", "PATIENT")
    token = _login(client, "ws_nonadmin@test.com")
    _ws_rejected(client, _ws_url("/ws/admin", token))


def test_ws_admin_admin_accepted(client, db_session):
    """An ADMIN user must be able to connect to the admin channel."""
    # Manually create an ADMIN user directly in the DB (can't use public register)
    admin_user = User(
        email="ws_admin_user@test.com",
        password_hash=_hash(),
        role=UserRole.ADMIN,
        full_name="Admin WS Test",
    )
    db_session.add(admin_user)
    db_session.commit()
    db_session.refresh(admin_user)

    token = create_access_token({"sub": str(admin_user.id), "role": admin_user.role})

    with client.websocket_connect(_ws_url("/ws/admin", token)) as ws:
        pass  # connection accepted and cleanly closed
