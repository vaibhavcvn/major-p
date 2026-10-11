import math
import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, not_

from app.models import (
    User, Driver, Ambulance, Trip, DispatchRequest,
    TripStatus, DispatchStatus
)
from app.websocket import manager

logger = logging.getLogger("smart_ambulance.dispatch")
def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0 # Radius of Earth in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def find_eligible_drivers(db: Session, pickup_lat: float, pickup_lng: float, excluded_driver_ids: list[int] = None) -> list[tuple[Driver, Ambulance, float]]:
    """
    Find on-duty drivers with active ambulances who are NOT currently on an active trip.
    Returns list of tuples: (Driver, Ambulance, distance_km) sorted by distance.
    """
    if excluded_driver_ids is None:
        excluded_driver_ids = []

    # Get driver IDs currently on active trips
    active_statuses = [
        TripStatus.ASSIGNED, TripStatus.EN_ROUTE_TO_PICKUP, TripStatus.AT_PICKUP,
        TripStatus.TRANSPORTING, TripStatus.HOSPITAL_SELECTED, TripStatus.EN_ROUTE_TO_HOSPITAL,
        TripStatus.AT_HOSPITAL
    ]
    busy_driver_ids_query = db.query(Trip.assigned_driver_id).filter(
        Trip.assigned_driver_id.isnot(None),
        Trip.status.in_(active_statuses)
    ).all()
    busy_driver_ids = [r[0] for r in busy_driver_ids_query if r[0] is not None]

    # Query on-duty drivers who are not busy and not excluded
    drivers = db.query(Driver).join(Ambulance, Driver.id == Ambulance.driver_id).filter(
        Driver.is_on_duty == True,
        Ambulance.is_active == True,
        not_(Driver.id.in_(busy_driver_ids)),
        not_(Driver.id.in_(excluded_driver_ids))
    ).all()

    driver_candidates = []
    for d in drivers:
        amb = d.ambulance
        # M-5: Use driver or ambulance GPS only — never fall back to pickup coords.
        # A driver with no known location must NOT appear as 0 km away (nearest).
        lat = d.current_lat or (amb.current_lat if amb else None)
        lng = d.current_lng or (amb.current_lng if amb else None)
        if lat is None or lng is None:
            # Skip drivers whose location is unknown to prevent false "nearest" ranking.
            logger.debug(f"Driver {d.id} skipped: no GPS coordinates available")
            continue
        dist = haversine_distance_km(pickup_lat, pickup_lng, lat, lng)
        driver_candidates.append((d, amb, round(dist, 2)))

    # Sort candidates by distance ascending
    driver_candidates.sort(key=lambda x: x[2])
    return driver_candidates

async def dispatch_next_driver(db: Session, trip: Trip) -> bool:
    """
    Finds the next eligible driver for the trip and creates a DispatchRequest.

    H-2 concurrency protection:
    For each candidate driver (sorted by distance), we attempt to acquire a
    SELECT FOR UPDATE SKIP LOCKED on both the Driver and Ambulance rows before
    creating the DispatchRequest.  If those rows are already locked by another
    concurrent dispatch call, we skip to the next candidate.  We re-verify
    eligibility after acquiring the lock to prevent TOCTOU races.

    Sends WebSocket notification to the driver.
    Returns True if a request was sent, False if no drivers available.
    """
    # Get previously rejected/expired driver IDs for this trip
    past_requests = db.query(DispatchRequest).filter(DispatchRequest.trip_id == trip.id).all()
    excluded_driver_ids = [r.driver_id for r in past_requests]

    candidates = find_eligible_drivers(db, trip.pickup_lat, trip.pickup_lng, excluded_driver_ids=excluded_driver_ids)
    if not candidates:
        trip.status = TripStatus.FAILED
        db.commit()
        await manager.broadcast_to_trip(trip.id, {
            "event": "trip_status_changed",
            "data": {
                "trip_id": trip.id,
                "status": TripStatus.FAILED,
                "message": "No available drivers found in your area. Please retry."
            }
        })
        await manager.broadcast_admin({
            "event": "trip_status_changed",
            "data": {"trip_id": trip.id, "status": TripStatus.FAILED}
        })
        return False

    # H-2: Try each candidate in order until we can lock one exclusively
    selected_driver = None
    selected_amb = None
    dist_km = 0.0

    active_statuses = [
        TripStatus.ASSIGNED, TripStatus.EN_ROUTE_TO_PICKUP, TripStatus.AT_PICKUP,
        TripStatus.TRANSPORTING, TripStatus.HOSPITAL_SELECTED, TripStatus.EN_ROUTE_TO_HOSPITAL,
        TripStatus.AT_HOSPITAL
    ]

    for candidate_driver, candidate_amb, candidate_dist in candidates:
        # Attempt to lock the Driver row; skip if another transaction holds it
        locked_driver = (
            db.query(Driver)
            .filter(Driver.id == candidate_driver.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if locked_driver is None:
            # Another dispatch holds this driver — skip
            continue

        # Re-verify driver is still on-duty and not on an active trip after acquiring lock
        still_busy = db.query(Trip).filter(
            Trip.assigned_driver_id == locked_driver.id,
            Trip.status.in_(active_statuses)
        ).first()
        if not locked_driver.is_on_duty or still_busy:
            db.rollback()
            continue

        # Lock the Ambulance row too
        locked_amb = (
            db.query(Ambulance)
            .filter(Ambulance.driver_id == locked_driver.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if locked_amb is None or not locked_amb.is_active:
            db.rollback()
            continue

        # Both rows locked and still eligible — use this driver
        selected_driver = locked_driver
        selected_amb    = locked_amb
        dist_km         = candidate_dist
        break

    if selected_driver is None:
        # All candidates were locked/unavailable by the time we checked
        trip.status = TripStatus.FAILED
        db.commit()
        await manager.broadcast_to_trip(trip.id, {
            "event": "trip_status_changed",
            "data": {
                "trip_id": trip.id,
                "status": TripStatus.FAILED,
                "message": "No available drivers found in your area. Please retry."
            }
        })
        await manager.broadcast_admin({
            "event": "trip_status_changed",
            "data": {"trip_id": trip.id, "status": TripStatus.FAILED}
        })
        return False

    # Create DispatchRequest while the driver/ambulance rows are still locked
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=45)
    dispatch_req = DispatchRequest(
        trip_id=trip.id,
        driver_id=selected_driver.id,
        status=DispatchStatus.PENDING,
        distance_km=dist_km,
        expires_at=expires_at
    )
    db.add(dispatch_req)
    trip.status = TripStatus.DRIVER_REQUESTED
    db.commit()   # releases the FOR UPDATE locks
    db.refresh(dispatch_req)

    # Estimate initial pickup ETA based on speed 40km/h
    estimated_pickup_eta = max(1, int((dist_km / 40.0) * 60))
    trip.estimated_pickup_eta = estimated_pickup_eta
    db.commit()

    logger.info(f"Dispatched trip {trip.id} to driver {selected_driver.id} (Distance: {dist_km}km)")

    # Send WebSocket event to targeted driver
    driver_user = selected_driver.user
    driver_name = driver_user.full_name if driver_user else f"Driver #{selected_driver.id}"

    payload = {
        "event": "new_trip_request",
        "data": {
            "request_id": dispatch_req.id,
            "trip_id": trip.id,
            "pickup_address": trip.pickup_address,
            "pickup_lat": trip.pickup_lat,
            "pickup_lng": trip.pickup_lng,
            "severity": trip.severity,
            "distance_km": dist_km,
            "estimated_eta_minutes": estimated_pickup_eta,
            "expires_at": expires_at.isoformat(),
            "patient_name": trip.patient.full_name if trip.patient else "Emergency Patient"
        }
    }
    await manager.notify_driver(selected_driver.id, payload)

    # Notify patient trip is searching/offered
    await manager.broadcast_to_trip(trip.id, {
        "event": "trip_status_changed",
        "data": {
            "trip_id": trip.id,
            "status": TripStatus.DRIVER_REQUESTED,
            "message": "Dispatching nearest ambulance..."
        }
    })
    return True


async def expire_pending_requests(db: Session) -> None:
    """
    Background-safe expiry worker.

    Finds every PENDING DispatchRequest whose expires_at has passed, atomically
    transitions it to EXPIRED (using SELECT FOR UPDATE to prevent races with a
    simultaneous driver ACCEPT), then triggers redispatch for the owning trip.

    Design guarantees:
    - Each row is locked before write  →  ACCEPT can never race with EXPIRY silently.
    - An already-ACCEPTED row is skipped (status != PENDING after lock).
    - Each expired trip is re-dispatched exactly once per cycle.
    - No driver or ambulance is ever pre-reserved, so no explicit release is needed.
    """
    now = datetime.datetime.utcnow()

    # Collect IDs first (lightweight read, no lock yet)
    expired_ids = [
        row[0] for row in db.query(DispatchRequest.id).filter(
            DispatchRequest.status == DispatchStatus.PENDING,
            DispatchRequest.expires_at <= now
        ).all()
    ]

    if not expired_ids:
        return

    trips_to_redispatch = []  # collect trip objects after locking

    for req_id in expired_ids:
        # Re-fetch with row lock — prevents race with concurrent ACCEPT
        req = (
            db.query(DispatchRequest)
            .filter(DispatchRequest.id == req_id)
            .with_for_update(skip_locked=True)   # skip if ACCEPT already holds the lock
            .first()
        )
        if req is None:
            # Another session holds the lock (ACCEPT in flight) — leave it alone
            continue

        if req.status != DispatchStatus.PENDING:
            # ACCEPT or REJECT already won the race — nothing to do
            db.rollback()
            continue

        # Lock the trip row too, so ACCEPT on the same trip also blocks
        trip = (
            db.query(Trip)
            .filter(Trip.id == req.trip_id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if trip is None:
            db.rollback()
            continue

        # Only expire if trip is still waiting for a driver
        if trip.status not in (TripStatus.DRIVER_REQUESTED, TripStatus.SEARCHING):
            # Trip already moved on (ASSIGNED, FAILED, CANCELLED) — just mark the req
            req.status = DispatchStatus.EXPIRED
            req.responded_at = now
            db.commit()
            continue

        # Atomically mark expired
        req.status = DispatchStatus.EXPIRED
        req.responded_at = now
        trip.status = TripStatus.SEARCHING
        db.commit()

        logger.info(f"DispatchRequest {req.id} EXPIRED for trip {trip.id} (driver {req.driver_id})")
        trips_to_redispatch.append(trip)

    # Redispatch outside the per-row lock loop (each call commits its own transaction)
    for trip in trips_to_redispatch:
        # Refresh to get latest state after the commit above
        db.refresh(trip)
        await dispatch_next_driver(db, trip)
