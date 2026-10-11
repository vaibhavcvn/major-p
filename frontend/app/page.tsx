"use client";

import Link from "next/link";
import { Siren, User, Ambulance, Building2, TrafficCone, Shield, ArrowRight, Activity, Clock, Zap, MapPin } from "lucide-react";
import { setAuthToken } from "../lib/auth";
import { api } from "../lib/api";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  const [loadingRole, setLoadingRole] = useState<string | null>(null);

  const demoLogin = async (email: string, targetPath: string) => {
    try {
      setLoadingRole(email);
      const res = await api.login({ email, password: "password123" });
      setAuthToken({
        token: res.access_token,
        role: res.role,
        userId: res.user_id,
        fullName: res.full_name,
        driverId: res.driver_id ?? null,
        hospitalId: res.hospital_id ?? null,
      });
      router.push(targetPath);
    } catch (err: any) {
      alert(`Demo login failed: ${err.message}`);
    } finally {
      setLoadingRole(null);
    }
  };

  return (
    <div className="space-y-16 py-6">

      {/* Hero Banner */}
      <div className="relative rounded-3xl bg-gradient-to-br from-red-950/40 via-slate-900 to-slate-950 border border-red-500/20 p-8 sm:p-12 overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 -translate-y-12 translate-x-12 w-96 h-96 bg-red-600/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 max-w-3xl space-y-6">

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold uppercase tracking-wider">
            <Siren className="w-4 h-4 animate-bounce" />
            Next-Gen Emergency Dispatch & ML Delay Prediction
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold text-white tracking-tight leading-none">
            Smart Ambulance <br />
            <span className="bg-gradient-to-r from-red-500 via-amber-400 to-red-400 bg-clip-text text-transparent">
              Real-Time Emergency Network
            </span>
          </h1>

          <p className="text-slate-300 text-base sm:text-lg leading-relaxed">
            Instant ambulance dispatch with explicit driver acceptance, real browser geolocation streaming, dynamic OSRM routing, and scikit-learn powered delay prediction for critical medical care.
          </p>

          <div className="flex flex-wrap gap-4 pt-2">
            <button
              onClick={() => demoLogin("patient@smartambulance.com", "/patient/book")}
              className="px-6 py-3.5 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl flex items-center gap-3 transition-all shadow-xl shadow-red-600/30 hover:scale-105"
            >

              <Siren className="w-5 h-5" />
              Request Emergency Ambulance
            </button>
            <Link
              href="/login"
              className="px-6 py-3.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 font-semibold rounded-xl flex items-center gap-2 transition-all"
            >
              Sign In to Dashboard
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

        </div>
      </div>

      {/* Quick Role Access Cards (Demo Mode) */}
      <div className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Zap className="w-6 h-6 text-amber-400" />
              Quick Multi-Role Demo Access
            </h2>
            <p className="text-slate-400 text-sm">One-click launch into seeded demo accounts for immediate testing.</p>
          </div>
          <span className="text-xs bg-slate-800 text-slate-300 px-3 py-1 rounded-full font-mono">
            Default Password: password123
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

          {/* Patient Card */}
          <div className="bg-slate-900/60 border border-slate-800 hover:border-red-500/50 rounded-2xl p-6 space-y-4 transition-all hover:shadow-lg hover:shadow-red-500/10">
            <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-500">
              <User className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">Patient Portal</h3>
              <p className="text-xs text-slate-400 mt-1">Book emergency pickup, severity selection, live map tracking & ETA.</p>
            </div>
            <button
              onClick={() => demoLogin("patient@smartambulance.com", "/patient")}
              disabled={loadingRole === "patient@smartambulance.com"}
              className="w-full py-2.5 bg-red-600/20 hover:bg-red-600 border border-red-500/40 text-red-300 hover:text-white font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              {loadingRole === "patient@smartambulance.com" ? "Logging in..." : "Launch Patient Portal"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Driver Card */}
          <div className="bg-slate-900/60 border border-slate-800 hover:border-amber-500/50 rounded-2xl p-6 space-y-4 transition-all hover:shadow-lg hover:shadow-amber-500/10">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-500">
              <Ambulance className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">Driver Portal</h3>
              <p className="text-xs text-slate-400 mt-1">Duty toggle, atomic request accept/reject, real browser GPS watcher.</p>
            </div>
            <button
              onClick={() => demoLogin("driver@smartambulance.com", "/driver")}
              disabled={loadingRole === "driver@smartambulance.com"}
              className="w-full py-2.5 bg-amber-600/20 hover:bg-amber-600 border border-amber-500/40 text-amber-300 hover:text-white font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              {loadingRole === "driver@smartambulance.com" ? "Logging in..." : "Launch Driver Portal"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Hospital Card */}
          <div className="bg-slate-900/60 border border-slate-800 hover:border-blue-500/50 rounded-2xl p-6 space-y-4 transition-all hover:shadow-lg hover:shadow-blue-500/10">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-500">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">Hospital Emergency Room</h3>
              <p className="text-xs text-slate-400 mt-1">Incoming ambulance telemetry, severity rating, bed readiness status.</p>
            </div>
            <button
              onClick={() => demoLogin("hospital@smartambulance.com", "/hospital")}
              disabled={loadingRole === "hospital@smartambulance.com"}
              className="w-full py-2.5 bg-blue-600/20 hover:bg-blue-600 border border-blue-500/40 text-blue-300 hover:text-white font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              {loadingRole === "hospital@smartambulance.com" ? "Logging in..." : "Launch Hospital ER"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Traffic Card */}
          <div className="bg-slate-900/60 border border-slate-800 hover:border-emerald-500/50 rounded-2xl p-6 space-y-4 transition-all hover:shadow-lg hover:shadow-emerald-500/10">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-500">
              <TrafficCone className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">Traffic Control Center</h3>
              <p className="text-xs text-slate-400 mt-1">Active emergency green corridors. Zero patient data leakage.</p>
            </div>
            <button
              onClick={() => demoLogin("traffic@smartambulance.com", "/traffic")}
              disabled={loadingRole === "traffic@smartambulance.com"}
              className="w-full py-2.5 bg-emerald-600/20 hover:bg-emerald-600 border border-emerald-500/40 text-emerald-300 hover:text-white font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              {loadingRole === "traffic@smartambulance.com" ? "Logging in..." : "Launch Traffic Control"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Admin Card */}
          <div className="bg-slate-900/60 border border-slate-800 hover:border-purple-500/50 rounded-2xl p-6 space-y-4 transition-all hover:shadow-lg hover:shadow-purple-500/10">
            <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-500">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">Admin Command Center</h3>
              <p className="text-xs text-slate-400 mt-1">Fleet management, active trips, ML delay prediction analytics.</p>
            </div>
            <button
              onClick={() => demoLogin("admin@smartambulance.com", "/admin")}
              disabled={loadingRole === "admin@smartambulance.com"}
              className="w-full py-2.5 bg-purple-600/20 hover:bg-purple-600 border border-purple-500/40 text-purple-300 hover:text-white font-semibold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
            >
              {loadingRole === "admin@smartambulance.com" ? "Logging in..." : "Launch Admin Control"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

        </div>
      </div>

    </div>
  );
}
