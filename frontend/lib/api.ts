import { getAuthToken } from "./auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorDetail = "An unexpected error occurred";
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || errorDetail;
    } catch (e) {
      errorDetail = res.statusText;
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (data: any) => fetchAPI("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  register: (data: any) => fetchAPI("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  getMe: () => fetchAPI("/auth/me"),

  // Patient
  bookAmbulance: (data: any) => fetchAPI("/patient/book", { method: "POST", body: JSON.stringify(data) }),
  getPatientTrip: (tripId: number) => fetchAPI(`/patient/trip/${tripId}`),

  // Driver
  getDriverProfile: () => fetchAPI("/driver/profile"),
  updateDutyStatus: (is_on_duty: boolean) => fetchAPI("/driver/status", { method: "POST", body: JSON.stringify({ is_on_duty }) }),
  getPendingRequests: () => fetchAPI("/driver/requests/pending"),
  acceptRequest: (requestId: number) => fetchAPI(`/driver/accept/${requestId}`, { method: "POST" }),
  rejectRequest: (requestId: number) => fetchAPI(`/driver/reject/${requestId}`, { method: "POST" }),
  updateTripStatus: (tripId: number, status: string) => fetchAPI(`/driver/trip/${tripId}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  sendGPSUpdate: (data: any) => fetchAPI("/driver/gps", { method: "POST", body: JSON.stringify(data) }),

  // Hospital
  getHospitalTrips: () => fetchAPI("/hospital/trips"),
  getHospitalStatus: () => fetchAPI("/hospital/status"),
  updateHospitalStatus: (data: any) => fetchAPI("/hospital/status", { method: "POST", body: JSON.stringify(data) }),
  getHospitals: () => fetchAPI("/hospitals"),

  // Traffic
  getTrafficCorridors: () => fetchAPI("/traffic/corridors"),

  // Admin
  getAdminOverview: () => fetchAPI("/admin/overview"),

  // ML Delay Prediction
  predictDelay: (data: any) => fetchAPI("/ml/predict", { method: "POST", body: JSON.stringify(data) }),
};
