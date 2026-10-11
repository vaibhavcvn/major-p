"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { TrafficCone, Siren, ShieldCheck, Navigation, Radio, Bell } from "lucide-react";
import { api } from "../../lib/api";
import { RealtimeClient } from "../../lib/websocket";
import type { AmbulanceMarker } from "../../components/LeafletMap";

const LeafletMap = dynamic(() => import("../../components/LeafletMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-slate-900 animate-pulse rounded-2xl flex items-center justify-center text-slate-500">
      Loading Corridor Map...
    </div>
  ),
});

interface ProximityAlert {
  trip_id: number;
  ambulance_identifier: string;
  direction: string;
  approaching: string;
  eta_minutes: number;
  distance_to_destination_km: number;
  severity: string;
  latitude: number;
  longitude: number;
  received_at: string;
}

export default function TrafficDashboard() {
  const [corridors, setCorridors] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<ProximityAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);

  const loadData = async () => {
    try {
      const data = await api.getTrafficCorridors();
      setCorridors(data);
    } catch (err: any) {
      console.error("Traffic corridors error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();

    const client = new RealtimeClient(
      "/ws/traffic",
      (message) => {
        const { event, data } = message;
        console.log("[Traffic WS Event]", event, data);

        if (event === "corridor_update") {
          // Update the corridor list to get refreshed positions for all ambulances
          loadData();
        } else if (event === "ambulance_approaching") {
          // One-time proximity alert — deduplicate by trip_id
          setAlerts((prev) => {
            if (prev.find((a) => a.trip_id === data.trip_id)) return prev;
            return [{ ...data, received_at: new Date().toLocaleTimeString() }, ...prev].slice(0, 10);
          });
          loadData();
        } else if (event === "ambulance_location") {
          // GPS update — update individual corridor position without full reload
          setCorridors((prev) =>
            prev.map((c) =>
              c.trip_id === data.trip_id
                ? { ...c, current_lat: data.latitude, current_lng: data.longitude, eta_minutes: data.eta_minutes }
                : c
            )
          );
        }
      },
      () => setWsConnected(true),
      () => setWsConnected(false)
    );

    client.connect();
    return () => client.disconnect();
  }, []);

  // Issue 2: Build AmbulanceMarker[] from ALL active corridors for the map
  const ambulanceMarkers: AmbulanceMarker[] = corridors
    .filter((c) => c.current_lat != null && c.current_lng != null)
    .map((c) => ({
      id: c.trip_id,
      lat: c.current_lat,
      lng: c.current_lng,
      heading: c.heading ?? 0,
      label: c.ambulance_identifier,
      status: c.status,
      eta_minutes: c.eta_minutes,
    }));

  return (
    <div className="space-y-8 py-4 max-w-6xl mx-auto">

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <TrafficCone className="w-8 h-8 text-emerald-500" />
            Emergency Green Corridor Control
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Traffic junction clearance & signal priority for active ambulances.
          </p>
        </div>
        <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 px-4 py-2 rounded-xl text-emerald-400 text-xs font-semibold">
          <ShieldCheck className="w-4 h-4" />
          <span>Zero Patient Data Mode · {ambulanceMarkers.length} Active</span>
        </div>
      </div>

      {/* Proximity alerts */}
      {alerts.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-bold text-red-400 uppercase flex items-center gap-2">
            <Bell className="w-4 h-4 animate-bounce" />
            PROXIMITY ALERTS ({alerts.length})
          </h2>
          {alerts.map((alert) => (
            <div key={alert.trip_id}
              className="bg-red-950/40 border-2 border-red-500/60 rounded-2xl p-5 shadow-xl space-y-2 animate-pulse"
            >
              <div className="flex justify-between items-center">
                <span className="text-red-400 font-extrabold text-sm">🚨 AMBULANCE APPROACHING — CLEAR ROUTE</span>
                <span className="text-slate-500 text-xs font-mono">{alert.received_at}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-slate-400">Ambulance: <span className="text-white font-bold">{alert.ambulance_identifier}</span></div>
                <div className="text-slate-400">Direction: <span className="text-amber-400 font-bold">{alert.direction}</span></div>
                <div className="text-slate-400">Approaching: <span className="text-white font-bold">{alert.approaching}</span></div>
                <div className="text-slate-400">ETA: <span className="text-amber-400 font-bold">{alert.eta_minutes} MIN</span></div>
                <div className="text-slate-400">Distance: <span className="text-slate-200">{alert.distance_to_destination_km} km to destination</span></div>
                <div className="text-slate-400">Severity: <span className="text-red-400 font-bold">{alert.severity}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Map + Corridor List */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Issue 2: Map shows ALL active ambulances */}
        <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-3xl p-4 shadow-xl flex flex-col h-[500px]">
          <div className="flex items-center justify-between px-2 pb-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-2">
              <Navigation className="w-4 h-4 text-emerald-400" />
              All Active Emergency Vehicle Positions
            </span>
            <span className="font-mono text-emerald-400">
              {ambulanceMarkers.length} AMBULANCE{ambulanceMarkers.length !== 1 ? "S" : ""} ON MAP
            </span>
          </div>
          <div className="flex-1 rounded-2xl overflow-hidden">
            <LeafletMap
              center={ambulanceMarkers.length > 0 ? [ambulanceMarkers[0].lat, ambulanceMarkers[0].lng] : [12.9716, 77.5946]}
              zoom={ambulanceMarkers.length > 0 ? 12 : 10}
              ambulances={ambulanceMarkers}
            />
          </div>
        </div>

        {/* Corridor List — all active */}
        <div className="lg:col-span-5 space-y-4 max-h-[500px] overflow-y-auto pr-1">
          <h2 className="text-lg font-bold text-white flex items-center gap-2 sticky top-0 bg-slate-950 py-2">
            <Siren className="w-5 h-5 text-emerald-400" />
            Active Priority Signals
          </h2>

          {corridors.length === 0 ? (
            <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-8 text-center text-slate-500 text-sm">
              No active emergency ambulances requiring traffic clearance.
            </div>
          ) : (
            corridors.map((c) => (
              <div key={c.trip_id}
                className="bg-slate-900/90 border border-emerald-500/30 rounded-2xl p-5 shadow-xl space-y-3"
              >
                <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                  <span className="font-bold text-white text-base">VEHICLE #{c.ambulance_identifier}</span>
                  <span className="px-2.5 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[11px] font-bold rounded-full">
                    CLEARANCE REQUIRED
                  </span>
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between text-slate-400">
                    <span>Status:</span>
                    <span className="text-slate-200 font-medium">{c.status?.replace(/_/g, " ")}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Severity:</span>
                    <span className={`font-bold ${c.severity === "CRITICAL" || c.severity === "HIGH" ? "text-red-400" : "text-amber-400"}`}>
                      {c.severity}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Heading To:</span>
                    <span className="text-slate-200 font-medium truncate max-w-[180px]">
                      {c.destination_address || "Hospital En-Route"}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Next Junction ETA:</span>
                    <span className="text-amber-400 font-bold">{c.eta_minutes} MINS</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

      </div>

    </div>
  );
}
