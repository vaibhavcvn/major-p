import pytest
from app.ml import predict_ambulance_delay, get_risk_level

def test_risk_level_thresholds():
    assert get_risk_level(1.5) == "LOW"
    assert get_risk_level(4.2) == "MEDIUM"
    assert get_risk_level(8.0) == "HIGH"
    assert get_risk_level(15.0) == "CRITICAL"

def test_predict_ambulance_delay():
    res = predict_ambulance_delay(
        distance_km=10.0,
        osrm_duration_min=15.0,
        severity="HIGH"
    )
    assert "predicted_delay_minutes" in res
    assert "delay_risk_level" in res
    assert res["delay_risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert res["confidence_score"] > 0.5
