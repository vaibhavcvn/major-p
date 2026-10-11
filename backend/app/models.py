import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class UserRole:
    PATIENT = "PATIENT"
    DRIVER = "DRIVER"
    HOSPITAL = "HOSPITAL"
    TRAFFIC = "TRAFFIC"
    ADMIN = "ADMIN"

class TripStatus:
    REQUESTED = "REQUESTED"
    SEARCHING = "SEARCHING"
    DRIVER_REQUESTED = "DRIVER_REQUESTED"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE_TO_PICKUP = "EN_ROUTE_TO_PICKUP"
    AT_PICKUP = "AT_PICKUP"
    TRANSPORTING = "TRANSPORTING"
    HOSPITAL_SELECTED = "HOSPITAL_SELECTED"
    EN_ROUTE_TO_HOSPITAL = "EN_ROUTE_TO_HOSPITAL"
    AT_HOSPITAL = "AT_HOSPITAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class DispatchStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default=UserRole.PATIENT)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    driver_profile = relationship("Driver", back_populates="user", uselist=False, cascade="all, delete-orphan")
    hospital_staff_profile = relationship("HospitalStaff", back_populates="user", uselist=False, cascade="all, delete-orphan")
    trips_requested = relationship("Trip", back_populates="patient", foreign_keys="Trip.patient_id")

class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    license_number = Column(String, nullable=False)
    is_on_duty = Column(Boolean, default=False)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    last_location_update = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="driver_profile")
    ambulance = relationship("Ambulance", back_populates="driver", uselist=False)
    dispatch_requests = relationship("DispatchRequest", back_populates="driver")
    assigned_trips = relationship("Trip", back_populates="assigned_driver", foreign_keys="Trip.assigned_driver_id")

class Ambulance(Base):
    __tablename__ = "ambulances"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), unique=True, nullable=True)
    vehicle_number = Column(String, unique=True, nullable=False)
    type = Column(String, default="ADVANCED_LIFE_SUPPORT")
    is_active = Column(Boolean, default=True)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    driver = relationship("Driver", back_populates="ambulance")
    assigned_trips = relationship("Trip", back_populates="assigned_ambulance")

class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String, nullable=False)
    total_beds = Column(Integer, default=50)
    available_beds = Column(Integer, default=20)
    trauma_level = Column(Integer, default=1)
    is_ready = Column(Boolean, default=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    staff = relationship("HospitalStaff", back_populates="hospital")
    trips = relationship("Trip", back_populates="hospital")

class HospitalStaff(Base):
    __tablename__ = "hospital_staff"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False)
    department = Column(String, default="Emergency")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="hospital_staff_profile")
    hospital = relationship("Hospital", back_populates="staff")

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    assigned_ambulance_id = Column(Integer, ForeignKey("ambulances.id"), nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)

    status = Column(String, nullable=False, default=TripStatus.REQUESTED)
    severity = Column(String, nullable=False, default="HIGH")

    pickup_address = Column(String, nullable=False)
    pickup_lat = Column(Float, nullable=False)
    pickup_lng = Column(Float, nullable=False)

    destination_address = Column(String, nullable=True)
    destination_lat = Column(Float, nullable=True)
    destination_lng = Column(Float, nullable=True)

    estimated_pickup_eta = Column(Integer, nullable=True)  # Minutes
    estimated_hospital_eta = Column(Integer, nullable=True) # Minutes
    predicted_delay_minutes = Column(Float, nullable=True)
    delay_risk_level = Column(String, nullable=True, default="LOW") # LOW, MEDIUM, HIGH, CRITICAL
    distance_km = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    patient = relationship("User", back_populates="trips_requested", foreign_keys=[patient_id])
    assigned_driver = relationship("Driver", back_populates="assigned_trips", foreign_keys=[assigned_driver_id])
    assigned_ambulance = relationship("Ambulance", back_populates="assigned_trips")
    hospital = relationship("Hospital", back_populates="trips")
    dispatch_requests = relationship("DispatchRequest", back_populates="trip", cascade="all, delete-orphan")
    gps_locations = relationship("GPSLocation", back_populates="trip", cascade="all, delete-orphan")
    traffic_alerts = relationship("TrafficAlert", back_populates="trip", cascade="all, delete-orphan")

class DispatchRequest(Base):
    __tablename__ = "dispatch_requests"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default=DispatchStatus.PENDING)
    distance_km = Column(Float, nullable=False, default=0.0)
    requested_at = Column(DateTime, default=datetime.datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    trip = relationship("Trip", back_populates="dispatch_requests")
    driver = relationship("Driver", back_populates="dispatch_requests")

class GPSLocation(Base):
    __tablename__ = "gps_locations"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    ambulance_id = Column(Integer, ForeignKey("ambulances.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True, default=0.0)
    heading = Column(Float, nullable=True, default=0.0)
    accuracy = Column(Float, nullable=True, default=0.0)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    trip = relationship("Trip", back_populates="gps_locations")

class TrafficAlert(Base):
    __tablename__ = "traffic_alerts"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    ambulance_id = Column(Integer, ForeignKey("ambulances.id"), nullable=False)
    corridor_name = Column(String, nullable=False)
    current_junction = Column(String, nullable=False)
    status = Column(String, default="ACTIVE")
    requested_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    trip = relationship("Trip", back_populates="traffic_alerts")

class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    event_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
