import sys
import os
import logging
from sqlalchemy.orm import Session

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base, SessionLocal
from app.models import (
    User, Driver, Ambulance, Hospital, HospitalStaff, UserRole
)
from app.auth import get_password_hash
from app.ml import train_and_save_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_ambulance.seed")

def seed_db():
    logger.info("Recreating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        default_pwd = get_password_hash("password123")

        # 1. Seed Admin
        admin_user = db.query(User).filter(User.email == "admin@smartambulance.com").first()
        if not admin_user:
            admin_user = User(
                email="admin@smartambulance.com",
                password_hash=default_pwd,
                role=UserRole.ADMIN,
                full_name="Emergency Command Admin",
                phone="+1-800-555-0199"
            )
            db.add(admin_user)
            logger.info("Created Admin account: admin@smartambulance.com")

        # 2. Seed Patient
        patient_user = db.query(User).filter(User.email == "patient@smartambulance.com").first()
        if not patient_user:
            patient_user = User(
                email="patient@smartambulance.com",
                password_hash=default_pwd,
                role=UserRole.PATIENT,
                full_name="John Doe (Patient)",
                phone="+1-555-0142"
            )
            db.add(patient_user)
            logger.info("Created Patient account: patient@smartambulance.com")

        # 3. Seed Traffic Support
        traffic_user = db.query(User).filter(User.email == "traffic@smartambulance.com").first()
        if not traffic_user:
            traffic_user = User(
                email="traffic@smartambulance.com",
                password_hash=default_pwd,
                role=UserRole.TRAFFIC,
                full_name="City Traffic Control Operator",
                phone="+1-555-0188"
            )
            db.add(traffic_user)
            logger.info("Created Traffic account: traffic@smartambulance.com")

        # 4. Seed Hospitals
        hospitals_data = [
            {
                "name": "City Central Trauma Center",
                "lat": 12.9750,
                "lng": 77.6050,
                "address": "100 Emergency Ave, City Center",
                "total_beds": 60,
                "available_beds": 24,
                "trauma_level": 1,
                "phone": "+1-800-EMERGENCY-1"
            },
            {
                "name": "Metro General Emergency Hospital",
                "lat": 12.9620,
                "lng": 77.5850,
                "address": "45 Metro Boulevard",
                "total_beds": 40,
                "available_beds": 15,
                "trauma_level": 2,
                "phone": "+1-800-EMERGENCY-2"
            },
            {
                "name": "St. Jude LifeCare Hospital",
                "lat": 12.9850,
                "lng": 77.6200,
                "address": "12 North Coast Highway",
                "total_beds": 50,
                "available_beds": 18,
                "trauma_level": 1,
                "phone": "+1-800-EMERGENCY-3"
            }
        ]

        created_hospitals = []
        for h_data in hospitals_data:
            h_obj = db.query(Hospital).filter(Hospital.name == h_data["name"]).first()
            if not h_obj:
                h_obj = Hospital(
                    name=h_data["name"],
                    latitude=h_data["lat"],
                    longitude=h_data["lng"],
                    address=h_data["address"],
                    total_beds=h_data["total_beds"],
                    available_beds=h_data["available_beds"],
                    trauma_level=h_data["trauma_level"],
                    is_ready=True,
                    phone=h_data["phone"]
                )
                db.add(h_obj)
                db.flush()
                logger.info(f"Created Hospital: {h_data['name']}")
            created_hospitals.append(h_obj)

        # 5. Seed Hospital User
        hospital_user = db.query(User).filter(User.email == "hospital@smartambulance.com").first()
        if not hospital_user:
            hospital_user = User(
                email="hospital@smartambulance.com",
                password_hash=default_pwd,
                role=UserRole.HOSPITAL,
                full_name="Dr. Sarah Jenkins (ER Chief)",
                phone="+1-555-0177"
            )
            db.add(hospital_user)
            db.flush()

            h_staff = HospitalStaff(
                user_id=hospital_user.id,
                hospital_id=created_hospitals[0].id,
                department="Emergency Room"
            )
            db.add(h_staff)
            logger.info("Created Hospital account: hospital@smartambulance.com")

        # 6. Seed Drivers & Ambulances
        drivers_data = [
            {
                "email": "driver@smartambulance.com",
                "name": "Michael Vance (ALS Driver)",
                "phone": "+1-555-0111",
                "license": "LIC-AMB-001",
                "plate": "AMB-101-ALS",
                "type": "ADVANCED_LIFE_SUPPORT",
                "lat": 12.9716,
                "lng": 77.5946
            },
            {
                "email": "driver2@smartambulance.com",
                "name": "Robert Miller (BLS Driver)",
                "phone": "+1-555-0222",
                "license": "LIC-AMB-002",
                "plate": "AMB-102-BLS",
                "type": "BASIC_LIFE_SUPPORT",
                "lat": 12.9780,
                "lng": 77.6000
            }
        ]

        for d_data in drivers_data:
            d_user = db.query(User).filter(User.email == d_data["email"]).first()
            if not d_user:
                d_user = User(
                    email=d_data["email"],
                    password_hash=default_pwd,
                    role=UserRole.DRIVER,
                    full_name=d_data["name"],
                    phone=d_data["phone"]
                )
                db.add(d_user)
                db.flush()

                d_profile = Driver(
                    user_id=d_user.id,
                    license_number=d_data["license"],
                    is_on_duty=True,
                    current_lat=d_data["lat"],
                    current_lng=d_data["lng"]
                )
                db.add(d_profile)
                db.flush()

                amb = Ambulance(
                    driver_id=d_profile.id,
                    vehicle_number=d_data["plate"],
                    type=d_data["type"],
                    is_active=True,
                    current_lat=d_data["lat"],
                    current_lng=d_data["lng"]
                )
                db.add(amb)
                logger.info(f"Created Driver & Ambulance: {d_data['email']} - {d_data['plate']}")

        db.commit()
        logger.info("Database seeding completed successfully.")

        # Train ML Model
        logger.info("Training ML Ambulance Delay Prediction model...")
        train_and_save_model()
        logger.info("ML model trained and saved.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
