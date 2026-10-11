import type { Metadata } from "next";
import "./globals.css";
import Navbar from "../components/Navbar";

export const metadata: Metadata = {
  title: "Smart Ambulance - Intelligent Emergency Response System",
  description: "Real-time dispatch, browser GPS tracking, and ML-powered ambulance delay prediction system.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
        <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
          <p>© 2026 Smart Ambulance Platform. Intelligent Emergency Response & Delay Prediction.</p>
        </footer>
      </body>
    </html>
  );
}
