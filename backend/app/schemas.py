import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator

# ── coordinate validators (M-1) ─────────────────────────────────────────────
def _validate_lat(v: float) -> float:
    if not (-90.0 <= v <= 90.0):
        raise ValueError(f"Latitude must be between -90 and 90, got {v}")
    return v

def _validate_lng(v: float) -> float:
    if not (-180.0 <= v <= 180.0):
        raise ValueError(f"Longitude must be between -180 and 180, got {v}")
    return v


# User & Auth Schemas
class UserRegister(BaseModel):
    email: EmailStr
    # M-2: minimum 8 characters
    password: str = Field(..., min_length=8,
                          description="Password must be at least 8 characters")
    full_name: str
    role: str = "PATIENT"
    phone: Optional[str] = None
    license_number: Optional[str] = None # required if DRIVER

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str
    driver_id: Optional[int] = None      # populated for DRIVER role only
    hospital_id: Optional[int] = None    # populated for HOSPITAL role only

class UserOut(BaseModel):
    id: int
    email: str
    role: str
    full_name: str
    phone: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True

# Driver Schemas
class DriverStatusUpdate(BaseModel):
    is_on_duty: bool

class DriverLocationUpdate(BaseModel):
    latitude: float
    longitude: float

class DriverOut(BaseModel):
    id: int
    user_id: int
    license_number: str
    is_on_duty: bool
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    last_location_update: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

# Ambulance Schemas
class AmbulanceOut(BaseModel):
    id: int
    driver_id: Optional[int] = None
    vehicle_number: str
    type: str
    is_active: bool
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None

    class Config:
        from_attributes = True

# Hospital Schemas
class HospitalOut(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    address: str
    total_beds: int
    available_beds: int
    trauma_level: int
    is_ready: bool
    phone: Optional[str] = None

    class Config:
        from_attributes = True

class HospitalStatusUpdate(BaseModel):
    available_beds: Optional[int] = None
    is_ready: Optional[bool] = None

# Trip Schemas
class TripCreate(BaseModel):
    pickup_address: str
    # M-1: coordinate range validation
    pickup_lat: float = Field(..., ge=-90.0, le=90.0,
                              description="Latitude must be between -90 and 90")
    pickup_lng: float = Field(..., ge=-180.0, le=180.0,
                              description="Longitude must be between -180 and 180")
    severity: str = "HIGH" # CRITICAL, HIGH, MEDIUM, LOW

class TripStatusUpdate(BaseModel):
    status: str

class TripOut(BaseModel):
    id: int
    patient_id: int
    assigned_driver_id: Optional[int] = None
    assigned_ambulance_id: Optional[int] = None
    hospital_id: Optional[int] = None
    status: str
    severity: str
    pickup_address: str
    pickup_lat: float
    pickup_lng: float
    destination_address: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    estimated_pickup_eta: Optional[int] = None
    estimated_hospital_eta: Optional[int] = None
    predicted_delay_minutes: Optional[float] = None
    delay_risk_level: Optional[str] = None
    distance_km: Optional[float] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    # Nested detail for UI
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    ambulance_plate: Optional[str] = None
    hospital_name: Optional[str] = None
    driver_lat: Optional[float] = None
    driver_lng: Optional[float] = None

    class Config:
        from_attributes = True

# Dispatch Schemas
class DispatchRequestOut(BaseModel):
    id: int
    trip_id: int
    driver_id: int
    status: str
    distance_km: float
    requested_at: datetime.datetime
    expires_at: datetime.datetime
    trip: TripOut

    class Config:
        from_attributes = True

# GPS Update Payload
class GPSUpdate(BaseModel):
    trip_id: int
    # M-1: coordinate range validation
    latitude: float = Field(..., ge=-90.0, le=90.0,
                            description="Latitude must be between -90 and 90")
    longitude: float = Field(..., ge=-180.0, le=180.0,
                             description="Longitude must be between -180 and 180")
    speed: Optional[float] = 0.0
    heading: Optional[float] = 0.0
    accuracy: Optional[float] = 0.0
    timestamp: Optional[str] = None

# Delay Prediction Schema
class PredictDelayRequest(BaseModel):
    pickup_lat: float
    pickup_lng: float
    dest_lat: float
    dest_lng: float
    osrm_distance_km: float
    osrm_duration_min: float
    severity: str = "HIGH"

class PredictDelayResponse(BaseModel):
    predicted_delay_minutes: float
    total_estimated_trip_minutes: float
    delay_risk_level: str
    confidence_score: float
