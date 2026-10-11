"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Siren, User, Mail, KeyRound, Phone, ShieldCheck, ArrowRight } from "lucide-react";
import { api } from "../../lib/api";
import { setAuthToken } from "../../lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState("PATIENT");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.register({
        email,
        password,
        full_name: fullName,
        phone,
        role,
        license_number: role === "DRIVER" ? licenseNumber : undefined,
      });

      setAuthToken({
        token: res.access_token,
        role: res.role,
        userId: res.user_id,
        fullName: res.full_name,
      });

      switch (res.role) {
        case "PATIENT":
          router.push("/patient");
          break;
        case "DRIVER":
          router.push("/driver");
          break;
        default:
          router.push("/");
      }
    } catch (err: any) {
      setError(err.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12 space-y-8">

      <div className="text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-500 mx-auto">
          <Siren className="w-7 h-7" />
        </div>
        <h1 className="text-3xl font-extrabold text-white">Create Account</h1>
        <p className="text-slate-400 text-sm">Register for Smart Ambulance Services</p>
      </div>

      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 shadow-2xl space-y-6">

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Account Type</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none"
            >
              <option value="PATIENT">Patient / Citizen</option>
              <option value="DRIVER">Ambulance Driver</option>
              <option value="HOSPITAL">Hospital Staff</option>
              <option value="TRAFFIC">Traffic Control Operator</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Full Name</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Email Address</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@example.com"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Phone Number</label>
            <input
              type="text"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1-555-0199"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none"
            />
          </div>

          {role === "DRIVER" && (
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Driver License Number</label>
              <input
                type="text"
                required
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                placeholder="LIC-998877"
                className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-amber-500 rounded-xl text-slate-200 text-sm focus:outline-none"
              />
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-800 focus:border-red-500 rounded-xl text-slate-200 text-sm focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl text-sm transition-all shadow-xl shadow-red-600/20 flex items-center justify-center gap-2 mt-4"
          >
            {loading ? "Registering..." : "Create Account"}
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <div className="pt-4 border-t border-slate-800 text-center text-xs text-slate-400">
          Already have an account?{" "}
          <Link href="/login" className="text-red-400 hover:underline font-semibold">
            Sign In
          </Link>
        </div>

      </div>

    </div>
  );
}
