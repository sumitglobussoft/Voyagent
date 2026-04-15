"use server";

import { redirect } from "next/navigation";

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

export async function forgotPasswordAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim();
  if (!email) {
    redirect("/forgot-password");
  }
  try {
    await fetch(`${apiBase()}/api/auth/request-password-reset`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ email }),
      cache: "no-store",
    });
  } catch (err) {
    console.error("forgot-password action failed", err);
  }
  // Always land on the success screen — we never leak whether the
  // address is registered.
  redirect("/forgot-password?submitted=1");
}
