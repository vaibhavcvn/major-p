"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { Siren, Shield, User, Ambulance, Building2, TrafficCone, LogOut, Radio } from "lucide-react";
import { getUserDetails, clearAuth } from "../lib/auth";

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    setUser(getUserDetails());
  }, [pathname]);

  const handleLogout = () => {
    clearAuth();
    setUser(null);
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 text-slate-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">

        {/* Brand Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-500 group-hover:scale-105 transition-transform animate-emergency-pulse">
            <Siren className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="font-bold text-lg leading-none tracking-tight flex items-center gap-2">
              <span>SMART AMBULANCE</span>
              <span className="bg-red-500/20 text-red-400 text-xs px-2 py-0.5 rounded-full border border-red-500/30">
                LIVE
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono">Emergency Response Engine</p>
          </div>
        </Link>

        {/* Role Navigation Bar */}
        <nav className="hidden md:flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800/80">
          <Link
            href="/patient"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
              pathname.startsWith("/patient")
                ? "bg-red-600 text-white shadow-lg shadow-red-600/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <User className="w-3.5 h-3.5" />
            Patient
          </Link>

          <Link
            href="/driver"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
              pathname.startsWith("/driver")
                ? "bg-amber-600 text-white shadow-lg shadow-amber-600/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Ambulance className="w-3.5 h-3.5" />
            Driver
          </Link>

          <Link
            href="/hospital"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
              pathname.startsWith("/hospital")
                ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Building2 className="w-3.5 h-3.5" />
            Hospital
          </Link>

          <Link
            href="/traffic"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
              pathname.startsWith("/traffic")
                ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <TrafficCone className="w-3.5 h-3.5" />
            Traffic
          </Link>

          <Link
            href="/admin"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
              pathname.startsWith("/admin")
                ? "bg-purple-600 text-white shadow-lg shadow-purple-600/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            Admin
          </Link>
        </nav>

        {/* User Account / Action */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs">
            <Radio className="w-3 h-3 animate-ping" />
            <span>Server Connected</span>
          </div>

          {user?.token ? (
            <div className="flex items-center gap-3">
              <div className="text-right text-xs hidden sm:block">
                <p className="font-semibold text-slate-200">{user.fullName}</p>
                <p className="text-slate-400 uppercase font-mono text-[10px]">{user.role}</p>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-red-400 hover:border-red-500/40 transition-colors"
                title="Log out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-semibold transition-colors shadow-lg shadow-red-600/20"
            >
              Sign In
            </Link>
          )}
        </div>

      </div>
    </header>
  );
}
