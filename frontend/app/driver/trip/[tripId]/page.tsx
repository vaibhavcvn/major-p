"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { Ambulance, MapPin, Navigation, Radio, CheckCircle, ArrowRight, Building2, AlertCircle } from "lucide-react";
import { api } from "../../../../lib/api";
import type { HospitalMarker } from "../../../../components/LeafletMap";

const LeafletMap = dynamic(() => import("../../../../components/LeafletMap"), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-slate-900 animate-pulse rounded-2xl flex items-center justify-center text-slate-500">Loading Navigation Map...</div>
});

export default function DriverTripPage() {
  const params = useParams();
  const router = useRouter();
  const tripId = parseInt(params.tripId as string, 10);

  const [trip, setTrip] = useState<any>(null);
  const [currentGPS, setCurrentGPS] = useState<[number, number] | null>(null);
  const [heading, setHeading] = useState(0);
  const [speed, setSpeed] = useState(0);
  const [gpsActive, setGpsActive] = useState(false);
  const [gpsError, setGpsError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [hospitals, setHospitals] = useState<HospitalMarker[]>([]);

  const watchIdRef = useRef<number | null>(null);

  // Load initial trip details
  const loadTrip = async () => {
    try {
      const data = await api.getPatientTrip(tripId);
      setTrip(data);
    } catch (err: any) {
      alert(`Trip load error: ${err.message}`);
    }
  };

  useEffect(() => {
    if (tripId) loadTrip();
    // Load hospitals for map markers
    api.getHospitals()
      .then((data: any[]) =>
        setHospitals(data.map((h: any) => ({
          id: h.id, name: h.name, lat: h.latitude, lng: h.longitude,
          address: h.address, is_ready: h.is_ready, available_beds: h.available_beds,
        })))
      )
      .catch(() => {});
  }, [tripId]);

  // Real Browser GPS Watcher (navigator.geolocation.watchPosition)
  useEffect(() => {
    if (!tripId || !navigator.geolocation) {
      setGpsError("Geolocation API is not supported by your browser");
      return;
    }

    setGpsActive(true);

    watchIdRef.current = navigator.geolocation.watchPosition(
      async (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const h = position.coords.heading || 0;
        const s = position.coords.speed || 0;

        setCurrentGPS([lat, lng]);
        setHeading(h);
        setSpeed(s);

        try {
          await api.sendGPSUpdate({
            trip_id: tripId,
            latitude: lat,
            longitude: lng,
            speed: s,
            heading: h,
            accuracy: position.coords.accuracy || 0,
            timestamp: new Date(position.timestamp).toISOString(),
          });
        } catch (err: any) {
          console.error("Error pushing real GPS:", err);
        }
      },
      (error) => {
        console.warn("Real browser GPS warning (using default location fallback):", error.message);
        setGpsError(`GPS Notice: ${error.message}`);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 1000,
      }
    );

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, [tripId]);

  const updateStatus = async (nextStatus: string) => {
    try {
      setActionLoading(true);
      const res = await api.updateTripStatus(tripId, nextStatus);
      setTrip(res.trip);
      if (nextStatus === "COMPLETED") {
        alert("Trip completed successfully!");
        router.push("/driver");
      }
    } catch (err: any) {
      alert(`Status update failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  if (!trip) {
    return (
      <div className="py-16 text-center text-slate-400 text-sm">
        Initializing Navigation Console...
      </div>
    );
  }

  const pickupPos: [number, number] = [trip.pickup_lat, trip.pickup_lng];
  const hospitalPos: [number, number] | null = trip.destination_lat && trip.destination_lng ? [trip.destination_lat, trip.destination_lng] : null;

  return (
    <div className="space-y-6 py-2">

      {/* Top Navigation Bar */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-full font-bold text-xs uppercase tracking-wider">
              {trip.status.replace(/_/g, " ")}
            </span>
            <span className="text-slate-400 text-xs font-mono">TRIP #{trip.id}</span>
          </div>
          <h1 className="text-2xl font-extrabold text-white mt-1">Driver Live Navigation Console</h1>
        </div>

        {/* Real Browser GPS Status */}
        <div className="flex items-center gap-3 bg-slate-950 px-4 py-2.5 rounded-2xl border border-slate-800 text-xs">
          <Radio className={`w-4 h-4 ${gpsActive ? "text-emerald-400 animate-ping" : "text-slate-500"}`} />
          <div>
            <p className="font-bold text-slate-200">{gpsActive ? "Browser GPS Active" : "GPS Standing By"}</p>
            <p className="text-[10px] text-slate-400 font-mono">
              {currentGPS ? `${currentGPS[0].toFixed(4)}, ${currentGPS[1].toFixed(4)}` : "Acquiring Fix..."}
            </p>
          </div>
        </div>
      </div>

      {gpsError && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {gpsError}
        </div>
      )}

      {/* Map + Controls Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Navigation Map */}
        <div className="lg:col-span-8 bg-slate-900/80 border border-slate-800 rounded-3xl p-4 shadow-xl flex flex-col h-[520px]">
          <div className="flex items-center justify-between px-2 pb-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-2">
              <Navigation className="w-4 h-4 text-amber-400" />
              OSRM Driver Turn-by-Turn Route
            </span>
            <span className="font-mono text-emerald-400">SPEED: {(speed * 3.6).toFixed(1)} KM/H</span>
          </div>
          <div className="flex-1 rounded-2xl overflow-hidden">
            <LeafletMap
              center={currentGPS || pickupPos}
              ambulancePos={currentGPS || pickupPos}
              pickupPos={pickupPos}
              hospitalPos={hospitalPos}
              hospitals={hospitals}
              heading={heading}
              zoom={15}
            />
          </div>
        </div>

        {/* Action Controls */}
        <div className="lg:col-span-4 space-y-6">

          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-6">
            <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Trip Workflow Controls</h3>

            {/* Action Buttons based on current state */}
            <div className="space-y-3">

              {trip.status === "ASSIGNED" && (
                <button
                  onClick={() => updateStatus("EN_ROUTE_TO_PICKUP")}
                  disabled={actionLoading}
                  className="w-full py-4 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-amber-600/30 flex items-center justify-center gap-2"
                >
                  <Navigation className="w-5 h-5" />
                  START EN-ROUTE TO PICKUP
                </button>
              )}

              {trip.status === "EN_ROUTE_TO_PICKUP" && (
                <button
                  onClick={() => updateStatus("AT_PICKUP")}
                  disabled={actionLoading}
                  className="w-full py-4 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-blue-600/30 flex items-center justify-center gap-2"
                >
                  <MapPin className="w-5 h-5" />
                  MARK ARRIVED AT PICKUP
                </button>
              )}

              {trip.status === "AT_PICKUP" && (
                <button
                  onClick={() => updateStatus("TRANSPORTING")}
                  disabled={actionLoading}
                  className="w-full py-4 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-purple-600/30 flex items-center justify-center gap-2 animate-emergency-pulse"
                >
                  <Ambulance className="w-5 h-5" />
                  PATIENT PICKED UP — EN ROUTE TO HOSPITAL
                </button>
              )}

              {(trip.status === "EN_ROUTE_TO_HOSPITAL" || trip.status === "HOSPITAL_SELECTED") && (
                <button
                  onClick={() => updateStatus("AT_HOSPITAL")}
                  disabled={actionLoading}
                  className="w-full py-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2"
                >
                  <Building2 className="w-5 h-5" />
                  MARK ARRIVED AT HOSPITAL
                </button>
              )}

              {trip.status === "AT_HOSPITAL" && (
                <button
                  onClick={() => updateStatus("COMPLETED")}
                  disabled={actionLoading}
                  className="w-full py-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2"
                >
                  <CheckCircle className="w-5 h-5" />
                  COMPLETE TRIP & RETURN AVAILABLE
                </button>
              )}

            </div>

            {/* Destination Info */}
            <div className="border-t border-slate-800 pt-4 space-y-2 text-xs">
              <p className="text-slate-500 uppercase font-mono">Current Destination</p>
              {trip.destination_address ? (
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <p className="font-bold text-white text-sm">{trip.hospital_name || "Emergency Hospital"}</p>
                  <p className="text-slate-400 mt-0.5">{trip.destination_address}</p>
                </div>
              ) : (
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <p className="font-bold text-white text-sm">Pickup Point</p>
                  <p className="text-slate-400 mt-0.5">{trip.pickup_address}</p>
                </div>
              )}
            </div>

          </div>

        </div>

      </div>

    </div>
  );
}
