"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { Siren, MapPin, AlertTriangle, ArrowRight, Compass, Search, Loader2, LocateFixed } from "lucide-react";
import { api } from "../../../lib/api";

const LeafletMap = dynamic(() => import("../../../components/LeafletMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-80 bg-slate-900 animate-pulse rounded-2xl flex items-center justify-center text-slate-500">
      Loading Map...
    </div>
  ),
});

const NOMINATIM_BASE = process.env.NEXT_PUBLIC_NOMINATIM_URL || "https://nominatim.openstreetmap.org";

async function reverseGeocode(lat: number, lng: number): Promise<string> {
  try {
    const url = `${NOMINATIM_BASE}/reverse?format=json&lat=${lat}&lon=${lng}&zoom=17&addressdetails=1`;
    const res = await fetch(url, { headers: { "Accept-Language": "en" } });
    if (!res.ok) return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    const data = await res.json();
    return data.display_name || `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  } catch {
    return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }
}

async function searchAddress(query: string): Promise<any[]> {
  try {
    const url = `${NOMINATIM_BASE}/search?format=json&q=${encodeURIComponent(query)}&limit=5&addressdetails=1`;
    const res = await fetch(url, { headers: { "Accept-Language": "en" } });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export default function BookAmbulancePage() {
  const router = useRouter();

  // No hardcoded location — start with no selection, neutral map center
  const [pickupAddress, setPickupAddress] = useState("");
  const [pickupLat, setPickupLat] = useState<number | null>(null);
  const [pickupLng, setPickupLng] = useState<number | null>(null);
  const [mapCenter, setMapCenter] = useState<[number, number]>([20, 0]); // world view until chosen
  const [severity, setSeverity] = useState("HIGH");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);

  // Geocoding state
  const [geocoding, setGeocoding] = useState(false);
  const [locating, setLocating] = useState(false);

  const searchDebounceRef = useRef<any>(null);

  const setLocation = useCallback(async (lat: number, lng: number, knownAddress?: string) => {
    setPickupLat(lat);
    setPickupLng(lng);
    setMapCenter([lat, lng]);
    if (knownAddress) {
      setPickupAddress(knownAddress);
    } else {
      setGeocoding(true);
      const addr = await reverseGeocode(lat, lng);
      setPickupAddress(addr);
      setGeocoding(false);
    }
  }, []);

  const handleMapClick = useCallback(async (lat: number, lng: number) => {
    await setLocation(lat, lng);
  }, [setLocation]);

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      setError("Your browser does not support geolocation.");
      return;
    }
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        await setLocation(pos.coords.latitude, pos.coords.longitude);
        setLocating(false);
      },
      (err) => {
        setError(`Location access denied: ${err.message}`);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const handleSearchInput = (value: string) => {
    setSearchQuery(value);
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!value.trim()) { setSearchResults([]); setShowResults(false); return; }
    searchDebounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      const results = await searchAddress(value);
      setSearchResults(results);
      setShowResults(true);
      setSearchLoading(false);
    }, 400);
  };

  const handleSelectResult = async (result: any) => {
    const lat = parseFloat(result.lat);
    const lng = parseFloat(result.lon);
    await setLocation(lat, lng, result.display_name);
    setSearchQuery(result.display_name.substring(0, 60));
    setShowResults(false);
    setSearchResults([]);
  };

  const handleBook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pickupLat === null || pickupLng === null) {
      setError("Please select a pickup location on the map or search for an address.");
      return;
    }
    if (!pickupAddress.trim()) {
      setError("Pickup address is required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api.bookAmbulance({
        pickup_address: pickupAddress,
        pickup_lat: pickupLat,
        pickup_lng: pickupLng,
        severity,
      });
      // Store last trip ID so the patient dashboard can detect active trips
      if (typeof window !== "undefined") {
        sessionStorage.setItem("sa_last_trip_id", String(res.trip_id));
      }
      router.push(`/patient/tracking/${res.trip_id}`);
    } catch (err: any) {
      setError(err.message || "Failed to submit ambulance request");
    } finally {
      setLoading(false);
    }
  };

  const hasLocation = pickupLat !== null && pickupLng !== null;

  return (
    <div className="max-w-4xl mx-auto space-y-8 py-4">

      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
          <Siren className="w-8 h-8 text-red-500 animate-pulse" />
          Request Emergency Ambulance
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Search for a location, click the map, or use your current position.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

        {/* Form */}
        <div className="lg:col-span-5 space-y-6">
          <form onSubmit={handleBook} className="space-y-6 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl">

            {/* Location Search */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <Search className="w-4 h-4 text-blue-400" />
                Search Pickup Address
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => handleSearchInput(e.target.value)}
                  onFocus={() => searchResults.length > 0 && setShowResults(true)}
                  placeholder="Type street, area, or landmark..."
                  className="w-full px-4 py-3 pr-10 bg-slate-950 border border-slate-800 focus:border-blue-500 rounded-xl text-slate-200 text-sm focus:outline-none"
                />
                {searchLoading && (
                  <Loader2 className="absolute right-3 top-3.5 w-4 h-4 text-slate-500 animate-spin" />
                )}
                {showResults && searchResults.length > 0 && (
                  <div className="absolute z-50 top-full mt-1 left-0 right-0 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-h-52 overflow-y-auto">
                    {searchResults.map((r, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => handleSelectResult(r)}
                        className="w-full text-left px-4 py-2.5 text-xs text-slate-200 hover:bg-slate-800 border-b border-slate-800 last:border-0 flex items-start gap-2"
                      >
                        <MapPin className="w-3.5 h-3.5 mt-0.5 text-blue-400 shrink-0" />
                        <span className="line-clamp-2">{r.display_name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Use My Location */}
            <button
              type="button"
              onClick={handleUseMyLocation}
              disabled={locating}
              className="w-full py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold rounded-xl text-xs transition-all flex items-center justify-center gap-2"
            >
              {locating ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Locating...</>
              ) : (
                <><LocateFixed className="w-4 h-4 text-emerald-400" /> Use My Current Location</>
              )}
            </button>

            {/* Selected Address Display */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-red-400" />
                Selected Pickup Location
              </label>
              <div className="px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm min-h-[48px] flex items-center gap-2">
                {geocoding ? (
                  <span className="text-slate-500 flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Getting address...
                  </span>
                ) : hasLocation ? (
                  <span className="text-slate-200">{pickupAddress || "Location selected"}</span>
                ) : (
                  <span className="text-slate-600 italic">
                    Click the map or search above to select a pickup point
                  </span>
                )}
              </div>
              {hasLocation && (
                <p className="text-[11px] text-slate-500 font-mono">
                  {pickupLat!.toFixed(6)}, {pickupLng!.toFixed(6)}
                </p>
              )}
            </div>

            {/* Severity */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Emergency Severity Rating
              </label>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { id: "CRITICAL", label: "CRITICAL", desc: "Life Threatening", color: "border-red-600 bg-red-600/20 text-red-400" },
                  { id: "HIGH",     label: "HIGH",     desc: "Severe Injury",    color: "border-amber-600 bg-amber-600/20 text-amber-400" },
                  { id: "MEDIUM",   label: "MEDIUM",   desc: "Urgent Care",     color: "border-blue-600 bg-blue-600/20 text-blue-400" },
                  { id: "LOW",      label: "LOW",      desc: "Non-Urgent",      color: "border-slate-600 bg-slate-800 text-slate-300" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSeverity(item.id)}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      severity === item.id
                        ? `${item.color} shadow-lg`
                        : "border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <div className="font-bold text-xs">{item.label}</div>
                    <div className="text-[10px] opacity-80">{item.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !hasLocation}
              className="w-full py-4 bg-red-600 hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-red-600/30 flex items-center justify-center gap-2 animate-emergency-pulse"
            >
              {loading ? "Finding Available Ambulance..." : "DISPATCH AMBULANCE NOW"}
              <ArrowRight className="w-5 h-5" />
            </button>

          </form>
        </div>

        {/* Map */}
        <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-3xl p-4 shadow-xl flex flex-col h-[520px]">
          <div className="flex items-center justify-between px-2 pb-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200 flex items-center gap-2">
              <Compass className="w-4 h-4 text-emerald-400" />
              Interactive Location Picker
            </span>
            <span>Click anywhere to place pickup pin</span>
          </div>
          <div className="flex-1 rounded-2xl overflow-hidden">
            <LeafletMap
              center={mapCenter}
              zoom={hasLocation ? 14 : 3}
              pickupPos={hasLocation ? [pickupLat!, pickupLng!] : null}
              onSelectLocation={handleMapClick}
              interactive={true}
            />
          </div>
        </div>

      </div>
    </div>
  );
}
