"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Siren, Clock, ArrowRight, Activity, Navigation } from "lucide-react";
import { getAuthToken } from "../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// Non-terminal trip statuses — if a trip is in one of these states, the patient
// has an active trip they should be able to track.
const ACTIVE_STATUSES = new Set([
  "REQUESTED", "SEARCHING", "DRIVER_REQUESTED", "ASSIGNED",
  "EN_ROUTE_TO_PICKUP", "AT_PICKUP", "TRANSPORTING", "HOSPITAL_SELECTED",
  "EN_ROUTE_TO_HOSPITAL", "AT_HOSPITAL",
]);

export default function PatientDashboard() {
  const [activeTrip, setActiveTrip] = useState<any>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) { setChecking(false); return; }

    // Fetch the admin overview is not appropriate here — instead, call the
    // patient's own trip list from local storage (last trip id if persisted)
    // or try to GET /patient/trip/latest if available.
    // Since the backend has no "list patient trips" endpoint, we store the
    // last trip_id in sessionStorage when booking and check it here.
    const lastTripId = sessionStorage.getItem("sa_last_trip_id");
    if (!lastTripId) { setChecking(false); return; }

    fetch(`${API_BASE}/patient/trip/${lastTripId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data && ACTIVE_STATUSES.has(data.status)) {
          setActiveTrip(data);
        }
        setChecking(false);
      })
      .catch(() => setChecking(false));
  }, []);

  return (
    <div className="space-y-8 max-w-4xl mx-auto py-4">

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <Siren className="w-8 h-8 text-red-500 animate-pulse" />
            Patient Emergency Portal
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Book an emergency ambulance or track an ongoing response.
          </p>
        </div>
        <Link
          href="/patient/book"
          className="px-6 py-3.5 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl flex items-center gap-3 transition-all shadow-xl shadow-red-600/30 hover:scale-105"
        >
          <Siren className="w-5 h-5" />
          Request Emergency Ambulance
        </Link>
      </div>

      {/* Active trip banner */}
      {checking ? (
        <div className="text-slate-500 text-xs animate-pulse">Checking for active trip...</div>
      ) : activeTrip ? (
        <div className="bg-amber-950/30 border-2 border-amber-500/50 rounded-3xl p-6 shadow-xl space-y-4">
          <div className="flex items-center gap-3">
            <Activity className="w-5 h-5 text-amber-400 animate-pulse" />
            <span className="text-amber-400 font-bold text-sm uppercase tracking-wider">
              Active Trip Detected
            </span>
            <span className="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-400 text-xs font-mono">
              {activeTrip.status.replace(/_/g, " ")}
            </span>
          </div>
          <p className="text-slate-300 text-sm">
            Your ambulance request is in progress. Track the live ambulance location below.
          </p>
          <Link
            href={`/patient/tracking/${activeTrip.id}`}
            className="inline-flex items-center gap-2 px-6 py-3.5 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-amber-600/30"
          >
            <Navigation className="w-5 h-5" />
            Track Ambulance Live
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      ) : null}

      {/* Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        <div className="bg-gradient-to-br from-red-950/40 via-slate-900 to-slate-950 border border-red-500/30 rounded-3xl p-8 space-y-6 shadow-xl">
          <div className="w-14 h-14 rounded-2xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-500 animate-emergency-pulse">
            <Siren className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-white">Book Emergency Ride</h2>
            <p className="text-slate-300 text-sm leading-relaxed">
              Search any location, click the map, or use your GPS. State severity
              and instantly match with nearby drivers.
            </p>
          </div>
          <Link
            href="/patient/book"
            className="w-full py-3.5 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
          >
            Start Pickup Request
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 space-y-6 shadow-xl">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-500">
            <Clock className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-white">Live Tracking & ETA</h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              View live ambulance GPS on the Leaflet map, dynamic OSRM route,
              driver details, hospital destination, and ML delay risk.
            </p>
          </div>
          {activeTrip ? (
            <Link
              href={`/patient/tracking/${activeTrip.id}`}
              className="w-full py-3.5 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              Track Active Trip
              <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <Link
              href="/patient/book"
              className="w-full py-3.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              Create New Trip
              <ArrowRight className="w-4 h-4" />
            </Link>
          )}
        </div>

      </div>

    </div>
  );
}
