import asyncio
import collections
import datetime
import logging
import time
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request, status, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import httpx

from app.config import settings
from app.database import get_db, Base, engine
from app.models import (
    User, Driver, Ambulance, Hospital, HospitalStaff, Trip, DispatchRequest,
    GPSLocation, TrafficAlert, EmergencyEvent, UserRole, TripStatus, DispatchStatus
)
from app.schemas import (
    UserRegister, UserLogin, Token, UserOut, DriverStatusUpdate, DriverLocationUpdate,
    DriverOut, AmbulanceOut, HospitalOut, HospitalStatusUpdate, TripCreate, TripStatusUpdate,
    TripOut, DispatchRequestOut, GPSUpdate, PredictDelayRequest, PredictDelayResponse
)
from app.auth import (
    get_password_hash, verify_password, create_access_token, get_current_user, require_role
)
from app.dispatch import dispatch_next_driver, find_eligible_drivers, haversine_distance_km, expire_pending_requests
from app.websocket import manager
from app.ml import predict_ambulance_delay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_ambulance.main")

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# In-process set tracking which trips have already triggered a traffic
# proximity alert. Prevents spamming on every GPS update.
# Cleared when the trip transitions to a terminal state.
# ---------------------------------------------------------------------------
_proximity_alerted_trips: set[int] = set()

# ---------------------------------------------------------------------------
# Background expiry worker — runs every 10 seconds while the server is up
# ---------------------------------------------------------------------------
EXPIRY_POLL_INTERVAL_SECONDS = 10

async def _expiry_worker() -> None:
    """Periodically expire PENDING dispatch requests whose TTL has elapsed."""
    from app.database import SessionLocal
    logger.info("Dispatch expiry worker started (interval=%ds)", EXPIRY_POLL_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.sleep(EXPIRY_POLL_INTERVAL_SECONDS)
            db = SessionLocal()
            try:
                await expire_pending_requests(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("Dispatch expiry worker stopped")
            break
        except Exception as exc:
            # Never crash the worker on a transient error
            logger.error("Expiry worker error: %s", exc, exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: start background expiry task on startup, cancel on shutdown."""
    task = asyncio.create_task(_expiry_worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Smart Ambulance Response Platform API with Realtime Dispatch, Browser GPS & ML Delay Prediction",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # loaded from ALLOWED_ORIGINS env var
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ---------------------------------------------------------------------------
# M-3: In-process sliding-window rate limiter for auth endpoints
# ---------------------------------------------------------------------------
# Stores per-IP timestamps in a deque.  On every call older entries are
# pruned and the count is compared to the limit.  Entirely in-process —
# no Redis or external service required.  Suitable for a demo/dev server.
# Disabled in tests via the RATE_LIMIT_ENABLED env var (set in conftest).

class _SlidingWindowLimiter:
    def __init__(self, max_calls: int = 10, window_seconds: int = 60):
        self._max   = max_calls
        self._win   = window_seconds
        self._store: dict[str, collections.deque] = {}

    def is_allowed(self, key: str) -> bool:
        now   = time.monotonic()
        cutoff = now - self._win
        if key not in self._store:
            self._store[key] = collections.deque()
        dq = self._store[key]
        # Prune expired entries
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self._max:
            return False
        dq.append(now)
        return True

_auth_limiter = _SlidingWindowLimiter(max_calls=10, window_seconds=60)

def _check_auth_rate(request: Request) -> None:
    """Dependency — raises 429 if the caller has exceeded the auth rate limit."""
    import os
    if os.getenv("RATE_LIMIT_ENABLED", "1") == "0":
        return
    ip = request.client.host if request.client else "unknown"
    if not _auth_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts. Please wait a moment and try again."
        )

# ---------------------------------------------------------------------------
# WebSocket JWT authentication helper
# ---------------------------------------------------------------------------
# WebSocket connections carry the JWT as a query parameter:
#   /ws/tracking/42?token=<jwt>
# This is necessary because browser WebSocket APIs cannot set custom headers.

from jose import JWTError, jwt as _jwt

async def _ws_get_user(websocket: WebSocket, db: Session) -> Optional[User]:
    """
    Decode and verify the JWT token passed as ?token=<jwt> on a WebSocket URL.
    Returns the User if valid, or closes the WebSocket with code 4001 and returns None.
    """
    token: Optional[str] = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return None
    try:
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise JWTError("missing sub")
        user = db.query(User).filter(User.id == int(user_id_str)).first()
        if not user:
            raise JWTError("user not found")
        return user
    except JWTError:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return None

# Helper function to enrich TripOut with driver & hospital details
# H-3: include_driver_phone defaults to False.  Only admin-facing callers pass True.
def enrich_trip(trip: Trip, db: Session, include_driver_phone: bool = False) -> dict:
    t_dict = {
        "id": trip.id,
        "patient_id": trip.patient_id,
        "assigned_driver_id": trip.assigned_driver_id,
        "assigned_ambulance_id": trip.assigned_ambulance_id,
        "hospital_id": trip.hospital_id,
        "status": trip.status,
        "severity": trip.severity,
        "pickup_address": trip.pickup_address,
        "pickup_lat": trip.pickup_lat,
        "pickup_lng": trip.pickup_lng,
        "destination_address": trip.destination_address,
        "destination_lat": trip.destination_lat,
        "destination_lng": trip.destination_lng,
        "estimated_pickup_eta": trip.estimated_pickup_eta,
        "estimated_hospital_eta": trip.estimated_hospital_eta,
        "predicted_delay_minutes": trip.predicted_delay_minutes,
        "delay_risk_level": trip.delay_risk_level,
        "distance_km": trip.distance_km,
        "created_at": trip.created_at.isoformat() if isinstance(trip.created_at, datetime.datetime) else str(trip.created_at),
        "updated_at": trip.updated_at.isoformat() if isinstance(trip.updated_at, datetime.datetime) else str(trip.updated_at),
        "driver_name": None,
        # H-3: driver_phone is None by default; set only when caller explicitly opts in (admin)
        "driver_phone": None,
        "ambulance_plate": None,
        "hospital_name": None,
        "driver_lat": None,
        "driver_lng": None,
    }
    if trip.assigned_driver and trip.assigned_driver.user:
        t_dict["driver_name"] = trip.assigned_driver.user.full_name
        if include_driver_phone:
            t_dict["driver_phone"] = trip.assigned_driver.user.phone
        t_dict["driver_lat"] = trip.assigned_driver.current_lat
        t_dict["driver_lng"] = trip.assigned_driver.current_lng

    if trip.assigned_ambulance:
        t_dict["ambulance_plate"] = trip.assigned_ambulance.vehicle_number

    if trip.hospital:
        t_dict["hospital_name"] = trip.hospital.name

    return t_dict

# ----------------------------------------------------
# AUTH ENDPOINTS
# ----------------------------------------------------
@app.post(f"{settings.API_V1_STR}/auth/register", response_model=Token)
def register_user(req: UserRegister, request: Request, db: Session = Depends(get_db), _: None = Depends(_check_auth_rate)):
    # C-4: Block self-elevation to ADMIN via public registration.
    # Allowed public roles: PATIENT, DRIVER, HOSPITAL, TRAFFIC.
    requested_role = req.role.upper()
    PUBLIC_ROLES = {UserRole.PATIENT, UserRole.DRIVER, UserRole.HOSPITAL, UserRole.TRAFFIC}
    if requested_role not in PUBLIC_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{req.role}' cannot be set during public registration. "
                   "Allowed roles: PATIENT, DRIVER, HOSPITAL, TRAFFIC."
        )

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    hashed_pwd = get_password_hash(req.password)
    user = User(
        email=req.email,
        password_hash=hashed_pwd,
        role=requested_role,
        full_name=req.full_name,
        phone=req.phone
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # If role is DRIVER, create driver profile & default ambulance
    if user.role == UserRole.DRIVER:
        lic = req.license_number or f"LIC-{user.id:04d}"
        driver_prof = Driver(
            user_id=user.id,
            license_number=lic,
            is_on_duty=True
        )
        db.add(driver_prof)
        db.commit()
        db.refresh(driver_prof)

        amb = Ambulance(
            driver_id=driver_prof.id,
            vehicle_number=f"AMB-{driver_prof.id:03d}",
            type="ADVANCED_LIFE_SUPPORT",
            is_active=True
        )
        db.add(amb)
        db.commit()

    token_str = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": token_str,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "full_name": user.full_name
    }

@app.post(f"{settings.API_V1_STR}/auth/login", response_model=Token)
def login_user(req: UserLogin, request: Request, db: Session = Depends(get_db), _: None = Depends(_check_auth_rate)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token_str = create_access_token({"sub": str(user.id), "role": user.role})

    # Resolve role-specific profile IDs so the frontend opens the correct WebSocket channel
    driver_id: Optional[int] = None
    hospital_id: Optional[int] = None

    if user.role == UserRole.DRIVER:
        driver_profile = db.query(Driver).filter(Driver.user_id == user.id).first()
        if driver_profile:
            driver_id = driver_profile.id

    elif user.role == UserRole.HOSPITAL:
        h_staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == user.id).first()
        if h_staff:
            hospital_id = h_staff.hospital_id

    return {
        "access_token": token_str,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "full_name": user.full_name,
        "driver_id": driver_id,
        "hospital_id": hospital_id,
    }

@app.get(f"{settings.API_V1_STR}/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# ----------------------------------------------------
# PATIENT ENDPOINTS
# ----------------------------------------------------
@app.post(f"{settings.API_V1_STR}/patient/book", response_model=dict)
async def book_ambulance(req: TripCreate, current_user: User = Depends(require_role([UserRole.PATIENT, UserRole.ADMIN])), db: Session = Depends(get_db)):
    # Create Trip
    trip = Trip(
        patient_id=current_user.id,
        status=TripStatus.REQUESTED,
        severity=req.severity,
        pickup_address=req.pickup_address,
        pickup_lat=req.pickup_lat,
        pickup_lng=req.pickup_lng
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    # Dispatch to nearest eligible driver
    success = await dispatch_next_driver(db, trip)

    # Broadcast admin update
    await manager.broadcast_admin({
        "event": "new_trip_created",
        "data": enrich_trip(trip, db)
    })

    return {
        "message": "Ambulance request created. Finding nearby drivers...",
        "trip_id": trip.id,
        "status": trip.status,
        "dispatched": success
    }

@app.get(f"{settings.API_V1_STR}/patient/trip/{{trip_id}}", response_model=dict)
def get_patient_trip(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Access control: Patient can view their trip, driver/hospital/admin can view active trips
    if current_user.role == UserRole.PATIENT and trip.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized trip access")

    return enrich_trip(trip, db)

# ----------------------------------------------------
# DRIVER ENDPOINTS
# ----------------------------------------------------
@app.get(f"{settings.API_V1_STR}/driver/profile", response_model=DriverOut)
def get_driver_profile(current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    return driver

@app.post(f"{settings.API_V1_STR}/driver/status", response_model=DriverOut)
def update_driver_duty(req: DriverStatusUpdate, current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    driver.is_on_duty = req.is_on_duty
    db.commit()
    db.refresh(driver)
    return driver

@app.get(f"{settings.API_V1_STR}/driver/requests/pending", response_model=List[DispatchRequestOut])
def get_driver_pending_requests(current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        return []

    requests = db.query(DispatchRequest).filter(
        DispatchRequest.driver_id == driver.id,
        DispatchRequest.status == DispatchStatus.PENDING,
        DispatchRequest.expires_at > datetime.datetime.utcnow()
    ).all()

    res = []
    for r in requests:
        r_dict = {
            "id": r.id,
            "trip_id": r.trip_id,
            "driver_id": r.driver_id,
            "status": r.status,
            "distance_km": r.distance_km,
            "requested_at": r.requested_at,
            "expires_at": r.expires_at,
            "trip": enrich_trip(r.trip, db)
        }
        res.append(r_dict)
    return res

@app.post(f"{settings.API_V1_STR}/driver/accept/{{request_id}}", response_model=dict)
async def accept_dispatch_request(request_id: int, current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    # Atomic acceptance check
    req = db.query(DispatchRequest).filter(DispatchRequest.id == request_id).with_for_update().first()
    if not req:
        raise HTTPException(status_code=404, detail="Dispatch request not found")

    if req.driver_id != driver.id:
        raise HTTPException(status_code=403, detail="Dispatch request belongs to another driver")

    if req.status != DispatchStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Request is no longer pending (Status: {req.status})")

    trip = db.query(Trip).filter(Trip.id == req.trip_id).with_for_update().first()
    if trip.status not in [TripStatus.DRIVER_REQUESTED, TripStatus.SEARCHING]:
        raise HTTPException(status_code=400, detail="Trip is already assigned or cancelled")

    # ATOMIC ASSIGNMENT
    req.status = DispatchStatus.ACCEPTED
    req.responded_at = datetime.datetime.utcnow()

    ambulance = db.query(Ambulance).filter(Ambulance.driver_id == driver.id).first()

    trip.assigned_driver_id = driver.id
    trip.assigned_ambulance_id = ambulance.id if ambulance else None
    trip.status = TripStatus.ASSIGNED
    db.commit()
    db.refresh(trip)

    # Compute initial ML prediction for delay
    pred = predict_ambulance_delay(req.distance_km, trip.estimated_pickup_eta or 10.0, trip.severity)
    trip.predicted_delay_minutes = pred["predicted_delay_minutes"]
    trip.delay_risk_level = pred["delay_risk_level"]
    db.commit()

    logger.info(f"Driver {driver.id} ACCEPTED trip {trip.id}")

    enriched = enrich_trip(trip, db)

    # Notify patient & admin realtime
    await manager.broadcast_to_trip(trip.id, {
        "event": "trip_assigned",
        "data": enriched
    })
    await manager.broadcast_admin({
        "event": "trip_assigned",
        "data": enriched
    })

    return {
        "message": "Trip request accepted successfully. Real browser GPS tracking initiated.",
        "trip": enriched
    }

@app.post(f"{settings.API_V1_STR}/driver/reject/{{request_id}}", response_model=dict)
async def reject_dispatch_request(request_id: int, current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    # Lock the request row — prevents simultaneous EXPIRY from double-processing
    req = db.query(DispatchRequest).filter(DispatchRequest.id == request_id).with_for_update().first()
    if not req or req.driver_id != driver.id:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != DispatchStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Request is no longer pending (status: {req.status})")

    req.status = DispatchStatus.REJECTED
    req.responded_at = datetime.datetime.utcnow()

    trip = db.query(Trip).filter(Trip.id == req.trip_id).with_for_update().first()
    trip.status = TripStatus.SEARCHING
    db.commit()

    # Escalate to next candidate driver
    await dispatch_next_driver(db, trip)

    return {"message": "Request rejected. Escalating to next available driver."}

# H-1: Statuses the driver endpoint is allowed to set directly.
# DRIVER_REQUESTED → ASSIGNED is exclusively handled by the /driver/accept endpoint.
# System-only states (REQUESTED, SEARCHING, DRIVER_REQUESTED, FAILED, CANCELLED) are
# not in this set and cannot be set by the driver through this endpoint.
_DRIVER_SETTABLE_STATUSES = {
    TripStatus.EN_ROUTE_TO_PICKUP,
    TripStatus.AT_PICKUP,
    TripStatus.TRANSPORTING,       # triggers hospital selection → becomes EN_ROUTE_TO_HOSPITAL
    TripStatus.AT_HOSPITAL,
    TripStatus.COMPLETED,
}

# H-1: Valid state transitions the driver may request.
# Key = current trip status, Value = set of statuses the driver may transition to from it.
_DRIVER_VALID_TRANSITIONS: dict[str, set[str]] = {
    TripStatus.ASSIGNED:              {TripStatus.EN_ROUTE_TO_PICKUP},
    TripStatus.EN_ROUTE_TO_PICKUP:    {TripStatus.AT_PICKUP},
    TripStatus.AT_PICKUP:             {TripStatus.TRANSPORTING},
    TripStatus.TRANSPORTING:          set(),   # system overrides to EN_ROUTE_TO_HOSPITAL
    TripStatus.EN_ROUTE_TO_HOSPITAL:  {TripStatus.AT_HOSPITAL},
    TripStatus.AT_HOSPITAL:           {TripStatus.COMPLETED},
}

@app.post(f"{settings.API_V1_STR}/driver/trip/{{trip_id}}/status", response_model=dict)
async def update_trip_status(trip_id: int, req: TripStatusUpdate, current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip or trip.assigned_driver_id != driver.id:
        raise HTTPException(status_code=403, detail="Unauthorized to update this trip")

    # H-1: Validate requested status against the allowlist
    new_status = req.status.upper()
    if new_status not in _DRIVER_SETTABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status '{req.status}' is not a valid driver-settable trip status. "
                   f"Allowed: {sorted(_DRIVER_SETTABLE_STATUSES)}"
        )

    # H-1: Enforce valid state transitions
    current_status = trip.status
    allowed_next = _DRIVER_VALID_TRANSITIONS.get(current_status, set())

    # TRANSPORTING is the special case: the driver submits TRANSPORTING and
    # the system converts it to EN_ROUTE_TO_HOSPITAL internally (see below).
    # We treat EN_ROUTE_TO_HOSPITAL as an acceptable alias for TRANSPORTING here.
    if new_status == TripStatus.TRANSPORTING:
        if TripStatus.AT_PICKUP != current_status:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current_status}' to '{new_status}'. "
                       f"Trip must be in AT_PICKUP state to mark patient as picked up."
            )
    elif new_status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: '{current_status}' → '{new_status}'. "
                   f"Allowed next states from '{current_status}': {sorted(allowed_next) or 'none (terminal state)'}"
        )

    # H-1: Explicitly block bypassing the accept workflow
    if new_status == TripStatus.ASSIGNED:
        raise HTTPException(
            status_code=400,
            detail="Trip assignment requires driver ACCEPT via the dedicated accept endpoint."
        )

    trip.status = new_status

    # Special handling when driver marks TRANSPORTING (patient picked up)
    if new_status in [TripStatus.TRANSPORTING]:
        # Select nearest ready hospital
        hospitals = db.query(Hospital).filter(Hospital.is_ready == True, Hospital.available_beds > 0).all()
        if hospitals:
            # Sort hospitals by distance from pickup location
            hospitals.sort(key=lambda h: haversine_distance_km(trip.pickup_lat, trip.pickup_lng, h.latitude, h.longitude))
            selected_h = hospitals[0]
            trip.hospital_id = selected_h.id
            trip.destination_address = selected_h.address
            trip.destination_lat = selected_h.latitude
            trip.destination_lng = selected_h.longitude
            dist_to_h = haversine_distance_km(trip.pickup_lat, trip.pickup_lng, selected_h.latitude, selected_h.longitude)
            trip.estimated_hospital_eta = max(1, int((dist_to_h / 45.0) * 60))
            trip.status = TripStatus.EN_ROUTE_TO_HOSPITAL

            # Notify Hospital
            await manager.notify_hospital(selected_h.id, {
                "event": "incoming_ambulance",
                "data": {
                    "trip_id": trip.id,
                    "ambulance_plate": trip.assigned_ambulance.vehicle_number if trip.assigned_ambulance else "AMB-101",
                    "severity": trip.severity,
                    "estimated_eta_minutes": trip.estimated_hospital_eta,
                    "status": trip.status
                }
            })

    db.commit()
    db.refresh(trip)

    # Clear proximity alert tracking when a trip reaches a terminal state
    if trip.status in (TripStatus.COMPLETED, TripStatus.FAILED, TripStatus.CANCELLED):
        _proximity_alerted_trips.discard(trip.id)

    enriched = enrich_trip(trip, db)

    # Broadcast status change to patient, hospital, admin, traffic
    await manager.broadcast_to_trip(trip.id, {
        "event": "trip_status_changed",
        "data": enriched
    })
    await manager.broadcast_admin({
        "event": "trip_status_changed",
        "data": enriched
    })
    if trip.hospital_id:
        await manager.notify_hospital(trip.hospital_id, {
            "event": "trip_status_changed",
            "data": enriched
        })

    return {"message": f"Trip status updated to {trip.status}", "trip": enriched}

# ----------------------------------------------------
# REAL BROWSER GPS ENDPOINT
# ----------------------------------------------------
@app.post(f"{settings.API_V1_STR}/driver/gps", response_model=dict)
async def record_driver_gps(payload: GPSUpdate, current_user: User = Depends(require_role([UserRole.DRIVER])), db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    # Verify active trip assigned to driver
    trip = db.query(Trip).filter(Trip.id == payload.trip_id).first()
    if not trip or trip.assigned_driver_id != driver.id:
        raise HTTPException(status_code=403, detail="Driver is not assigned to this trip")

    active_statuses = [
        TripStatus.ASSIGNED, TripStatus.EN_ROUTE_TO_PICKUP, TripStatus.AT_PICKUP,
        TripStatus.TRANSPORTING, TripStatus.HOSPITAL_SELECTED, TripStatus.EN_ROUTE_TO_HOSPITAL,
        TripStatus.AT_HOSPITAL
    ]
    if trip.status not in active_statuses:
        raise HTTPException(status_code=400, detail="Trip is not in an active tracking state")

    ambulance = db.query(Ambulance).filter(Ambulance.driver_id == driver.id).first()
    if not ambulance:
        raise HTTPException(status_code=400, detail="Driver does not operate an active ambulance")

    # Update driver & ambulance coordinates
    driver.current_lat = payload.latitude
    driver.current_lng = payload.longitude
    driver.last_location_update = datetime.datetime.utcnow()

    ambulance.current_lat = payload.latitude
    ambulance.current_lng = payload.longitude

    gps_entry = GPSLocation(
        trip_id=trip.id,
        driver_id=driver.id,
        ambulance_id=ambulance.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        speed=payload.speed,
        heading=payload.heading,
        accuracy=payload.accuracy
    )
    db.add(gps_entry)
    db.commit()

    # Recompute ETA dynamically based on current GPS position
    target_lat = trip.destination_lat if trip.destination_lat else trip.pickup_lat
    target_lng = trip.destination_lng if trip.destination_lng else trip.pickup_lng
    dist_rem = haversine_distance_km(payload.latitude, payload.longitude, target_lat, target_lng)

    speed_kph = max(20.0, payload.speed * 3.6 if payload.speed else 40.0)
    current_eta = max(1, int((dist_rem / speed_kph) * 60))

    if trip.destination_lat:
        trip.estimated_hospital_eta = current_eta
    else:
        trip.estimated_pickup_eta = current_eta

    # Re-eval ML delay prediction
    pred = predict_ambulance_delay(dist_rem, current_eta, trip.severity)
    trip.predicted_delay_minutes = pred["predicted_delay_minutes"]
    trip.delay_risk_level = pred["delay_risk_level"]
    db.commit()

    gps_broadcast = {
        "event": "ambulance_location",
        "data": {
            "trip_id": trip.id,
            "driver_id": driver.id,
            "ambulance_plate": ambulance.vehicle_number,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "speed": payload.speed,
            "heading": payload.heading,
            "eta_minutes": current_eta,
            "predicted_delay_minutes": trip.predicted_delay_minutes,
            "delay_risk_level": trip.delay_risk_level,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    }

    # Broadcast real-time location to Patient, Hospital, Traffic, Admin
    await manager.broadcast_to_trip(trip.id, gps_broadcast)
    await manager.broadcast_admin(gps_broadcast)

    if trip.hospital_id:
        await manager.notify_hospital(trip.hospital_id, gps_broadcast)

    await manager.broadcast_traffic({
        "event": "corridor_update",
        "data": {
            "ambulance_id": ambulance.id,
            "vehicle_number": ambulance.vehicle_number,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "eta_minutes": current_eta,
            "trip_status": trip.status
        }
    })

    # ── FIX-8: Proximity-based traffic alert ──────────────────────────────
    # Only fire once per trip when the ambulance enters the proximity threshold.
    if trip.id not in _proximity_alerted_trips:
        dest_lat = trip.destination_lat if trip.destination_lat else None
        dest_lng = trip.destination_lng if trip.destination_lng else None
        if dest_lat is not None and dest_lng is not None:
            dist_to_dest = haversine_distance_km(
                payload.latitude, payload.longitude, dest_lat, dest_lng
            )
            if dist_to_dest <= settings.TRAFFIC_PROXIMITY_KM:
                _proximity_alerted_trips.add(trip.id)
                heading_deg = payload.heading or 0
                # Map heading degrees to cardinal direction
                dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                direction = dirs[round(heading_deg / 45) % 8]
                dest_name = trip.hospital_name if hasattr(trip, "hospital_name") else (
                    trip.destination_address or "Destination"
                )
                # Fetch hospital name from relationship if available
                if trip.hospital:
                    dest_name = trip.hospital.name

                await manager.broadcast_traffic({
                    "event": "ambulance_approaching",
                    "data": {
                        "trip_id": trip.id,
                        "ambulance_identifier": ambulance.vehicle_number,
                        "latitude": payload.latitude,
                        "longitude": payload.longitude,
                        "heading_degrees": heading_deg,
                        "direction": direction,
                        "approaching": dest_name,
                        "eta_minutes": current_eta,
                        "severity": trip.severity,
                        "distance_to_destination_km": round(dist_to_dest, 2),
                    }
                })
                logger.info(
                    f"Traffic proximity alert: trip {trip.id} ambulance {ambulance.vehicle_number} "
                    f"is {dist_to_dest:.2f}km from destination"
                )

    return {"message": "GPS updated successfully", "eta_minutes": current_eta}

# ----------------------------------------------------
# HOSPITAL ENDPOINTS
# ----------------------------------------------------
@app.get(f"{settings.API_V1_STR}/hospital/trips", response_model=List[dict])
def get_hospital_incoming_trips(current_user: User = Depends(require_role([UserRole.HOSPITAL, UserRole.ADMIN])), db: Session = Depends(get_db)):
    # ADMIN may view all hospitals; HOSPITAL role is scoped to their own hospital only
    if current_user.role == UserRole.ADMIN:
        active_statuses = [
            TripStatus.HOSPITAL_SELECTED, TripStatus.EN_ROUTE_TO_HOSPITAL, TripStatus.AT_HOSPITAL
        ]
        trips = db.query(Trip).filter(Trip.status.in_(active_statuses)).all()
        return [enrich_trip(t, db) for t in trips]

    h_staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == current_user.id).first()
    if not h_staff:
        raise HTTPException(status_code=403, detail="No hospital association found for this account")
    hospital_id = h_staff.hospital_id

    active_statuses = [
        TripStatus.HOSPITAL_SELECTED, TripStatus.EN_ROUTE_TO_HOSPITAL, TripStatus.AT_HOSPITAL
    ]
    trips = db.query(Trip).filter(
        Trip.hospital_id == hospital_id,
        Trip.status.in_(active_statuses)
    ).all()

    return [enrich_trip(t, db) for t in trips]

@app.get(f"{settings.API_V1_STR}/hospital/status", response_model=HospitalOut)
def get_hospital_status(current_user: User = Depends(require_role([UserRole.HOSPITAL, UserRole.ADMIN])), db: Session = Depends(get_db)):
    """Returns the authenticated hospital's current status (beds, readiness)."""
    h_staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == current_user.id).first()
    if not h_staff:
        raise HTTPException(status_code=403, detail="No hospital association found for this account")
    hospital = db.query(Hospital).filter(Hospital.id == h_staff.hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital record not found")
    return hospital

@app.post(f"{settings.API_V1_STR}/hospital/status", response_model=HospitalOut)
def update_hospital_status(req: HospitalStatusUpdate, current_user: User = Depends(require_role([UserRole.HOSPITAL, UserRole.ADMIN])), db: Session = Depends(get_db)):
    h_staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == current_user.id).first()
    if not h_staff:
        raise HTTPException(status_code=403, detail="No hospital association found for this account")
    hospital_id = h_staff.hospital_id

    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital record not found")

    if req.available_beds is not None:
        hospital.available_beds = req.available_beds
    if req.is_ready is not None:
        hospital.is_ready = req.is_ready

    db.commit()
    db.refresh(hospital)
    return hospital

# ----------------------------------------------------
# TRAFFIC SUPPORT ENDPOINTS
# ----------------------------------------------------
@app.get(f"{settings.API_V1_STR}/traffic/corridors", response_model=List[dict])
def get_active_traffic_corridors(current_user: User = Depends(require_role([UserRole.TRAFFIC, UserRole.ADMIN])), db: Session = Depends(get_db)):
    """
    Returns active emergency ambulance corridors.
    EXCLUDES all patient names, phones, diagnosis to enforce privacy strictly.
    """
    active_statuses = [
        TripStatus.ASSIGNED, TripStatus.EN_ROUTE_TO_PICKUP, TripStatus.AT_PICKUP,
        TripStatus.TRANSPORTING, TripStatus.EN_ROUTE_TO_HOSPITAL
    ]
    trips = db.query(Trip).filter(Trip.status.in_(active_statuses)).all()

    corridors = []
    for t in trips:
        amb_number = t.assigned_ambulance.vehicle_number if t.assigned_ambulance else "AMB-UNKNOWN"
        lat = t.assigned_driver.current_lat if t.assigned_driver else t.pickup_lat
        lng = t.assigned_driver.current_lng if t.assigned_driver else t.pickup_lng
        corridors.append({
            "trip_id": t.id,
            "ambulance_identifier": amb_number,
            "status": t.status,
            "severity": t.severity,
            "current_lat": lat,
            "current_lng": lng,
            # M-4: pickup_address removed — traffic must not receive patient location PII
            "destination_address": t.destination_address or "Hospital En-Route",
            "eta_minutes": t.estimated_hospital_eta or t.estimated_pickup_eta or 5,
            "traffic_clearance_required": True if t.severity in ["CRITICAL", "HIGH"] else False
        })
    return corridors

# ----------------------------------------------------
# HOSPITALS PUBLIC LIST
# ----------------------------------------------------
@app.get(f"{settings.API_V1_STR}/hospitals", response_model=List[dict])
def get_all_hospitals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns all hospitals for map display and hospital selection.
    Accessible to all authenticated users.
    Excludes any patient/trip private data.
    """
    hospitals = db.query(Hospital).all()
    return [
        {
            "id": h.id,
            "name": h.name,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "address": h.address,
            "is_ready": h.is_ready,
            "available_beds": h.available_beds,
            "trauma_level": h.trauma_level,
        }
        for h in hospitals
    ]

# ----------------------------------------------------
# ADMIN CONTROL ENDPOINTS
# ----------------------------------------------------
@app.get(f"{settings.API_V1_STR}/admin/overview", response_model=dict)
def get_admin_overview(current_user: User = Depends(require_role([UserRole.ADMIN])), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    active_trips = db.query(Trip).filter(Trip.status.notin_([TripStatus.COMPLETED, TripStatus.FAILED, TripStatus.CANCELLED])).count()
    on_duty_drivers = db.query(Driver).filter(Driver.is_on_duty == True).count()
    total_ambulances = db.query(Ambulance).filter(Ambulance.is_active == True).count()
    total_hospitals = db.query(Hospital).count()

    recent_trips = db.query(Trip).order_by(Trip.created_at.desc()).limit(10).all()

    return {
        "metrics": {
            "total_users": total_users,
            "active_trips": active_trips,
            "on_duty_drivers": on_duty_drivers,
            "total_ambulances": total_ambulances,
            "total_hospitals": total_hospitals
        },
        "recent_trips": [enrich_trip(t, db, include_driver_phone=True) for t in recent_trips]
    }

# ----------------------------------------------------
# ML PREDICTION ENDPOINT
# ----------------------------------------------------
@app.post(f"{settings.API_V1_STR}/ml/predict", response_model=PredictDelayResponse)
def predict_delay_endpoint(req: PredictDelayRequest,
                           current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HOSPITAL, UserRole.TRAFFIC, UserRole.DRIVER]))):
    """M-6: ML prediction requires authentication. Allowed roles: ADMIN, HOSPITAL, TRAFFIC, DRIVER."""
    res = predict_ambulance_delay(
        distance_km=req.osrm_distance_km,
        osrm_duration_min=req.osrm_duration_min,
        severity=req.severity
    )
    return res

# ----------------------------------------------------
# WEBSOCKET ENDPOINTS — all require JWT auth via ?token=<jwt>
# ----------------------------------------------------

@app.websocket("/ws/tracking/{trip_id}")
async def websocket_tracking(websocket: WebSocket, trip_id: int, db: Session = Depends(get_db)):
    """
    Patient live ambulance tracking.
    Auth: valid JWT + PATIENT role + trip.patient_id == authenticated user.
    """
    await websocket.accept()
    user = await _ws_get_user(websocket, db)
    if user is None:
        return  # already closed with 4001

    # Role check — patients and admins may track; also allow DRIVER/HOSPITAL for operational use
    allowed_roles = {UserRole.PATIENT, UserRole.DRIVER, UserRole.HOSPITAL, UserRole.ADMIN}
    if user.role not in allowed_roles:
        await websocket.close(code=4003, reason="Role not permitted to access tracking channel")
        return

    # Ownership check for patients — a patient may only track their own trip
    if user.role == UserRole.PATIENT:
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if not trip or trip.patient_id != user.id:
            await websocket.close(code=4003, reason="Not authorized to track this trip")
            return

    manager.trip_connections.setdefault(trip_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_trip(trip_id, websocket)


@app.websocket("/ws/driver/{driver_id}")
async def websocket_driver(websocket: WebSocket, driver_id: int, db: Session = Depends(get_db)):
    """
    Driver incoming-request channel.
    Auth: valid JWT + DRIVER role + authenticated user's Driver.id == driver_id.
    """
    await websocket.accept()
    user = await _ws_get_user(websocket, db)
    if user is None:
        return

    if user.role != UserRole.DRIVER:
        await websocket.close(code=4003, reason="Only drivers may access a driver channel")
        return

    driver = db.query(Driver).filter(Driver.user_id == user.id).first()
    if not driver or driver.id != driver_id:
        await websocket.close(code=4003, reason="Driver channel ID does not match your profile")
        return

    manager.driver_connections.setdefault(driver_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_driver(driver_id, websocket)


@app.websocket("/ws/hospital/{hospital_id}")
async def websocket_hospital(websocket: WebSocket, hospital_id: int, db: Session = Depends(get_db)):
    """
    Hospital incoming ambulance feed.
    Auth: valid JWT + HOSPITAL role + HospitalStaff.hospital_id == hospital_id.
    """
    await websocket.accept()
    user = await _ws_get_user(websocket, db)
    if user is None:
        return

    if user.role != UserRole.HOSPITAL:
        await websocket.close(code=4003, reason="Only hospital staff may access a hospital channel")
        return

    h_staff = db.query(HospitalStaff).filter(HospitalStaff.user_id == user.id).first()
    if not h_staff or h_staff.hospital_id != hospital_id:
        await websocket.close(code=4003, reason="Hospital channel ID does not match your hospital association")
        return

    manager.hospital_connections.setdefault(hospital_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_hospital(hospital_id, websocket)


@app.websocket("/ws/traffic")
async def websocket_traffic(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    Traffic support operational corridor feed.
    Auth: valid JWT + TRAFFIC or ADMIN role.
    """
    await websocket.accept()
    user = await _ws_get_user(websocket, db)
    if user is None:
        return

    if user.role not in {UserRole.TRAFFIC, UserRole.ADMIN}:
        await websocket.close(code=4003, reason="Only traffic support or admin may access the traffic channel")
        return

    manager.traffic_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_traffic(websocket)


@app.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    Admin operations channel.
    Auth: valid JWT + ADMIN role only.
    """
    await websocket.accept()
    user = await _ws_get_user(websocket, db)
    if user is None:
        return

    if user.role != UserRole.ADMIN:
        await websocket.close(code=4003, reason="Only admins may access the admin channel")
        return

    manager.admin_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)
