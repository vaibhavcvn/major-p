"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Siren, KeyRound, Mail, ArrowRight } from "lucide-react";
import { api } from "../../lib/api";
import { setAuthToken } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.login({ email, password });
      setAuthToken({
        token: res.access_token,
        role: res.role,
        userId: res.user_id,
        fullName: res.full_name,
        driverId: res.driver_id ?? null,
        hospitalId: res.hospital_id ?? null,
      });

      // Redirect based on role
      switch (res.role) {
        case "PATIENT":
          router.push("/patient");
          break;
        case "DRIVER":
          router.push("/driver");
          break;
        case "HOSPITAL":
          router.push("/hospital");
          break;
        case "TRAFFIC":
          router.push("/traffic");
          break;
        case "ADMIN":
          router.push("/admin");
          break;
        default:
          router.push("/");
      }
    } catch (err: any) {
      setError(err.message || "Failed to sign in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12 space-y-8">

      <div className="text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-500 mx-auto animate-emergency-pulse">
          <Siren className="w-7 h-7 animate-pulse" />
        </div>
        <h1 className="text-3xl font-extrabold text-white">Emergency Portal Login</h1>
        <p className="text-slate-400 text-sm">Access your role-based Smart Ambulance dashboard</p>
      </div>

      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-2xl space-y-6">

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
              <Mail className="w-3.5 h-3.5 text-slate-400" />
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@smartambulance.com"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 transition-all"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
              <KeyRound className="w-3.5 h-3.5 text-slate-400" />
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-red-600/20 flex items-center justify-center gap-2"
          >
            {loading ? "Signing In..." : "Sign In to Dashboard"}
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <div className="pt-4 border-t border-slate-800 text-center text-xs text-slate-400">
          Need an account?{" "}
          <Link href="/register" className="text-red-400 hover:underline font-semibold">
            Register Here
          </Link>
        </div>

      </div>

    </div>
  );
}
