"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Shield, Siren, User, Ambulance, Building2, Activity, Clock, AlertTriangle, TrendingUp } from "lucide-react";
import { api } from "../../lib/api";
import { RealtimeClient } from "../../lib/websocket";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from "recharts";
import type { HospitalMarker } from "../../components/LeafletMap";

const LeafletMap = dynamic(() => import("../../components/LeafletMap"), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-slate-900 animate-pulse rounded-2xl flex items-center justify-center text-slate-500">Loading Control Map...</div>
});

export default function AdminDashboard() {
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [hospitals, setHospitals] = useState<HospitalMarker[]>([]);

  const loadData = async () => {
    try {
      const [data, hospData] = await Promise.all([
        api.getAdminOverview(),
        api.getHospitals().catch(() => []),
      ]);
      setOverview(data);
      setHospitals(
        (hospData as any[]).map((h: any) => ({
          id: h.id,
          name: h.name,
          lat: h.latitude,
          lng: h.longitude,
          address: h.address,
          is_ready: h.is_ready,
          available_beds: h.available_beds,
        }))
      );
    } catch (err: any) {
      console.error("Admin overview error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();

    const client = new RealtimeClient(
      "/ws/admin",
      (message) => {
        console.log("[Admin WS Event]", message.event, message.data);
        loadData();
      },
      () => setWsConnected(true),
      () => setWsConnected(false)
    );
    client.connect();
    return () => client.disconnect();
  }, []);

  if (loading || !overview) {
    return (
      <div className="py-16 text-center text-slate-400 text-sm">
        Loading Emergency Command & Control Center...
      </div>
    );
  }

  const { metrics, recent_trips } = overview;

  // Derive ambulance positions from active trips that have a driver location
  const activeAmbulances = recent_trips.filter(
    (t: any) => t.driver_lat && t.driver_lng &&
      !["COMPLETED", "FAILED", "CANCELLED"].includes(t.status)
  );

  // Use the first active ambulance for the map center; fall back to first hospital or world view
  const mapCenter: [number, number] =
    activeAmbulances.length > 0
      ? [activeAmbulances[0].driver_lat, activeAmbulances[0].driver_lng]
      : hospitals.length > 0
      ? [hospitals[0].lat, hospitals[0].lng]
      : [12.9716, 77.5946];

  // Primary ambulance position (latest active trip)
  const primaryAmb: [number, number] | null =
    activeAmbulances.length > 0
      ? [activeAmbulances[0].driver_lat, activeAmbulances[0].driver_lng]
      : null;

  // Primary pickup
  const primaryPickup: [number, number] | null =
    activeAmbulances.length > 0
      ? [activeAmbulances[0].pickup_lat, activeAmbulances[0].pickup_lng]
      : null;

  const riskChartData = [
    { risk: "LOW (<3m)",     count: recent_trips.filter((t: any) => t.delay_risk_level === "LOW").length,      color: "#22c55e" },
    { risk: "MEDIUM (3-7m)", count: recent_trips.filter((t: any) => t.delay_risk_level === "MEDIUM").length,   color: "#f59e0b" },
    { risk: "HIGH (7-12m)",  count: recent_trips.filter((t: any) => t.delay_risk_level === "HIGH").length,     color: "#f97316" },
    { risk: "CRITICAL (>12m)",count: recent_trips.filter((t: any) => t.delay_risk_level === "CRITICAL").length,color: "#ef4444" },
  ];

  return (
    <div className="space-y-8 py-4 max-w-7xl mx-auto">

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <Shield className="w-8 h-8 text-purple-500" />
            Emergency Control Center & Fleet Intelligence
          </h1>
          <p className="text-slate-400 text-sm mt-1">Real-time emergency operations, active dispatch monitoring & ML delay analytics.</p>
        </div>
        <div className="flex items-center gap-2 px-3.5 py-1.5 bg-purple-500/10 border border-purple-500/30 rounded-xl text-purple-400 text-xs font-semibold">
          <Activity className={`w-4 h-4 ${wsConnected ? "animate-pulse" : ""}`} />
          {wsConnected ? "Control Room Live" : "Connecting..."}
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-1">
          <p className="text-xs text-slate-400 uppercase font-mono">Active Trips</p>
          <p className="text-3xl font-extrabold text-red-500">{metrics.active_trips}</p>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-1">
          <p className="text-xs text-slate-400 uppercase font-mono">On-Duty Drivers</p>
          <p className="text-3xl font-extrabold text-amber-400">{metrics.on_duty_drivers}</p>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-1">
          <p className="text-xs text-slate-400 uppercase font-mono">Total Ambulances</p>
          <p className="text-3xl font-extrabold text-blue-400">{metrics.total_ambulances}</p>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-1">
          <p className="text-xs text-slate-400 uppercase font-mono">Hospitals</p>
          <p className="text-3xl font-extrabold text-emerald-400">{metrics.total_hospitals}</p>
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-1 col-span-2 sm:col-span-1">
          <p className="text-xs text-slate-400 uppercase font-mono">Total Users</p>
          <p className="text-3xl font-extrabold text-purple-400">{metrics.total_users}</p>
        </div>
      </div>

      {/* Live Operations Map + ML Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Live Map — shows ambulances + hospitals */}
        <div className="lg:col-span-8 bg-slate-900/80 border border-slate-800 rounded-3xl p-4 shadow-xl flex flex-col h-[480px]">
          <div className="flex items-center justify-between px-2 pb-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-2">
              <Siren className="w-4 h-4 text-purple-400" />
              Live Fleet Operations Map
            </span>
            <span className="font-mono text-purple-400">
              {activeAmbulances.length} ACTIVE · {hospitals.length} HOSPITALS
            </span>
          </div>
          <div className="flex-1 rounded-2xl overflow-hidden">
            <LeafletMap
              center={mapCenter}
              zoom={activeAmbulances.length > 0 ? 13 : 10}
              ambulancePos={primaryAmb}
              pickupPos={primaryPickup}
              hospitals={hospitals}
            />
          </div>
        </div>

        {/* ML Chart */}
        <div className="lg:col-span-4 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4 flex flex-col">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              ML Delay Risk Analytics
            </h2>
            <span className="text-[10px] text-slate-500 font-mono">Scikit-Learn</span>
          </div>
          <div className="flex-1 min-h-[250px] w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskChartData}>
                <XAxis dataKey="risk" stroke="#64748b" fontSize={10} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", borderRadius: "8px" }} itemStyle={{ color: "#f8fafc" }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {riskChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-[11px] text-slate-400 space-y-1">
            <p className="font-semibold text-slate-200">Prediction Factors:</p>
            <p>OSRM duration · time of day · traffic factor · emergency severity</p>
          </div>
        </div>

      </div>

      {/* Active Trips Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-purple-400" />
          Emergency Trips Monitor
        </h2>
        {recent_trips.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs">No trips found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 uppercase font-mono border-b border-slate-800">
                <tr>
                  <th className="p-3">Trip ID</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Severity</th>
                  <th className="p-3">Pickup Address</th>
                  <th className="p-3">Assigned Driver</th>
                  <th className="p-3">Hospital</th>
                  <th className="p-3">Delay Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {recent_trips.map((t: any) => (
                  <tr key={t.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="p-3 font-mono font-bold text-white">#{t.id}</td>
                    <td className="p-3">
                      <span className="px-2.5 py-0.5 bg-red-600/20 text-red-400 border border-red-500/30 rounded-full font-semibold text-[11px]">
                        {t.status}
                      </span>
                    </td>
                    <td className="p-3 font-bold text-amber-400">{t.severity}</td>
                    <td className="p-3 truncate max-w-[150px]">{t.pickup_address}</td>
                    <td className="p-3 font-medium text-slate-200">{t.driver_name || "Unassigned"}</td>
                    <td className="p-3 text-slate-300">{t.hospital_name || "—"}</td>
                    <td className="p-3 font-bold text-emerald-400">{t.delay_risk_level || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
