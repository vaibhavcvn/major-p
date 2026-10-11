# Architecture Specification - Smart Ambulance System

## System Overview
The Smart Ambulance platform is a decoupled client-server web system designed for ultra-low latency emergency response management, dynamic route computation, real-time geolocation streaming, and ML-assisted delay prediction.

```
                    +-------------------------------------------------+
                    |               Web Browsers (Clients)            |
                    |  (Patient, Driver, Hospital, Traffic, Admin)    |
                    +-----------------------+-------------------------+
                                            |
                                  HTTP REST | WebSockets
                                            v
                    +-------------------------------------------------+
                    |              FastAPI Application Server         |
                    |  - REST Endpoints (Auth, Booking, State, ML)    |
                    |  - ConnectionManager (WebSocket Gateway)        |
                    |  - Dispatch Engine & Lock Manager               |
                    |  - Delay Predictor (Scikit-Learn Joblib)        |
                    +-----------------------+-------------------------+
                                            |
                    +-----------------------+-------------------------+
                    |                                                 |
                    v                                                 v
        +-----------------------+                         +-----------------------+
        |  PostgreSQL / SQLite  |                         |  External Map APIs    |
        |  - Users & Roles      |                         |  - OpenStreetMap      |
        |  - Ambulances & Fleet |                         |  - OSRM Routing       |
        |  - Active Trips & GPS |                         |  - Nominatim Geocode  |
        +-----------------------+                         +-----------------------+
```

---

## Technical Stack

| Layer | Technology | Key Details |
|---|---|---|
| **Frontend UI** | Next.js 14+ / React / TypeScript | App Router, Tailwind CSS, Lucide icons, Recharts |
| **Map Rendering** | Leaflet / OpenStreetMap | Canvas rendering, customized dark tiles, dynamic markers |
| **Geocoding & Route** | Nominatim & OSRM Engine | Nominatim for search, OSRM for polyline & duration |
| **Backend API** | Python 3.13 / FastAPI | Asynchronous endpoints, Pydantic schemas, Dependency Injection |
| **Database** | PostgreSQL / SQLite + SQLAlchemy 2.0 | Haversine distance calculations, Alembic migrations |
| **Realtime Gateway** | FastAPI WebSockets | Multi-room broadcasting, connection state recovery |
| **Machine Learning** | Scikit-Learn / Joblib | Random Forest model for delay & risk scoring |
| **Testing** | Pytest & Playwright | Automated backend API suite & E2E browser tests |

---

## Data Model ERD

```
User (id, email, password_hash, role, name, phone)
  |-- Driver (id, user_id, license_number, is_on_duty, current_lat, current_lng)
  |     |-- Ambulance (id, driver_id, vehicle_number, type, is_active)
  |-- HospitalStaff (id, user_id, hospital_id, department)

Hospital (id, name, latitude, longitude, total_beds, available_beds, trauma_level, phone)

Trip (id, patient_id, assigned_driver_id, assigned_ambulance_id, hospital_id, status, severity,
      pickup_lat, pickup_lng, pickup_address, destination_lat, destination_lng, destination_address,
      estimated_pickup_eta, estimated_hospital_eta, predicted_delay_minutes, delay_risk_level)

DispatchRequest (id, trip_id, driver_id, status, distance_km, requested_at, responded_at, expires_at)

GPSLocation (id, trip_id, driver_id, ambulance_id, latitude, longitude, speed, heading, accuracy, recorded_at)

TrafficAlert (id, trip_id, ambulance_id, corridor_name, current_junction, status, requested_at)
```

---

## Trip State Machine Matrix

```
       +--------------+
       |  REQUESTED   |
       +-------+------+
               |
               v
       +--------------+  No driver -> +------------+
       |  SEARCHING   +-------------->|   FAILED   |
       +-------+------+               +------------+
               |
               v
       +--------------+ Driver rejects / timeout
       |DRIVER_REQ'TD +-------------------------------+
       +-------+------+                               |
               | Driver accepts                       v
               v                             (retry next driver)
       +--------------+
       |   ASSIGNED   |
       +-------+------+
               | Driver departs
               v
       +--------------+
       |EN_ROUTE_PICKUP|
       +-------+------+
               | Driver arrives
               v
       +--------------+
       |  AT_PICKUP   |
       +-------+------+
               | Patient loaded
               v
       +--------------+
       | TRANSPORTING |
       +-------+------+
               | Hospital selected
               v
       +--------------+
       |EN_ROUTE_HOSP |
       +-------+------+
               | Arrives hospital
               v
       +--------------+
       | AT_HOSPITAL  |
       +-------+------+
               | Completed
               v
       +--------------+
       |  COMPLETED   |
       +--------------+
```

---

## Realtime WebSocket Protocol

Channels:
- `/ws/tracking/{trip_id}` (Patient & active trip observers)
- `/ws/driver/{driver_id}` (Driver dispatch request stream)
- `/ws/hospital/{hospital_id}` (Hospital incoming telemetry stream)
- `/ws/traffic` (Traffic support corridor alerts)
- `/ws/admin` (Admin control room global feed)

Payload structure standard:
```json
{
  "event": "ambulance_location",
  "data": {
    "trip_id": 101,
    "latitude": 12.9716,
    "longitude": 77.5946,
    "speed": 45.2,
    "heading": 180,
    "eta_minutes": 8,
    "timestamp": "2026-10-06T00:35:00Z"
  }
}
```

---

## Privacy & Security Model (RBAC)

1. **Patient**: Can only view their own trips and live location of their assigned ambulance.
2. **Driver**: Can view assigned trip details, navigation routes, and update trip status/GPS.
3. **Hospital**: Can view incoming ambulances, medical severity, ETA, but NO unnecessary private patient contact info.
4. **Traffic Control**: Receives ambulance ID, current junction, direction, ETA. Strictly zero access to patient personal info, names, or diagnosis.
5. **Admin**: Operational dashboard overview, fleet management, analytics.
