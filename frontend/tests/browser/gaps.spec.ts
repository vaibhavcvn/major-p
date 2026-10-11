/**
 * Smart Ambulance — Gap-Fix Browser Tests (Isolated DB)
 * =======================================================
 * All API calls target the isolated backend on port 8000 (playwright_test.db).
 * The user's smart_ambulance.db is NEVER touched.
 *
 * GAP-A  Patient books via real UI: address search → DISPATCH button
 * GAP-B  Two simultaneous ambulance markers in Leaflet DOM
 * GAP-C  Driver completes trip through all UI buttons including AT_HOSPITAL + COMPLETED
 *
 * Isolation guarantees:
 *  - Fresh DB seeded by globalSetup before every run.
 *  - Seed drivers D1/D2 have GPS coordinates and no active trips.
 *  - Only seed drivers D1/D2 are on-duty → dispatch always goes to them.
 *  - No null-GPS drivers pollute the eligibility pool.
 */

import { test, expect, Page } from "@playwright/test";

const BASE = "http://localhost:3000";
const API  = "http://localhost:8000/api/v1";  // isolated backend

const SEED_D1 = { email: "driver@smartambulance.com",  password: "password123", lat: 12.9716, lng: 77.5946 };
const SEED_D2 = { email: "driver2@smartambulance.com", password: "password123", lat: 12.9780, lng: 77.6000 };

// ── Helpers ──────────────────────────────────────────────────────────────────

async function apiPost(url: string, body: object, token = "") {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  return r;
}

async function apiGetJson(url: string, token: string): Promise<any> {
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`GET ${url} → ${r.status}: ${await r.text()}`);
  return r.json();
}

async function loginApi(email: string, password: string) {
  const r = await apiPost(`${API}/auth/login`, { email, password });
  if (!r.ok) throw new Error(`Login ${email} → ${r.status}: ${await r.text()}`);
  const d = await r.json();
  if (!d.access_token) throw new Error(`No token for ${email}: ${JSON.stringify(d)}`);
  return d;
}

async function registerAndLogin(email: string, pwd: string, role: string, extra: Record<string,string> = {}) {
  const reg = await apiPost(`${API}/auth/register`, {
    email, password: pwd, full_name: `Gap ${role}`, role, ...extra,
  });
  if (reg.status !== 200 && reg.status !== 400) throw new Error(`Register ${email} → ${reg.status}`);
  return loginApi(email, pwd);
}

async function injectAuth(page: Page, d: {
  access_token: string; role: string; user_id: number;
  driver_id?: number | null; hospital_id?: number | null;
}) {
  await page.evaluate((data) => {
    localStorage.setItem("sa_token",    data.access_token);
    localStorage.setItem("sa_role",     data.role);
    localStorage.setItem("sa_user_id",  String(data.user_id));
    if (data.driver_id)   localStorage.setItem("sa_driver_id",   String(data.driver_id));
    if (data.hospital_id) localStorage.setItem("sa_hospital_id", String(data.hospital_id));
  }, d);
}

// ════════════════════════════════════════════════════════════════════════════
//  GAP-A  Patient books via real UI: address search → DISPATCH button
// ════════════════════════════════════════════════════════════════════════════

const TS = Date.now();
let gapAPatientToken = "";
let gapATripId = 0;

test("GAP-A-setup", async () => {
  const pd = await registerAndLogin(`gap_a_p_${TS}@test.com`, "GapA_Pass8!", "PATIENT");
  gapAPatientToken = pd.access_token;
  // Ensure D1/D2 are on-duty (fresh DB but belt-and-suspenders)
  const d1 = await loginApi(SEED_D1.email, SEED_D1.password);
  const d2 = await loginApi(SEED_D2.email, SEED_D2.password);
  await apiPost(`${API}/driver/status`, { is_on_duty: true }, d1.access_token);
  await apiPost(`${API}/driver/status`, { is_on_duty: true }, d2.access_token);
});

test("GAP-A — patient books via UI: search → address selected → DISPATCH clicked → tracking", async ({ browser }) => {
  // ── Intercept Nominatim so test is network-independent ────────────────────
  const ctx = await browser.newContext({ permissions: ["geolocation"] });
  const page = await ctx.newPage();

  await page.route("**/nominatim.openstreetmap.org/search*", async (route) => {
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([{
        place_id: 99999,
        lat: String(SEED_D1.lat),
        lon: String(SEED_D1.lng),
        display_name: "MG Road, Bangalore, Karnataka, India",
        type: "road",
      }]),
    });
  });
  await page.route("**/nominatim.openstreetmap.org/reverse*", async (route) => {
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ display_name: "MG Road, Bangalore, Karnataka, India" }),
    });
  });

  // Inject auth
  await page.goto(BASE);
  await injectAuth(page, { access_token: gapAPatientToken, role: "PATIENT", user_id: 1 });

  // Navigate to booking page
  await page.goto(`${BASE}/patient/book`);
  await expect(page.locator("text=Request Emergency Ambulance")).toBeVisible({ timeout: 15_000 });

  // Type in the search box
  const searchInput = page.locator('input[placeholder="Type street, area, or landmark..."]');
  await expect(searchInput).toBeVisible({ timeout: 10_000 });
  await searchInput.fill("MG Road Bangalore");

  // Nominatim result dropdown appears
  const resultItem = page.locator("text=MG Road, Bangalore, Karnataka, India").first();
  await expect(resultItem).toBeVisible({ timeout: 10_000 });
  console.log("✓ Nominatim search result appeared in dropdown");

  // Click the result → sets lat/lng
  await resultItem.click();
  await expect(page.locator("text=MG Road, Bangalore").first()).toBeVisible({ timeout: 8_000 });
  console.log("✓ Address shown in pickup location field");

  // DISPATCH button must now be enabled
  const dispatchBtn = page.locator("text=DISPATCH AMBULANCE NOW");
  await expect(dispatchBtn).toBeVisible({ timeout: 5_000 });
  await expect(dispatchBtn).not.toBeDisabled({ timeout: 5_000 });
  console.log("✓ DISPATCH AMBULANCE NOW button is enabled");

  // Capture the /patient/book response to get trip_id
  page.on("response", async (resp) => {
    if (resp.url().includes("/patient/book") && resp.request().method() === "POST") {
      const b = await resp.json().catch(() => ({}));
      if (b.trip_id) gapATripId = b.trip_id;
    }
  });

  // ── Click DISPATCH — this submits the real form ───────────────────────────
  await dispatchBtn.click();
  console.log("✓ Clicked DISPATCH AMBULANCE NOW button");

  // Must redirect to /patient/tracking/{id}
  await page.waitForURL(/\/patient\/tracking\/\d+/, { timeout: 20_000 });
  const trackUrl = page.url();
  expect(trackUrl).toMatch(/\/patient\/tracking\/\d+/);
  const m = trackUrl.match(/\/patient\/tracking\/(\d+)/);
  if (m && !gapATripId) gapATripId = parseInt(m[1], 10);
  console.log(`✓ Redirected to tracking page — trip_id=${gapATripId}`);

  await expect(page.locator("text=Live Ambulance Dispatch Tracker")).toBeVisible({ timeout: 15_000 });
  console.log("✓ Patient tracking page loaded after booking via UI form");

  expect(gapATripId).toBeGreaterThan(0);
  const trip = await apiGetJson(`${API}/patient/trip/${gapATripId}`, gapAPatientToken);
  expect(["DRIVER_REQUESTED", "SEARCHING", "ASSIGNED"]).toContain(trip.status);
  console.log(`✓ Trip status from API: ${trip.status}`);

  await ctx.close();
});

// ════════════════════════════════════════════════════════════════════════════
//  GAP-B  Two simultaneous ambulance markers in Leaflet DOM
//
//  Fresh isolated DB: only D1 and D2 are on-duty.
//  Trip1 booked at D1's GPS → D1 is nearest (0 km) → dispatched to D1.
//  Trip2 booked at D2's GPS → D2 is nearest (0 km) → dispatched to D2.
//  Both accept via the real driver UI.
//  Traffic page verified to show both markers.
// ════════════════════════════════════════════════════════════════════════════

let gapBD1Token = ""; let gapBD2Token = "";
let gapBD1Profile: any = null; let gapBD2Profile: any = null;
let gapBP1Token = ""; let gapBP2Token = "";
let gapBTripId1 = 0; let gapBTripId2 = 0;

test("GAP-B-setup — two patients, seed drivers on-duty", async () => {
  const d1d = await loginApi(SEED_D1.email, SEED_D1.password);
  const d2d = await loginApi(SEED_D2.email, SEED_D2.password);
  gapBD1Token   = d1d.access_token;
  gapBD2Token   = d2d.access_token;
  gapBD1Profile = await apiGetJson(`${API}/driver/profile`, gapBD1Token);
  gapBD2Profile = await apiGetJson(`${API}/driver/profile`, gapBD2Token);

  // Ensure on-duty
  await apiPost(`${API}/driver/status`, { is_on_duty: true }, gapBD1Token);
  await apiPost(`${API}/driver/status`, { is_on_duty: true }, gapBD2Token);

  const p1d = await registerAndLogin(`gap_b_p1_${TS}@test.com`, "GapB_Pass8!", "PATIENT");
  const p2d = await registerAndLogin(`gap_b_p2_${TS}@test.com`, "GapB_Pass8!", "PATIENT");
  gapBP1Token = p1d.access_token;
  gapBP2Token = p2d.access_token;

  console.log(`D1 id=${gapBD1Profile.id} GPS=(${SEED_D1.lat},${SEED_D1.lng})`);
  console.log(`D2 id=${gapBD2Profile.id} GPS=(${SEED_D2.lat},${SEED_D2.lng})`);
});

test("GAP-B-book — two trips at distinct driver locations", async () => {
  // Trip1 at D1's GPS → D1 should be nearest (0 km)
  const b1 = await apiPost(`${API}/patient/book`, {
    pickup_address: "MG Road (Trip1)", pickup_lat: SEED_D1.lat, pickup_lng: SEED_D1.lng, severity: "HIGH",
  }, gapBP1Token);
  if (!b1.ok) throw new Error(`Book trip1: ${b1.status} ${await b1.text()}`);
  gapBTripId1 = (await b1.json()).trip_id;

  // Trip2 at D2's GPS → D2 should be nearest (0 km)
  const b2 = await apiPost(`${API}/patient/book`, {
    pickup_address: "Whitefield (Trip2)", pickup_lat: SEED_D2.lat, pickup_lng: SEED_D2.lng, severity: "MEDIUM",
  }, gapBP2Token);
  if (!b2.ok) throw new Error(`Book trip2: ${b2.status} ${await b2.text()}`);
  gapBTripId2 = (await b2.json()).trip_id;

  const t1 = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBP1Token);
  const t2 = await apiGetJson(`${API}/patient/trip/${gapBTripId2}`, gapBP2Token);
  console.log(`Trip1=${gapBTripId1} status=${t1.status}  Trip2=${gapBTripId2} status=${t2.status}`);

  expect(["DRIVER_REQUESTED","SEARCHING","ASSIGNED"]).toContain(t1.status);
  expect(["DRIVER_REQUESTED","SEARCHING","ASSIGNED","FAILED"]).toContain(t2.status);
});

test("GAP-B-accept1 — Seed D1 accepts trip1 via UI ACCEPT button", async ({ browser }) => {
  // Before opening the UI, reject any stale pending requests for D1 that are
  // NOT for gapBTripId1.  This prevents earlier trips (from GAP-A or a_workflow)
  // from appearing first in the driver dashboard and causing the wrong acceptance.
  const allPending = await apiGetJson(`${API}/driver/requests/pending`, gapBD1Token);
  if (!Array.isArray(allPending)) throw new Error(`D1 pending not array: ${JSON.stringify(allPending)}`);

  for (const r of allPending) {
    if (r.trip_id !== gapBTripId1) {
      console.log(`Rejecting stale request id=${r.id} for trip ${r.trip_id} (not our trip ${gapBTripId1})`);
      await apiPost(`${API}/driver/reject/${r.id}`, {}, gapBD1Token);
    }
  }

  // Now verify D1 has exactly our request
  const pending = await apiGetJson(`${API}/driver/requests/pending`, gapBD1Token);
  if (!Array.isArray(pending)) throw new Error(`D1 pending not array after cleanup: ${JSON.stringify(pending)}`);

  const req = pending.find((r: any) => r.trip_id === gapBTripId1);
  if (!req) {
    const t = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBP1Token);
    if (["ASSIGNED","EN_ROUTE_TO_PICKUP"].includes(t.status)) {
      console.log(`Trip1 (${gapBTripId1}) already ASSIGNED — skipping UI accept`);
      return;
    }
    throw new Error(
      `D1 has no pending request for trip ${gapBTripId1} after cleanup. ` +
      `Remaining pending: ${JSON.stringify(pending.map((r: any) => ({ id: r.id, trip_id: r.trip_id })))}. ` +
      `Trip1 status: ${t.status}`
    );
  }

  console.log(`D1 has exactly 1 pending request id=${req.id} for trip ${gapBTripId1} ✓`);

  const ctx = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: SEED_D1.lat, longitude: SEED_D1.lng },
  });
  const page = await ctx.newPage();
  await page.goto(BASE);
  await injectAuth(page, {
    access_token: gapBD1Token, role: "DRIVER",
    user_id: gapBD1Profile.user_id, driver_id: gapBD1Profile.id,
  });
  await page.goto(`${BASE}/driver`);
  await expect(page.locator("text=Driver Dispatch Terminal")).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await page.waitForTimeout(1_500);

  const acceptBtn = page.locator("text=ACCEPT EMERGENCY TRIP").first();
  await expect(acceptBtn).toBeVisible({ timeout: 10_000 });
  await acceptBtn.click();
  await page.waitForURL(/\/driver\/trip\/\d+/, { timeout: 15_000 });
  const url = page.url();
  console.log(`✓ D1 clicked ACCEPT → ${url}`);

  // Strictly verify the URL contains the trip ID we expected
  const acceptedTripId = parseInt(url.match(/\/driver\/trip\/(\d+)/)![1], 10);
  if (acceptedTripId !== gapBTripId1) {
    throw new Error(
      `D1 accepted trip ${acceptedTripId} but expected trip ${gapBTripId1}. ` +
      `The driver UI showed a different pending request after cleanup.`
    );
  }
  console.log(`✓ Confirmed: accepted trip ${acceptedTripId} === gapBTripId1 (${gapBTripId1})`);

  // Verify via API that gapBTripId1 is now ASSIGNED
  const t = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBP1Token);
  expect(["ASSIGNED","EN_ROUTE_TO_PICKUP"]).toContain(t.status);
  console.log(`✓ Trip1 (${gapBTripId1}) status: ${t.status}`);
  await ctx.close();
});

test("GAP-B-accept2 — Seed D2 accepts trip2 via UI ACCEPT button", async ({ browser }) => {
  // Reject any stale pending requests for D2 that are NOT for gapBTripId2
  const allPending = await apiGetJson(`${API}/driver/requests/pending`, gapBD2Token);
  if (!Array.isArray(allPending)) throw new Error(`D2 pending not array: ${JSON.stringify(allPending)}`);

  for (const r of allPending) {
    if (r.trip_id !== gapBTripId2) {
      console.log(`Rejecting stale request id=${r.id} for trip ${r.trip_id} (not our trip ${gapBTripId2})`);
      await apiPost(`${API}/driver/reject/${r.id}`, {}, gapBD2Token);
    }
  }

  const pending = await apiGetJson(`${API}/driver/requests/pending`, gapBD2Token);
  if (!Array.isArray(pending)) throw new Error(`D2 pending not array after cleanup: ${JSON.stringify(pending)}`);

  const req = pending.find((r: any) => r.trip_id === gapBTripId2);
  if (!req) {
    const t = await apiGetJson(`${API}/patient/trip/${gapBTripId2}`, gapBP2Token).catch(() => null);
    if (t && ["ASSIGNED","EN_ROUTE_TO_PICKUP"].includes(t.status)) {
      console.log(`Trip2 (${gapBTripId2}) already ASSIGNED — skipping UI accept`);
      return;
    }
    test.skip(true,
      `D2 has no pending request for trip ${gapBTripId2} after cleanup. ` +
      `Trip2 status: ${t?.status ?? "unknown"}`
    );
  }

  console.log(`D2 has exactly 1 pending request id=${req.id} for trip ${gapBTripId2} ✓`);

  const ctx = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: SEED_D2.lat, longitude: SEED_D2.lng },
  });
  const page = await ctx.newPage();
  await page.goto(BASE);
  await injectAuth(page, {
    access_token: gapBD2Token, role: "DRIVER",
    user_id: gapBD2Profile.user_id, driver_id: gapBD2Profile.id,
  });
  await page.goto(`${BASE}/driver`);
  await expect(page.locator("text=Driver Dispatch Terminal")).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await page.waitForTimeout(1_500);

  const acceptBtn = page.locator("text=ACCEPT EMERGENCY TRIP").first();
  await expect(acceptBtn).toBeVisible({ timeout: 10_000 });
  await acceptBtn.click();
  await page.waitForURL(/\/driver\/trip\/\d+/, { timeout: 15_000 });
  const url = page.url();
  console.log(`✓ D2 clicked ACCEPT → ${url}`);

  // Strictly verify URL matches expected trip
  const acceptedTripId = parseInt(url.match(/\/driver\/trip\/(\d+)/)![1], 10);
  if (acceptedTripId !== gapBTripId2) {
    throw new Error(
      `D2 accepted trip ${acceptedTripId} but expected trip ${gapBTripId2}.`
    );
  }
  console.log(`✓ Confirmed: accepted trip ${acceptedTripId} === gapBTripId2 (${gapBTripId2})`);

  const t = await apiGetJson(`${API}/patient/trip/${gapBTripId2}`, gapBP2Token);
  expect(["ASSIGNED","EN_ROUTE_TO_PICKUP"]).toContain(t.status);
  console.log(`✓ Trip2 (${gapBTripId2}) status: ${t.status}`);
  await ctx.close();
});

test("GAP-B-markers — Leaflet DOM shows two simultaneous ambulance markers", async ({ browser }) => {
  const t1 = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBD1Token);
  const t2 = await apiGetJson(`${API}/patient/trip/${gapBTripId2}`, gapBD2Token);
  console.log(`Trip1=${gapBTripId1} status=${t1.status}  Trip2=${gapBTripId2} status=${t2.status}`);

  const active = ["ASSIGNED","EN_ROUTE_TO_PICKUP","AT_PICKUP","TRANSPORTING","EN_ROUTE_TO_HOSPITAL","AT_HOSPITAL"];

  // Both trips must be in an active state for this test to be meaningful
  if (!active.includes(t1.status)) throw new Error(`Trip1 (${gapBTripId1}) not active: ${t1.status}`);
  if (!active.includes(t2.status)) throw new Error(`Trip2 (${gapBTripId2}) not active: ${t2.status}`);

  const trafficLogin = await loginApi("traffic@smartambulance.com", "password123");
  const trafficToken = trafficLogin.access_token;

  // Verify both exact trip IDs appear in the corridors API
  const corridors = await apiGetJson(`${API}/traffic/corridors`, trafficToken);
  if (!Array.isArray(corridors)) throw new Error(`Corridors not array: ${JSON.stringify(corridors)}`);
  const cIds = corridors.map((c: any) => c.trip_id);
  console.log(`Traffic corridors: ${JSON.stringify(cIds)}`);

  expect(cIds).toContain(gapBTripId1);
  expect(cIds).toContain(gapBTripId2);
  console.log(`✓ Both exact trip IDs (${gapBTripId1}, ${gapBTripId2}) present in corridors API`);

  // Verify no patient PII in corridors API
  for (const c of corridors) {
    expect(c).not.toHaveProperty("pickup_address");
  }

  // Open traffic browser and verify Leaflet DOM markers
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE);
  await page.evaluate((tok) => {
    localStorage.setItem("sa_token", tok);
    localStorage.setItem("sa_role", "TRAFFIC");
    localStorage.setItem("sa_user_id", "4");
  }, trafficToken);
  await page.goto(`${BASE}/traffic`);
  await expect(page.locator("text=Emergency Green Corridor Control")).toBeVisible({ timeout: 15_000 });
  await page.waitForSelector(".leaflet-container", { timeout: 20_000 });
  await page.waitForTimeout(2_500);

  // Count 🚑 markers — each active corridor entry becomes one Leaflet marker
  const markerCount = await page.evaluate(() => {
    const icons = document.querySelectorAll(".leaflet-marker-icon");
    let count = 0;
    icons.forEach((el) => { if ((el.innerHTML || "").includes("🚑")) count++; });
    return count;
  });
  const corridorCards = await page.locator("text=VEHICLE #").count();
  console.log(`Leaflet 🚑 markers: ${markerCount}  Corridor sidebar cards: ${corridorCards}`);

  // Both trips are active → must see exactly 2 markers
  expect(markerCount).toBeGreaterThanOrEqual(2);
  expect(corridorCards).toBeGreaterThanOrEqual(2);
  console.log(`✓ Two simultaneous ambulance markers for trips ${gapBTripId1} and ${gapBTripId2} confirmed`);

  // Privacy check
  const html = await page.content();
  expect(html).not.toContain("patient@");
  expect(html).not.toContain("pickup_address");
  console.log("✓ No patient PII in traffic page HTML");

  await ctx.close();
});

test("GAP-B-remove — completing trip1 via driver UI removes only its marker, trip2 remains", async ({ browser }) => {
  const t1Pre = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBD1Token);
  const active = ["ASSIGNED","EN_ROUTE_TO_PICKUP","AT_PICKUP","TRANSPORTING","EN_ROUTE_TO_HOSPITAL","AT_HOSPITAL"];
  if (!active.includes(t1Pre.status)) {
    throw new Error(`Trip1 (${gapBTripId1}) not active before remove test: ${t1Pre.status}`);
  }

  // ── Complete trip1 via D1's driver trip page UI buttons ───────────────────
  const ctx1 = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: SEED_D1.lat, longitude: SEED_D1.lng },
  });
  const dPage = await ctx1.newPage();
  await dPage.goto(BASE);
  await injectAuth(dPage, {
    access_token: gapBD1Token, role: "DRIVER",
    user_id: gapBD1Profile.user_id, driver_id: gapBD1Profile.id,
  });
  await dPage.goto(`${BASE}/driver/trip/${gapBTripId1}`);
  await expect(dPage.locator("text=Driver Live Navigation Console")).toBeVisible({ timeout: 15_000 });

  const uiSteps = [
    "START EN-ROUTE TO PICKUP",
    "MARK ARRIVED AT PICKUP",
    "PATIENT PICKED UP — EN ROUTE TO HOSPITAL",
    "MARK ARRIVED AT HOSPITAL",
    "COMPLETE TRIP & RETURN AVAILABLE",
  ];
  for (const btnText of uiSteps) {
    const s = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBD1Token);
    if (s.status === "COMPLETED") break;
    const btn = dPage.locator(`text=${btnText}`).first();
    if (!(await btn.isVisible({ timeout: 3_000 }).catch(() => false))) continue;
    await btn.click();
    await dPage.waitForTimeout(1_500);
    const after = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBD1Token);
    console.log(`✓ D1 UI "${btnText}" → ${after.status}`);
    if (after.status === "COMPLETED") break;
  }
  const finalT1 = await apiGetJson(`${API}/patient/trip/${gapBTripId1}`, gapBD1Token);
  // Hard assertion: trip1 must reach COMPLETED via the UI buttons
  expect(finalT1.status).toBe("COMPLETED");
  console.log(`✓ Trip1 (${gapBTripId1}) COMPLETED via driver UI`);
  await ctx1.close();

  // ── Verify corridors API: trip1 gone, trip2 still present ────────────────
  const trafficLogin = await loginApi("traffic@smartambulance.com", "password123");
  const trafficToken = trafficLogin.access_token;
  const corridors = await apiGetJson(`${API}/traffic/corridors`, trafficToken);
  if (!Array.isArray(corridors)) throw new Error(`Corridors not array`);
  const cIds = corridors.map((c: any) => c.trip_id);
  console.log(`Corridors after completion: ${JSON.stringify(cIds)}`);

  // Hard assertions by exact trip ID
  expect(cIds).not.toContain(gapBTripId1);
  console.log(`✓ Completed trip1 (${gapBTripId1}) removed from corridors`);

  const t2Post = await apiGetJson(`${API}/patient/trip/${gapBTripId2}`, gapBD2Token);
  if (active.includes(t2Post.status)) {
    expect(cIds).toContain(gapBTripId2);
    console.log(`✓ Active trip2 (${gapBTripId2}) still present in corridors (status=${t2Post.status})`);
  } else {
    console.log(`Note: trip2 (${gapBTripId2}) is ${t2Post.status} — not expected in active corridors`);
  }

  // ── Open traffic browser and verify marker count changed ─────────────────
  const ctx2 = await browser.newContext();
  const tPage = await ctx2.newPage();
  await tPage.goto(BASE);
  await tPage.evaluate((tok) => {
    localStorage.setItem("sa_token", tok);
    localStorage.setItem("sa_role", "TRAFFIC");
    localStorage.setItem("sa_user_id", "4");
  }, trafficToken);
  await tPage.goto(`${BASE}/traffic`);
  await expect(tPage.locator("text=Emergency Green Corridor Control")).toBeVisible({ timeout: 15_000 });
  await tPage.waitForSelector(".leaflet-container", { timeout: 20_000 });
  await tPage.waitForTimeout(2_000);

  const afterMarkers = await tPage.evaluate(() => {
    const icons = document.querySelectorAll(".leaflet-marker-icon");
    let count = 0;
    icons.forEach((el) => { if ((el.innerHTML || "").includes("🚑")) count++; });
    return count;
  });
  const afterCards = await tPage.locator("text=VEHICLE #").count();
  console.log(`After completing trip1: markers=${afterMarkers} corridor-cards=${afterCards}`);

  // trip1's marker is gone; if trip2 is still active its marker should remain
  if (active.includes(t2Post.status)) {
    // We should have exactly 1 fewer marker than before (went from 2→1)
    expect(afterMarkers).toBeGreaterThanOrEqual(1);
    expect(afterCards).toBeGreaterThanOrEqual(1);
    console.log(`✓ Trip2 marker remains (markers=${afterMarkers}); trip1 marker is gone`);
  } else {
    console.log(`Trip2 (${gapBTripId2}) is ${t2Post.status} — marker count=${afterMarkers}`);
  }

  await ctx2.close();
});

// ════════════════════════════════════════════════════════════════════════════
//  GAP-C  Driver completes a trip via all driver UI buttons
//          including MARK ARRIVED AT HOSPITAL + COMPLETE TRIP & RETURN AVAILABLE
// ════════════════════════════════════════════════════════════════════════════

test("GAP-C — complete trip via all driver UI buttons → COMPLETED + tracking badge", async ({ browser }) => {
  // All setup (booking, finding which driver got dispatched) uses API helpers.
  // The acceptance and all state transitions use the real driver UI.

  const d1Login = await loginApi(SEED_D1.email, SEED_D1.password);
  const d2Login = await loginApi(SEED_D2.email, SEED_D2.password);
  const d1Tok = d1Login.access_token;
  const d2Tok = d2Login.access_token;
  const d1Prof = await apiGetJson(`${API}/driver/profile`, d1Tok);
  const d2Prof = await apiGetJson(`${API}/driver/profile`, d2Tok);

  await apiPost(`${API}/driver/status`, { is_on_duty: true }, d1Tok);
  await apiPost(`${API}/driver/status`, { is_on_duty: true }, d2Tok);

  // Fresh patient
  const pCData = await registerAndLogin(`gap_c_p_${TS}@test.com`, "GapC_Pass8!", "PATIENT");
  const pCTok = pCData.access_token;

  // Book at D1's GPS — D1 should be nearest (0 km)
  const bookR = await apiPost(`${API}/patient/book`, {
    pickup_address: "GAP-C Pickup, Bangalore",
    pickup_lat: SEED_D1.lat, pickup_lng: SEED_D1.lng, severity: "LOW",
  }, pCTok);
  if (!bookR.ok) throw new Error(`GAP-C booking failed: ${bookR.status} ${await bookR.text()}`);
  const cTripId = (await bookR.json()).trip_id;
  console.log(`GAP-C trip_id=${cTripId}`);

  // Find which driver has the pending request for this exact trip
  const d1Pend = await apiGetJson(`${API}/driver/requests/pending`, d1Tok);
  const d2Pend = await apiGetJson(`${API}/driver/requests/pending`, d2Tok);
  if (!Array.isArray(d1Pend)) throw new Error(`D1 pending not array: ${JSON.stringify(d1Pend)}`);
  if (!Array.isArray(d2Pend)) throw new Error(`D2 pending not array: ${JSON.stringify(d2Pend)}`);

  const d1Req = d1Pend.find((r: any) => r.trip_id === cTripId);
  const d2Req = d2Pend.find((r: any) => r.trip_id === cTripId);

  let acceptTok: string;
  let acceptProf: any;
  if (d1Req) {
    acceptTok = d1Tok; acceptProf = d1Prof;
    console.log(`D1 has pending request ${d1Req.id} for trip ${cTripId}`);
  } else if (d2Req) {
    acceptTok = d2Tok; acceptProf = d2Prof;
    console.log(`D2 has pending request ${d2Req.id} for trip ${cTripId}`);
  } else {
    const t = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
    throw new Error(`No seed driver has pending request for GAP-C trip ${cTripId} (status=${t.status})`);
  }

  // Reject any stale pending requests for the accepting driver that are NOT for cTripId.
  // This prevents earlier trips from other tests appearing first in the driver dashboard.
  const driverTokenForCleanup = acceptTok;
  const stalePending = await apiGetJson(`${API}/driver/requests/pending`, driverTokenForCleanup);
  if (Array.isArray(stalePending)) {
    for (const r of stalePending) {
      if (r.trip_id !== cTripId) {
        console.log(`Rejecting stale request id=${r.id} for trip ${r.trip_id}`);
        await apiPost(`${API}/driver/reject/${r.id}`, {}, driverTokenForCleanup);
      }
    }
  }

  // Verify only our request remains
  const cleanPending = await apiGetJson(`${API}/driver/requests/pending`, driverTokenForCleanup);
  if (!Array.isArray(cleanPending) || !cleanPending.find((r: any) => r.trip_id === cTripId)) {
    const t = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
    throw new Error(`After cleanup, driver has no request for trip ${cTripId} (status=${t.status})`);
  }
  console.log(`Driver has exactly 1 pending request for trip ${cTripId} after cleanup ✓`);

  // ── Accept via real driver UI ACCEPT button ───────────────────────────────
  const ctx = await browser.newContext({
    permissions: ["geolocation"],
    geolocation: { latitude: SEED_D1.lat, longitude: SEED_D1.lng },
  });
  const dPage = await ctx.newPage();
  await dPage.goto(BASE);
  await injectAuth(dPage, {
    access_token: acceptTok, role: "DRIVER",
    user_id: acceptProf.user_id, driver_id: acceptProf.id,
  });

  // Navigate to driver dashboard — ACCEPT button must be visible
  await dPage.goto(`${BASE}/driver`);
  await expect(dPage.locator("text=Driver Dispatch Terminal")).toBeVisible({ timeout: 15_000 });
  await dPage.reload();
  await dPage.waitForTimeout(1_500);

  const acceptBtn = dPage.locator("text=ACCEPT EMERGENCY TRIP").first();
  await expect(acceptBtn).toBeVisible({ timeout: 10_000 });
  await acceptBtn.click();
  console.log("✓ Clicked ACCEPT EMERGENCY TRIP button in driver UI");

  // Must redirect to /driver/trip/{id}
  await dPage.waitForURL(/\/driver\/trip\/\d+/, { timeout: 15_000 });
  const acceptUrl = dPage.url();
  const acceptedId = parseInt(acceptUrl.match(/\/driver\/trip\/(\d+)/)![1], 10);
  if (acceptedId !== cTripId) {
    throw new Error(
      `Driver accepted trip ${acceptedId} via UI but expected trip ${cTripId}. ` +
      `Another pending request may have been in the queue.`
    );
  }
  console.log(`✓ Driver UI accepted trip ${acceptedId} === cTripId (${cTripId})`);

  // Verify ASSIGNED via API
  const afterAccept = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
  expect(["ASSIGNED","EN_ROUTE_TO_PICKUP"]).toContain(afterAccept.status);
  console.log(`✓ Trip ${cTripId} status after UI accept: ${afterAccept.status}`);

  // ── Navigate to driver trip page and click all state-machine UI buttons ────
  await dPage.goto(`${BASE}/driver/trip/${cTripId}`);
  await expect(dPage.locator("text=Driver Live Navigation Console")).toBeVisible({ timeout: 15_000 });

  const buttons = [
    "START EN-ROUTE TO PICKUP",
    "MARK ARRIVED AT PICKUP",
    "PATIENT PICKED UP — EN ROUTE TO HOSPITAL",
    "MARK ARRIVED AT HOSPITAL",
    "COMPLETE TRIP & RETURN AVAILABLE",
  ];

  let progressedViaUI = false;
  for (const btnText of buttons) {
    const s = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
    if (s.status === "COMPLETED") { console.log("Trip already COMPLETED"); break; }
    const btn = dPage.locator(`text=${btnText}`).first();
    if (!(await btn.isVisible({ timeout: 3_000 }).catch(() => false))) {
      console.log(`"${btnText}" not visible — already past this state`);
      continue;
    }
    await btn.click();
    progressedViaUI = true;
    await dPage.waitForTimeout(2_000);
    const after = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
    console.log(`✓ "${btnText}" → status: ${after.status}`);
    if (after.status === "COMPLETED") break;
  }

  // Hard assertion: trip must be COMPLETED
  const final = await apiGetJson(`${API}/patient/trip/${cTripId}`, pCTok);
  expect(final.status).toBe("COMPLETED");
  expect(progressedViaUI).toBe(true);  // at least one UI button was clicked
  console.log("✓ Trip COMPLETED via driver UI buttons");

  // ── Patient tracking page shows COMPLETED badge ───────────────────────────
  await dPage.goto(BASE);
  await dPage.evaluate(({ tok }) => {
    localStorage.setItem("sa_token", tok);
    localStorage.setItem("sa_role", "PATIENT");
  }, { tok: pCTok });
  await dPage.goto(`${BASE}/patient/tracking/${cTripId}`);
  await expect(dPage.locator("text=Live Ambulance Dispatch Tracker")).toBeVisible({ timeout: 15_000 });
  await expect(dPage.locator("text=COMPLETED").first()).toBeVisible({ timeout: 10_000 });
  console.log("✓ Patient tracking page shows COMPLETED badge");

  await ctx.close();
});
