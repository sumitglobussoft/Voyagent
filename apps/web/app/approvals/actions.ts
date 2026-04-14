"use server";

/**
 * Server actions for the approvals inbox.
 *
 * The "resolve" action is a single form-post for both Approve and
 * Reject; the button's `name="granted"` value distinguishes them.
 * On success the caller lands back on /approvals with either no query
 * params (clean state) or an `?err=<code>` marker so the list page can
 * surface a banner on the next render.
 */
import { redirect } from "next/navigation";

import { apiErrorCode, apiPost } from "@/lib/api";

export async function resolveApprovalAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "").trim();
  const grantedRaw = String(formData.get("granted") ?? "").trim();
  const reason = String(formData.get("reason") ?? "").trim();

  if (!id || (grantedRaw !== "true" && grantedRaw !== "false")) {
    redirect("/approvals?err=invalid_request");
  }

  const body: { granted: boolean; reason?: string } = {
    granted: grantedRaw === "true",
  };
  if (reason) body.reason = reason;

  const res = await apiPost(`/api/approvals/${encodeURIComponent(id)}/resolve`, body);

  if (res.ok) {
    redirect("/approvals");
  }

  const code = apiErrorCode(res.data) ?? `status_${res.status}`;
  redirect(`/approvals?err=${encodeURIComponent(code)}`);
}
