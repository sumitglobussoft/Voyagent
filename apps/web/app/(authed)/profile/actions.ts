"use server";

import { redirect } from "next/navigation";

import { apiErrorCode, apiPatch, type UpdateProfileResponse } from "@/lib/api";

export async function updateProfileAction(formData: FormData): Promise<void> {
  const full_name = String(formData.get("full_name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();

  if (!full_name || !email) {
    redirect(
      `/profile?status=err&msg=${encodeURIComponent("All fields are required.")}`,
    );
  }

  const res = await apiPatch<UpdateProfileResponse>("/api/auth/profile", {
    full_name,
    email,
  });

  if (!res.ok || !res.data) {
    const code = apiErrorCode(res.data) ?? "request_failed";
    let msg = "Could not save changes.";
    if (code === "email_already_registered") {
      msg = "That email is already registered to another account.";
    }
    redirect(`/profile?status=err&msg=${encodeURIComponent(msg)}`);
  }

  const flash = res.data.email_verification_required
    ? "Profile updated — please verify your new email address."
    : "Profile updated.";
  redirect(`/profile?status=ok&msg=${encodeURIComponent(flash)}`);
}
