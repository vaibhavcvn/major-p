"use client";

import { useEffect, useState } from "react";
import { Building2, Clock, Siren, Bed, Activity, CheckCircle, Radio, AlertTriangle } from "lucide-react";
import { api } from "../../lib/api";
import { RealtimeClient } from "../../lib/websocket";
import { getUserDetails } from "../../lib/auth";

export default function HospitalDashboard() {
  const [trips, setTrips] = useState<any[]>([]);
  const [availableBeds, setAvailableBeds] = useState(24);
  const [isReady, setIsReady] = useState(true);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);

  // Resolve hospital identity from authenticated session — never fall back to a hardcoded ID
  const user = getUserDetails();
  const hospitalId = user?.hospitalId ?? null;

  const loadData = async () => {
    try {
      const data = await api.getHospitalTrips();
      setTrips(data);
      // FIX-10: Load actual hospital status (beds/readiness) from server
      const status = await api.getHospitalStatus().catch(() => null);
      if (status) {
        setAvailableBeds(status.available_beds ?? 0);
        setIsReady(status.is_ready ?? true);
      }
    } catch (err: any) {
      console.error("Hospital data error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Guard: if hospitalId is missing this account has no hospital association
    if (hospitalId == null) {
      setLoading(false);
      return;
    }

    loadData();

    // WebSocket Hospital Feed — subscribe to THIS hospital's channel using authenticated ID
    const client = new RealtimeClient(
      `/ws/hospital/${hospitalId}`,
      (message) => {
        const { event, data } = message;
        console.log("[Hospital WS Event]", event, data);
        loadData();
      },
      () => setWsConnected(true),
      () => setWsConnected(false)
    );

    client.connect();
    return () => client.disconnect();
  }, [hospitalId]);

  const updateBeds = async (newVal: number) => {
    try {
      setAvailableBeds(newVal);
      await api.updateHospitalStatus({ available_beds: newVal });
    } catch (err: any) {
      alert(`Status update failed: ${err.message}`);
    }
  };

  const toggleReady = async () => {
    try {
      const nextState = !isReady;
      setIsReady(nextState);
      await api.updateHospitalStatus({ is_ready: nextState });
    } catch (err: any) {
      alert(`Status update failed: ${err.message}`);
    }
  };

  // Guard: no hospital association found for this account
  if (!loading && hospitalId == null) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <AlertTriangle className="w-12 h-12 text-amber-500" />
        <h2 className="text-xl font-bold text-white">No Hospital Association</h2>
        <p className="text-slate-400 text-sm max-w-md text-center">
          This account is not linked to any hospital. Please contact your administrator
          to associate your account with a hospital record.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="py-16 text-center text-slate-400 text-sm">
        Loading Hospital ER Telemetry...
      </div>
    );
  }

  return (
    <div className="space-y-8 py-4 max-w-6xl mx-auto">

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <Building2 className="w-8 h-8 text-blue-500" />
            Hospital Emergency Room Telemetry
          </h1>
          <p className="text-slate-400 text-sm mt-1">Real-time incoming ambulance feed & trauma bay readiness control.</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-xl text-blue-400 text-xs font-semibold">
            <Radio className={`w-3.5 h-3.5 ${wsConnected ? "animate-ping" : ""}`} />
            {wsConnected ? "ER Gateway Connected" : "Connecting..."}
          </div>
        </div>
      </div>

      {/* Hospital Controls Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Readiness Toggle */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase font-mono">Trauma ER Readiness</p>
            <p className={`text-lg font-extrabold ${isReady ? "text-emerald-400" : "text-red-400"}`}>
              {isReady ? "ACCEPTING INCOMING" : "DIVERT / FULL"}
            </p>
          </div>
          <button
            onClick={toggleReady}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all border ${
              isReady ? "bg-emerald-600/20 border-emerald-500/40 text-emerald-300" : "bg-red-600/20 border-red-500/40 text-red-300"
            }`}
          >
            {isReady ? "SET DIVERT" : "SET READY"}
          </button>
        </div>

        {/* Beds Control */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase font-mono">Available Trauma Beds</p>
            <p className="text-2xl font-extrabold text-white">{availableBeds} BEDS</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => updateBeds(Math.max(0, availableBeds - 1))}
              className="w-9 h-9 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold flex items-center justify-center text-lg"
            >
              -
            </button>
            <button
              onClick={() => updateBeds(availableBeds + 1)}
              className="w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold flex items-center justify-center text-lg"
            >
              +
            </button>
          </div>
        </div>

        {/* Incoming Count */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase font-mono">Incoming Ambulances</p>
            <p className="text-2xl font-extrabold text-amber-400">{trips.length} EN-ROUTE</p>
          </div>
          <Siren className="w-8 h-8 text-amber-500 animate-pulse" />
        </div>

      </div>

      {/* Incoming Ambulances List */}
      <div className="space-y-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Active Incoming Ambulances Feed
        </h2>

        {trips.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-12 text-center text-slate-500 text-sm">
            No active emergency ambulances en-route to hospital at this time.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {trips.map((t) => (
              <div key={t.id} className="bg-slate-900/90 border border-blue-500/30 rounded-3xl p-6 shadow-xl space-y-4">

                <div className="flex justify-between items-start border-b border-slate-800 pb-3">
                  <div>
                    <span className="px-3 py-1 bg-red-600/20 text-red-400 border border-red-500/30 text-xs font-bold rounded-full uppercase">
                      {t.severity} SEVERITY
                    </span>
                    <h3 className="font-bold text-white text-lg mt-2">VEHICLE #{t.ambulance_plate || "AMB-101"}</h3>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-400 uppercase font-mono">Hospital ETA</p>
                    <p className="text-xl font-extrabold text-amber-400 flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      {t.estimated_hospital_eta || 6} MINS
                    </p>
                  </div>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between text-slate-400">
                    <span>Current Status:</span>
                    <span className="text-blue-400 font-bold">{t.status.replace(/_/g, " ")}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Driver Name:</span>
                    <span className="text-slate-200">{t.driver_name || "Emergency Driver"}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Pickup Address:</span>
                    <span className="text-slate-200 truncate max-w-[200px]">{t.pickup_address}</span>
                  </div>
                </div>

              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
