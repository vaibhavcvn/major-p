# Project Plan - Smart Ambulance System

## Executive Summary
The Smart Ambulance project is an intelligent emergency response and ambulance delay prediction system built from scratch. It features real-time dispatch, atomic driver acceptance, real browser geolocation tracking, OSRM routing, OpenStreetMap visuals, scikit-learn powered delay risk prediction, and role-based real-time dashboards for Patients, Drivers, Hospitals, Traffic Support, and Admin Control.

---

## Phase Breakdown

### Phase 1: Foundation & Architecture
- Setup project directory structure (`backend/` and `frontend/`).
- Configure FastAPI backend, SQLAlchemy models, PostgreSQL/SQLite engine compatibility, Alembic migrations.
- Implement User, Driver, Ambulance, Trip, DispatchRequest, Hospital, HospitalStaff, GPSLocation, TrafficAlert, EmergencyEvent models.
- Build JWT authentication, bcrypt password hashing, and Role-Based Access Control (RBAC).
- Create idempotent DB seed script with demo credentials (`admin`, `patient`, `driver`, `driver2`, `hospital`, `traffic`).

### Phase 2: Core Dispatch & State Machine
- Implement atomic Trip State Machine:
  `REQUESTED -> SEARCHING -> DRIVER_REQUESTED -> ASSIGNED -> EN_ROUTE_TO_PICKUP -> AT_PICKUP -> TRANSPORTING -> HOSPITAL_SELECTED -> EN_ROUTE_TO_HOSPITAL -> AT_HOSPITAL -> COMPLETED`
- Implement candidate driver lookup based on distance, duty status, vehicle availability.
- Dispatch request creation, atomic acceptance, rejection handling, timeout escalation, and race-condition prevention.

### Phase 3: Realtime Engine (WebSockets)
- FastAPI WebSocket connection manager supporting channels:
  - `/ws/tracking/{trip_id}` (Patient)
  - `/ws/driver/{driver_id}` (Driver)
  - `/ws/hospital/{hospital_id}` (Hospital)
  - `/ws/traffic` (Traffic Support)
  - `/ws/admin` (Admin Control)
- Realtime event distribution for dispatch requests, status changes, GPS updates, and hospital assignments.

### Phase 4: Browser GPS, Leaflet Maps & OSRM Routing
- Real browser `navigator.geolocation.watchPosition()` driver tracking engine.
- Backend GPS update endpoint with driver identity, trip assignment, and active status verification.
- OSRM route generation, Leaflet map components, Nominatim location search, and ETA computation.

### Phase 5: Role-Specific Dashboards
- **Patient Dashboard**: Pickup selection, emergency severity rating, live tracking, driver info, hospital info.
- **Driver Dashboard**: Duty toggle, incoming dispatch modal, route navigation, state transition buttons.
- **Hospital Dashboard**: Incoming emergency panel, ETA, readiness management, minimal privacy-preserving details.
- **Traffic Control**: Active green corridor overview, next junction clearance, zero patient data leakage.
- **Admin Control**: Fleet map, active trips, hospital/driver stats, delay analytics.

### Phase 6: Machine Learning Delay Prediction
- Scikit-learn training pipeline utilizing distance, OSRM duration, time of day, day of week, traffic index, historical speed.
- Pre-trained `delay_model.joblib` artifact generation.
- FastAPI ML inference endpoint returning predicted delay (minutes), risk level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and confidence rating.

### Phase 7: UI/UX Emergency Dark Aesthetic & Polish
- Emergency dark operations design with dynamic Leaflet styling, high contrast, red/orange accents.
- Responsive layouts, toast notifications, connection indicators, loading states, and REST fallbacks.

### Phase 8: Comprehensive E2E Testing & Verification
- Pytest suite for backend APIs, state machine transitions, dispatch locking, and authorization.
- TypeScript build check (`tsc --noEmit` / Next.js build).
- Playwright E2E test verifying complete end-to-end multi-role browser interaction.
