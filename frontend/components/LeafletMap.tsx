"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";

export interface HospitalMarker {
  id: number;
  name: string;
  lat: number;
  lng: number;
  address?: string;
  is_ready?: boolean;
  available_beds?: number;
}

/** Used by the traffic page to show multiple active ambulances simultaneously */
export interface AmbulanceMarker {
  /** Unique key — use trip_id for traffic, driver_id for other contexts */
  id: number;
  lat: number;
  lng: number;
  heading?: number;
  label?: string;   // e.g. vehicle number
  status?: string;
  eta_minutes?: number;
}

interface LeafletMapProps {
  center?: [number, number];
  zoom?: number;
  /** Single ambulance (legacy — still supported, used by tracking/driver pages) */
  ambulancePos?: [number, number] | null;
  heading?: number;
  pickupPos?: [number, number] | null;
  /** Single hospital (legacy — still supported) */
  hospitalPos?: [number, number] | null;
  /** Multiple hospitals for map display */
  hospitals?: HospitalMarker[];
  /** Multiple ambulances — when provided, replaces ambulancePos management */
  ambulances?: AmbulanceMarker[];
  onSelectLocation?: (lat: number, lng: number) => void;
  interactive?: boolean;
}

export default function LeafletMap({
  center = [20, 0],
  zoom = 3,
  ambulancePos,
  heading = 0,
  pickupPos,
  hospitalPos,
  hospitals,
  ambulances,
  onSelectLocation,
  interactive = true,
}: LeafletMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const singleAmbMarkerRef = useRef<any>(null);
  const multiAmbMarkersRef = useRef<Map<number, any>>(new Map());
  const pickupMarkerRef = useRef<any>(null);
  const legacyHospitalMarkerRef = useRef<any>(null);
  const hospitalMarkersRef = useRef<Map<number, any>>(new Map());
  const routePolylineRef = useRef<any>(null);
  const LRef = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false);
  // Track whether we've done the initial fit — only auto-fit once
  const initialFitDoneRef = useRef(false);

  // ── Init map once ─────────────────────────────────────────────────────────
  useEffect(() => {
    let isMounted = true;
    import("leaflet").then((L) => {
      if (!isMounted || !mapContainerRef.current) return;
      LRef.current = L;
      if (!mapInstanceRef.current) {
        const map = L.map(mapContainerRef.current, {
          zoomControl: true,
          attributionControl: false,
        }).setView(center, zoom);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
        }).addTo(map);
        if (interactive && onSelectLocation) {
          map.on("click", (e: any) => onSelectLocation(e.latlng.lat, e.latlng.lng));
        }
        mapInstanceRef.current = map;
        setMapReady(true);
      }
    });
    return () => {
      isMounted = false;
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Re-center when center prop changes ────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapInstanceRef.current) return;
    mapInstanceRef.current.setView(center, zoom, { animate: true });
  }, [center, zoom, mapReady]);

  // ── Pickup Marker ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    const L = LRef.current;
    const map = mapInstanceRef.current;
    if (pickupPos) {
      const icon = L.divIcon({
        className: "custom-pickup-icon",
        html: `<div style="width:32px;height:32px;background:rgba(34,197,94,.2);border:2px solid #22c55e;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 0 15px #22c55e;"><div style="width:12px;height:12px;background:#22c55e;border-radius:50%;"></div></div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });
      if (pickupMarkerRef.current) {
        pickupMarkerRef.current.setLatLng(pickupPos);
      } else {
        pickupMarkerRef.current = L.marker(pickupPos, { icon }).addTo(map);
        pickupMarkerRef.current.bindPopup("<b>📍 Pickup Location</b>");
      }
    } else if (pickupMarkerRef.current) {
      map.removeLayer(pickupMarkerRef.current);
      pickupMarkerRef.current = null;
    }
  }, [pickupPos, mapReady]);

  // ── Legacy single hospital ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    const L = LRef.current;
    const map = mapInstanceRef.current;
    if (hospitalPos) {
      const icon = L.divIcon({
        className: "custom-hospital-icon",
        html: `<div style="width:36px;height:36px;background:rgba(59,130,246,.3);border:2px solid #3b82f6;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 0 15px #3b82f6;">🏥</div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      });
      if (legacyHospitalMarkerRef.current) {
        legacyHospitalMarkerRef.current.setLatLng(hospitalPos);
      } else {
        legacyHospitalMarkerRef.current = L.marker(hospitalPos, { icon }).addTo(map);
        legacyHospitalMarkerRef.current.bindPopup("<b>🏥 Emergency Hospital</b>");
      }
    } else if (legacyHospitalMarkerRef.current) {
      map.removeLayer(legacyHospitalMarkerRef.current);
      legacyHospitalMarkerRef.current = null;
    }
  }, [hospitalPos, mapReady]);

  // ── Multiple hospital markers ─────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    const L = LRef.current;
    const map = mapInstanceRef.current;
    const existing = hospitalMarkersRef.current;
    if (!hospitals || hospitals.length === 0) {
      existing.forEach((m) => map.removeLayer(m));
      existing.clear();
      return;
    }
    const incomingIds = new Set(hospitals.map((h) => h.id));
    existing.forEach((m, id) => {
      if (!incomingIds.has(id)) { map.removeLayer(m); existing.delete(id); }
    });
    hospitals.forEach((h) => {
      const pos: [number, number] = [h.lat, h.lng];
      const statusColor = h.is_ready === false ? "#ef4444" : "#3b82f6";
      const bedsText = h.available_beds !== undefined
        ? `<br/><span style="color:#94a3b8;font-size:11px">Beds: ${h.available_beds}</span>` : "";
      const icon = L.divIcon({
        className: "",
        html: `<div style="width:34px;height:34px;background:rgba(59,130,246,.25);border:2px solid ${statusColor};border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 0 12px ${statusColor};">🏥</div>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      });
      if (existing.has(h.id)) {
        existing.get(h.id)!.setLatLng(pos).setIcon(icon);
      } else {
        const m = L.marker(pos, { icon }).addTo(map);
        m.bindPopup(`<b style="color:#fff">🏥 ${h.name}</b>${bedsText}<br/><span style="color:#94a3b8;font-size:10px">${h.address || ""}</span>`);
        existing.set(h.id, m);
      }
    });
  }, [hospitals, mapReady]);

  // ── Legacy single ambulance marker ────────────────────────────────────────
  // Only active when `ambulances` array prop is NOT provided.
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    // Skip if multi-ambulance mode is active
    if (ambulances && ambulances.length > 0) return;

    const L = LRef.current;
    const map = mapInstanceRef.current;
    if (ambulancePos) {
      const icon = L.divIcon({
        className: "custom-ambulance-icon",
        html: `<div style="transform:rotate(${heading}deg);transition:transform 0.3s ease;width:42px;height:42px;background:#ef4444;border:3px solid #fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 0 20px #ef4444;">🚑</div>`,
        iconSize: [42, 42],
        iconAnchor: [21, 21],
      });
      if (singleAmbMarkerRef.current) {
        singleAmbMarkerRef.current.setLatLng(ambulancePos);
        singleAmbMarkerRef.current.setIcon(icon);
      } else {
        singleAmbMarkerRef.current = L.marker(ambulancePos, { icon }).addTo(map);
        singleAmbMarkerRef.current.bindPopup("<b>🚑 Emergency Ambulance (Live GPS)</b>");
      }
      map.panTo(ambulancePos, { animate: true });
    } else if (singleAmbMarkerRef.current) {
      map.removeLayer(singleAmbMarkerRef.current);
      singleAmbMarkerRef.current = null;
    }
  }, [ambulancePos, heading, ambulances, mapReady]);

  // ── Multi-ambulance markers (Issue 2) ─────────────────────────────────────
  // Manages one marker per ambulance.id; add/update/remove as data changes.
  // Does NOT auto-pan — avoids viewport jumping with multiple active vehicles.
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    if (!ambulances) return;

    const L = LRef.current;
    const map = mapInstanceRef.current;
    const existing = multiAmbMarkersRef.current;

    if (ambulances.length === 0) {
      existing.forEach((m) => map.removeLayer(m));
      existing.clear();
      return;
    }

    const incomingIds = new Set(ambulances.map((a) => a.id));

    // Remove markers for ambulances no longer in the list (completed / off map)
    existing.forEach((m, id) => {
      if (!incomingIds.has(id)) { map.removeLayer(m); existing.delete(id); }
    });

    ambulances.forEach((amb) => {
      const pos: [number, number] = [amb.lat, amb.lng];
      const hdg = amb.heading ?? 0;
      const label = amb.label ?? `AMB-${amb.id}`;
      const statusText = amb.status ? amb.status.replace(/_/g, " ") : "ACTIVE";
      const etaText = amb.eta_minutes !== undefined ? `ETA: ${amb.eta_minutes} min` : "";

      const icon = L.divIcon({
        className: "",
        html: `<div style="transform:rotate(${hdg}deg);transition:transform 0.3s ease;width:40px;height:40px;background:#ef4444;border:3px solid #fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:19px;box-shadow:0 0 18px #ef4444;">🚑</div>`,
        iconSize: [40, 40],
        iconAnchor: [20, 20],
      });

      const popup = `<b style="color:#fff">🚑 ${label}</b><br/><span style="color:#94a3b8;font-size:11px">${statusText}</span>${etaText ? `<br/><span style="color:#f59e0b;font-size:11px">${etaText}</span>` : ""}`;

      if (existing.has(amb.id)) {
        const m = existing.get(amb.id)!;
        m.setLatLng(pos);
        m.setIcon(icon);
        if (m.isPopupOpen()) m.setPopupContent(popup);
      } else {
        const m = L.marker(pos, { icon }).addTo(map);
        m.bindPopup(popup);
        existing.set(amb.id, m);
      }
    });

    // On the very first render with real markers, fit bounds to show all of them.
    // After that, don't re-fit (would constantly zoom as ambulances move).
    if (!initialFitDoneRef.current && ambulances.length > 0) {
      try {
        const allPositions = ambulances.map((a) => [a.lat, a.lng]);
        const bounds = L.latLngBounds(allPositions as any);
        map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
        initialFitDoneRef.current = true;
      } catch {
        // Ignore if bounds are malformed
      }
    }
  }, [ambulances, mapReady]);

  // ── OSRM Route ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !LRef.current || !mapInstanceRef.current) return;
    // Skip route drawing in multi-ambulance mode (no single clear route)
    if (ambulances && ambulances.length > 0) return;

    const start = ambulancePos || pickupPos;
    const end = hospitalPos || (ambulancePos ? pickupPos : null);
    if (!start || !end) {
      if (routePolylineRef.current) {
        mapInstanceRef.current.removeLayer(routePolylineRef.current);
        routePolylineRef.current = null;
      }
      return;
    }
    const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${start[1]},${start[0]};${end[1]},${end[0]}?overview=full&geometries=geojson`;
    fetch(osrmUrl)
      .then((r) => r.json())
      .then((data) => {
        if (data.routes?.[0]) {
          const coords = data.routes[0].geometry.coordinates.map((c: [number, number]) => [c[1], c[0]]);
          const L = LRef.current;
          const map = mapInstanceRef.current;
          if (routePolylineRef.current) map.removeLayer(routePolylineRef.current);
          routePolylineRef.current = L.polyline(coords, {
            color: "#ef4444",
            weight: 5,
            opacity: 0.8,
            dashArray: "10, 10",
          }).addTo(map);
          map.fitBounds(routePolylineRef.current.getBounds(), { padding: [50, 50] });
        }
      })
      .catch(() => {});
  }, [ambulancePos, pickupPos, hospitalPos, ambulances, mapReady]);

  return <div ref={mapContainerRef} className="w-full h-full min-h-[350px] relative" />;
}
