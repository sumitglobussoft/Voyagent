"use server";

/**
 * Server actions for the enquiries CRUD.
 *
 * The create action redirects to the detail page on success and
 * re-renders the create form with an error banner on failure (via
 * `useFormState`-style state).
 *
 * The edit action is used for both field edits and status changes; it
 * reads a form and PATCHes whatever fields were submitted. Missing keys
 * are left alone, as per the API contract.
 *
 * The cancel action is a two-step: first click sends `?confirm=1`,
 * second click (with `?confirm=1` already in the URL) actually PATCHes
 * status=cancelled.
 */
import { redirect } from "next/navigation";

import { apiErrorCode, apiPatch, apiPost } from "@/lib/api";

export type CreateEnquiryState = {
  error: string | null;
  values: Record<string, string>;
};

/**
 * Trim + lowercase-check a form string. Returns null when empty so the
 * field can be omitted from the JSON body (API treats missing as "leave
 * alone"; null as "clear"). For create we just drop empties.
 */
function optString(v: FormDataEntryValue | null): string | null {
  if (v === null) return null;
  const s = String(v).trim();
  return s ? s : null;
}

function toPaxCount(v: FormDataEntryValue | null): number | null {
  if (v === null) return null;
  const s = String(v).trim();
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) return null;
  return n;
}

function snapshotValues(fd: FormData): Record<string, string> {
  const keys = [
    "customer_name",
    "customer_email",
    "customer_phone",
    "origin",
    "destination",
    "depart_date",
    "return_date",
    "pax_count",
    "budget_amount",
    "budget_currency",
    "notes",
    "status",
  ];
  const out: Record<string, string> = {};
  for (const k of keys) {
    const v = fd.get(k);
    if (typeof v === "string") out[k] = v;
  }
  return out;
}

const CREATE_ERRORS: Record<string, string> = {
  invalid_request: "Please double-check the form and try again.",
  forbidden_cross_tenant: "You don't have permission to do that.",
};

function createErrorMessage(code: string | null, fallback: string): string {
  if (!code) return fallback;
  return CREATE_ERRORS[code] ?? `${fallback} (${code})`;
}

export async function createEnquiryAction(
  _prev: CreateEnquiryState,
  formData: FormData,
): Promise<CreateEnquiryState> {
  const values = snapshotValues(formData);

  const customer_name = optString(formData.get("customer_name"));
  const pax_count = toPaxCount(formData.get("pax_count"));

  if (!customer_name) {
    return { error: "Customer name is required.", values };
  }
  if (pax_count === null) {
    return {
      error: "Pax count is required and must be a positive whole number.",
      values,
    };
  }

  const body: Record<string, unknown> = {
    customer_name,
    pax_count,
  };
  const addOpt = (key: string, v: string | null) => {
    if (v !== null) body[key] = v;
  };
  addOpt("customer_email", optString(formData.get("customer_email")));
  addOpt("customer_phone", optString(formData.get("customer_phone")));
  addOpt("origin", optString(formData.get("origin")));
  addOpt("destination", optString(formData.get("destination")));
  addOpt("depart_date", optString(formData.get("depart_date")));
  addOpt("return_date", optString(formData.get("return_date")));
  addOpt("budget_amount", optString(formData.get("budget_amount")));
  const currency = optString(formData.get("budget_currency"));
  if (currency !== null) body.budget_currency = currency.toUpperCase();
  addOpt("notes", optString(formData.get("notes")));

  const res = await apiPost<{ id: string }>("/api/enquiries", body);
  if (res.ok && res.data && typeof res.data.id === "string") {
    redirect(`/enquiries/${res.data.id}`);
  }
  const code = apiErrorCode(res.data);
  return {
    error: createErrorMessage(code, "Could not create enquiry."),
    values,
  };
}

/**
 * Edit enquiry fields. Blank text inputs become `null` (clear) for
 * nullable fields; pax_count stays a number and is always sent.
 *
 * Redirects to the detail page on success. On failure redirects to the
 * detail page with `?err=<code>` so the page can render a banner. We
 * don't round-trip form values here because PATCH is rarely rejected
 * mid-edit and the fields are still on screen to re-submit.
 */
export async function patchEnquiryAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "").trim();
  if (!id) redirect("/enquiries");

  const body: Record<string, unknown> = {};
  const nullableFields = [
    "customer_email",
    "customer_phone",
    "origin",
    "destination",
    "depart_date",
    "return_date",
    "budget_amount",
    "budget_currency",
    "notes",
  ];
  for (const f of nullableFields) {
    if (!formData.has(f)) continue;
    const raw = String(formData.get(f) ?? "").trim();
    body[f] = raw === "" ? null : f === "budget_currency" ? raw.toUpperCase() : raw;
  }
  if (formData.has("customer_name")) {
    const v = String(formData.get("customer_name") ?? "").trim();
    if (v) body.customer_name = v;
  }
  if (formData.has("pax_count")) {
    const n = toPaxCount(formData.get("pax_count"));
    if (n !== null) body.pax_count = n;
  }

  const res = await apiPatch(`/api/enquiries/${encodeURIComponent(id)}`, body);
  if (res.ok) {
    redirect(`/enquiries/${id}`);
  }
  const code = apiErrorCode(res.data) ?? `status_${res.status}`;
  redirect(`/enquiries/${id}?err=${encodeURIComponent(code)}`);
}

/**
 * Status-only PATCH. Separate action so the detail page can wire a
 * small dropdown+button without colliding with the big edit form.
 */
export async function changeStatusAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "").trim();
  const status = String(formData.get("status") ?? "").trim();
  if (!id || !status) redirect("/enquiries");

  const res = await apiPatch(`/api/enquiries/${encodeURIComponent(id)}`, { status });
  if (res.ok) {
    redirect(`/enquiries/${id}`);
  }
  const code = apiErrorCode(res.data) ?? `status_${res.status}`;
  redirect(`/enquiries/${id}?err=${encodeURIComponent(code)}`);
}

/**
 * Two-step cancel. If `confirm=1` is not present we just redirect to
 * the detail page with `?confirm=1`, which causes the page to render a
 * "Click again to confirm" banner. On the second click the form comes
 * in with confirm=1 already set; we then PATCH status=cancelled.
 */
export async function cancelEnquiryAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "").trim();
  const confirm = String(formData.get("confirm") ?? "").trim();
  if (!id) redirect("/enquiries");

  if (confirm !== "1") {
    redirect(`/enquiries/${id}?confirm=1`);
  }

  const res = await apiPatch(`/api/enquiries/${encodeURIComponent(id)}`, {
    status: "cancelled",
  });
  if (res.ok) {
    redirect(`/enquiries/${id}`);
  }
  const code = apiErrorCode(res.data) ?? `status_${res.status}`;
  redirect(`/enquiries/${id}?err=${encodeURIComponent(code)}`);
}

/**
 * Promote to a chat session. On success redirect to
 * `/chat?session_id=...`. If the enquiry already has a session we still
 * redirect to chat with that session id — the API returns the existing
 * session rather than 409'ing.
 */
export async function promoteEnquiryAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "").trim();
  if (!id) redirect("/enquiries");

  const res = await apiPost<{ session_id: string }>(
    `/api/enquiries/${encodeURIComponent(id)}/promote-to-session`,
  );
  if (res.ok && res.data && typeof res.data.session_id === "string") {
    redirect(`/chat?session_id=${encodeURIComponent(res.data.session_id)}`);
  }
  const code = apiErrorCode(res.data) ?? `status_${res.status}`;
  redirect(`/enquiries/${id}?err=${encodeURIComponent(code)}`);
}
