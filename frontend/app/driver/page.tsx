"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Ambulance, Power, Siren, CheckCircle2, XCircle, MapPin, Clock, ArrowRight, Activity } from "lucide-react";
import { api } from "../../lib/api";
import { RealtimeClient } from "../../lib/websocket";
import { getUserDetails } from "../../lib/auth";

export default function DriverDashboard() {
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [isOnDuty, setIsOnDuty] = useState(true);
  const [pendingRequests, setPendingRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  // Load Driver Profile & Pending Requests
  const loadData = async () => {
    try {
      const p = await api.getDriverProfile();
      setProfile(p);
      setIsOnDuty(p.is_on_duty);

      const reqs = await api.getPendingRequests();
      setPendingRequests(reqs);
    } catch (err: any) {
      console.error("Error loading driver data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // WebSocket Connection for Driver Channel
  // IMPORTANT: must use driver profile ID (sa_driver_id), NOT the user ID (sa_user_id).
  // The backend dispatch.py calls manager.notify_driver(selected_driver.id, ...) where
  // selected_driver.id is the Driver table PK — a different value from User.id.
  useEffect(() => {
    const user = getUserDetails();
    // Prefer the driver profile ID stored at login; fall back to profile fetch result
    const channelId = user?.driverId ?? profile?.id ?? null;
    if (!channelId) return;

    const client = new RealtimeClient(
      `/ws/driver/${channelId}`,
      (message) => {
        const { event, data } = message;
        console.log("[Driver WS Event]", event, data);

        if (event === "new_trip_request") {
          loadData();
          // Optional browser notification/sound
        }
      }
    );

    client.connect();
    return () => client.disconnect();
  }, [profile?.id]); // re-run if profile loads after mount

  const toggleDuty = async () => {
    try {
      const updated = await api.updateDutyStatus(!isOnDuty);
      setIsOnDuty(updated.is_on_duty);
    } catch (err: any) {
      alert(`Failed to update duty status: ${err.message}`);
    }
  };

  const handleAccept = async (requestId: number, tripId: number) => {
    try {
      setActionLoading(requestId);
      await api.acceptRequest(requestId);
      router.push(`/driver/trip/${tripId}`);
    } catch (err: any) {
      alert(`Accept failed: ${err.message}`);
      loadData();
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (requestId: number) => {
    try {
      setActionLoading(requestId);
      await api.rejectRequest(requestId);
      loadData();
    } catch (err: any) {
      alert(`Reject failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-slate-400 text-sm">
        Loading Driver Operations Terminal...
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-4xl mx-auto py-4">

      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <Ambulance className="w-8 h-8 text-amber-500" />
            Driver Dispatch Terminal
          </h1>
          <p className="text-slate-400 text-sm mt-1">Receive incoming trip offers in real-time. Explicit acceptance required.</p>
        </div>

        {/* On-Duty Toggle */}
        <button
          onClick={toggleDuty}
          className={`px-5 py-3 rounded-2xl font-bold text-xs flex items-center gap-3 transition-all border shadow-lg ${
            isOnDuty
              ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 shadow-emerald-500/10"
              : "bg-slate-900 border-slate-800 text-slate-500"
          }`}
        >
          <Power className={`w-4 h-4 ${isOnDuty ? "text-emerald-400 animate-pulse" : "text-slate-500"}`} />
          STATUS: {isOnDuty ? "ON DUTY (AVAILABLE)" : "OFF DUTY"}
        </button>
      </div>

      {/* Incoming Requests Panel */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Siren className="w-5 h-5 text-red-500 animate-bounce" />
            Incoming Emergency Offers
            <span className="ml-2 px-2.5 py-0.5 rounded-full bg-red-600/20 text-red-400 text-xs font-mono border border-red-500/30">
              {pendingRequests.length} PENDING
            </span>
          </h2>
          <button onClick={loadData} className="text-xs text-slate-400 hover:text-slate-200 underline">
            Refresh
          </button>
        </div>

        {pendingRequests.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-12 text-center space-y-3">
            <Activity className="w-10 h-10 text-slate-600 mx-auto" />
            <h3 className="text-lg font-bold text-slate-300">No Pending Requests</h3>
            <p className="text-slate-500 text-xs max-w-sm mx-auto">
              You are currently online. When a patient books an ambulance, new requests will appear here in real-time.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6">
            {pendingRequests.map((req) => (
              <div
                key={req.id}
                className="bg-slate-900/90 border-2 border-red-500/60 rounded-3xl p-6 shadow-2xl space-y-6 animate-emergency-pulse"
              >
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-4">
                  <div className="flex items-center gap-3">
                    <span className="px-3 py-1 bg-red-600 text-white font-extrabold text-xs rounded-full uppercase">
                      {req.trip?.severity || "HIGH"} EMERGENCY
                    </span>
                    <span className="text-xs text-slate-400 font-mono">TRIP #{req.trip_id}</span>
                  </div>
                  <div className="text-xs text-amber-400 font-semibold flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    APPROX DISTANCE: {req.distance_km} KM
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-start gap-3">
                    <MapPin className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs text-slate-400 uppercase font-mono">Pickup Location</p>
                      <p className="text-lg font-bold text-white">{req.trip?.pickup_address}</p>
                    </div>
                  </div>
                </div>

                {/* Explicit Accept / Reject Buttons */}
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <button
                    onClick={() => handleReject(req.id)}
                    disabled={actionLoading === req.id}
                    className="py-3.5 bg-slate-950 hover:bg-slate-800 border border-slate-700 text-slate-300 font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                  >
                    <XCircle className="w-4 h-4 text-slate-400" />
                    REJECT OFFER
                  </button>

                  <button
                    onClick={() => handleAccept(req.id, req.trip_id)}
                    disabled={actionLoading === req.id}
                    className="py-3.5 bg-emerald-600 hover:bg-emerald-500 text-white font-extrabold rounded-xl text-sm transition-all shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2"
                  >
                    <CheckCircle2 className="w-5 h-5" />
                    {actionLoading === req.id ? "ACCEPTING..." : "ACCEPT EMERGENCY TRIP"}
                  </button>
                </div>

              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
