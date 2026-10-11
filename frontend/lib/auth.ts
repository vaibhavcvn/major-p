export interface UserTokenData {
  token: string;
  role: string;
  userId: number;
  fullName: string;
  driverId?: number | null;    // Driver profile ID — only set for DRIVER role
  hospitalId?: number | null;  // Hospital ID — only set for HOSPITAL role
}

export const setAuthToken = (data: UserTokenData) => {
  if (typeof window !== "undefined") {
    localStorage.setItem("sa_token", data.token);
    localStorage.setItem("sa_role", data.role);
    localStorage.setItem("sa_user_id", data.userId.toString());
    localStorage.setItem("sa_full_name", data.fullName);
    // Store role-specific IDs for WebSocket channel routing
    if (data.driverId != null) {
      localStorage.setItem("sa_driver_id", data.driverId.toString());
    } else {
      localStorage.removeItem("sa_driver_id");
    }
    if (data.hospitalId != null) {
      localStorage.setItem("sa_hospital_id", data.hospitalId.toString());
    } else {
      localStorage.removeItem("sa_hospital_id");
    }
  }
};

export const getAuthToken = (): string | null => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("sa_token");
  }
  return null;
};

export const getUserRole = (): string | null => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("sa_role");
  }
  return null;
};

export const getUserDetails = () => {
  if (typeof window !== "undefined") {
    const rawDriverId = localStorage.getItem("sa_driver_id");
    const rawHospitalId = localStorage.getItem("sa_hospital_id");
    return {
      token: localStorage.getItem("sa_token"),
      role: localStorage.getItem("sa_role"),
      userId: localStorage.getItem("sa_user_id") ? parseInt(localStorage.getItem("sa_user_id")!, 10) : null,
      fullName: localStorage.getItem("sa_full_name") || "User",
      driverId: rawDriverId ? parseInt(rawDriverId, 10) : null,
      hospitalId: rawHospitalId ? parseInt(rawHospitalId, 10) : null,
    };
  }
  return { token: null, role: null, userId: null, fullName: "User", driverId: null, hospitalId: null };
};

export const clearAuth = () => {
  if (typeof window !== "undefined") {
    localStorage.removeItem("sa_token");
    localStorage.removeItem("sa_role");
    localStorage.removeItem("sa_user_id");
    localStorage.removeItem("sa_full_name");
    localStorage.removeItem("sa_driver_id");
    localStorage.removeItem("sa_hospital_id");
  }
};
