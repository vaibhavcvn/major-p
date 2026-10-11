"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { Siren, Clock, Ambulance, Phone, Building2, AlertCircle, CheckCircle2, Navigation, Activity } from "lucide-react";
import { api } from "../../../../lib/api";
import { RealtimeClient } from "../../../../lib/websocket";
import type { HospitalMarker } from "../../../../components/LeafletMap";

const LeafletMap = dynamic(() => import("../../../../components/LeafletMap"), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-slate-900 animate-pulse rounded-2xl flex items-center justify-center text-slate-500">Loading Tracking Map...</div>
});

export default function PatientTrackingPage() {
  const params = useParams();
  const tripId = parseInt(params.tripId as string, 10);

  const [trip, setTrip] = useState<any>(null);
  const [ambPos, setAmbPos] = useState<[number, number] | null>(null);
  const [ambHeading, setAmbHeading] = useState(0);
  const [etaMinutes, setEtaMinutes] = useState<number | null>(null);
  const [predictedDelay, setPredictedDelay] = useState<number | null>(null);
  const [delayRisk, setDelayRisk] = useState<string | null>("LOW");
  const [wsConnected, setWsConnected] = useState(false);
  const [error, setError] = useState("");
  const [hospitals, setHospitals] = useState<HospitalMarker[]>([]);

  // Load initial trip state
  useEffect(() => {
    if (!tripId) return;

    api.getPatientTrip(tripId)
      .then((data) => {
        setTrip(data);
        if (data.driver_lat && data.driver_lng) {
          setAmbPos([data.driver_lat, data.driver_lng]);
        }
        setEtaMinutes(data.estimated_pickup_eta || 8);
        setPredictedDelay(data.predicted_delay_minutes || 2.5);
        setDelayRisk(data.delay_risk_level || "LOW");
      })
      .catch((err) => setError(err.message));

    // Load hospitals for map display
    api.getHospitals()
      .then((data: any[]) =>
        setHospitals(data.map((h) => ({
          id: h.id, name: h.name, lat: h.latitude, lng: h.longitude,
          address: h.address, is_ready: h.is_ready, available_beds: h.available_beds,
        })))
      )
      .catch(() => {});
  }, [tripId]);

  // Realtime WebSocket Connection
  useEffect(() => {
    if (!tripId) return;

    const client = new RealtimeClient(
      `/ws/tracking/${tripId}`,
      (message) => {
        const { event, data } = message;
        console.log("[Patient WS Event]", event, data);

        if (event === "trip_status_changed" || event === "trip_assigned") {
          setTrip((prev: any) => ({ ...prev, ...data }));
        } else if (event === "ambulance_location") {
          setAmbPos([data.latitude, data.longitude]);
          if (data.heading) setAmbHeading(data.heading);
          if (data.eta_minutes !== undefined) setEtaMinutes(data.eta_minutes);
          if (data.predicted_delay_minutes !== undefined) setPredictedDelay(data.predicted_delay_minutes);
          if (data.delay_risk_level) setDelayRisk(data.delay_risk_level);
        }
      },
      () => setWsConnected(true),
      () => setWsConnected(false)
    );

    client.connect();
    return () => client.disconnect();
  }, [tripId]);

  if (error) {
    return (
      <div className="p-8 text-center max-w-md mx-auto space-y-4">
        <AlertCircle className="w-12 h-12 text-red-500 mx-auto" />
        <h2 className="text-xl font-bold text-white">Trip Access Error</h2>
        <p className="text-slate-400 text-sm">{error}</p>
      </div>
    );
  }

  if (!trip) {
    return (
      <div className="py-16 text-center space-y-4">
        <Siren className="w-10 h-10 text-red-500 animate-spin mx-auto" />
        <p className="text-slate-400 text-sm">Connecting to Emergency Tracking Gateway...</p>
      </div>
    );
  }

  const pickupPos: [number, number] = [trip.pickup_lat, trip.pickup_lng];
  const hospitalPos: [number, number] | null = trip.destination_lat && trip.destination_lng ? [trip.destination_lat, trip.destination_lng] : null;

  return (
    <div className="space-y-6 py-2">

      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-xl">
        <div>
          <div className="flex items-center gap-3">
            <span className="px-3 py-1 bg-red-500/20 text-red-400 border border-red-500/30 rounded-full font-bold text-xs uppercase tracking-wider animate-pulse">
              {trip.status.replace(/_/g, " ")}
            </span>
            <span className="text-slate-400 text-xs font-mono">TRIP #{trip.id}</span>
          </div>
          <h1 className="text-2xl font-extrabold text-white mt-1">Live Ambulance Dispatch Tracker</h1>
        </div>

        <div className="flex items-center gap-6 bg-slate-950 px-5 py-3 rounded-2xl border border-slate-800">
          <div>
            <p className="text-[10px] text-slate-500 uppercase font-mono">Estimated Arrival</p>
            <p className="text-xl font-extrabold text-amber-400 flex items-center gap-1.5">
              <Clock className="w-5 h-5" />
              {etaMinutes ? `${etaMinutes} MINS` : "COMPUTING..."}
            </p>
          </div>
          {predictedDelay !== null && (
            <div className="border-l border-slate-800 pl-5">
              <p className="text-[10px] text-slate-500 uppercase font-mono">ML Delay Risk</p>
              <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${
                delayRisk === "CRITICAL" ? "bg-red-500/20 text-red-400 border border-red-500/40" :
                delayRisk === "HIGH" ? "bg-orange-500/20 text-orange-400 border border-orange-500/40" :
                delayRisk === "MEDIUM" ? "bg-amber-500/20 text-amber-400 border border-amber-500/40" :
                "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
              }`}>
                {delayRisk} ({predictedDelay}m delay)
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Map View */}
        <div className="lg:col-span-8 bg-slate-900/80 border border-slate-800 rounded-3xl p-4 shadow-xl flex flex-col h-[500px]">
          <div className="flex items-center justify-between px-2 pb-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-2">
              <Navigation className="w-4 h-4 text-red-500" />
              OpenStreetMap + OSRM Live GPS Map
            </span>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${wsConnected ? "bg-emerald-500 animate-ping" : "bg-slate-600"}`} />
              <span>{wsConnected ? "GPS Feed Live" : "Reconnecting..."}</span>
            </div>
          </div>
          <div className="flex-1 rounded-2xl overflow-hidden">
            <LeafletMap
              center={ambPos || pickupPos}
              ambulancePos={ambPos}
              pickupPos={pickupPos}
              hospitalPos={hospitalPos}
              hospitals={hospitals}
              heading={ambHeading}
              zoom={14}
            />
          </div>
        </div>

        {/* Status Details */}
        <div className="lg:col-span-4 space-y-6">

          {/* Driver Info Card */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Ambulance className="w-4 h-4 text-amber-400" />
              Assigned Vehicle & Driver
            </h3>

            {trip.driver_name ? (
              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-bold text-white text-base">{trip.driver_name}</p>
                    <p className="text-xs text-slate-400 font-mono">PLATE: {trip.ambulance_plate || "AMB-101"}</p>
                  </div>
                  {trip.driver_phone && (
                    <a
                      href={`tel:${trip.driver_phone}`}
                      className="p-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500 hover:text-white rounded-xl transition-all"
                    >
                      <Phone className="w-4 h-4" />
                    </a>
                  )}
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs">
                Searching nearby drivers... Offer sent to eligible ambulance operators.
              </div>
            )}
          </div>

          {/* Hospital Card */}
          {trip.hospital_name && (
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-2">
              <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Building2 className="w-4 h-4 text-blue-400" />
                Target Hospital
              </h3>
              <p className="font-bold text-white text-base">{trip.hospital_name}</p>
              <p className="text-xs text-slate-400">{trip.destination_address}</p>
            </div>
          )}

          {/* Emergency Details */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-3 text-xs">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider">Trip Specifications</h3>
            <div className="flex justify-between py-1 border-b border-slate-800 text-slate-400">
              <span>Pickup Location:</span>
              <span className="text-slate-200 font-medium truncate max-w-[180px]">{trip.pickup_address}</span>
            </div>
            <div className="flex justify-between py-1 text-slate-400">
              <span>Emergency Severity:</span>
              <span className="text-red-400 font-bold">{trip.severity}</span>
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
