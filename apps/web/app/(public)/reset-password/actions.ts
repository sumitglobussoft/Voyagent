"use server";

import { redirect } from "next/navigation";

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

export async function resetPasswordAction(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "");
  const pw = String(formData.get("new_password") ?? "");
  const confirm = String(formData.get("confirm_password") ?? "");
  const back = (msg: string) =>
    redirect(
      `/reset-password?token=${encodeURIComponent(token)}&error=${encodeURIComponent(msg)}`,
    );

  if (!token) {
    redirect("/forgot-password");
  }
  if (pw.length < 12) {
    back("Password must be at least 12 characters.");
  }
  if (pw !== confirm) {
    back("Passwords do not match.");
  }

  let res: Response | null = null;
  try {
    res = await fetch(`${apiBase()}/api/auth/reset-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ token, new_password: pw }),
      cache: "no-store",
    });
  } catch (err) {
    console.error("reset-password fetch failed", err);
    back("Something went wrong. Please try again.");
  }
  if (!res || !res.ok) {
    back("That reset link is invalid or has expired.");
  }
  redirect("/sign-in?reset=1");
}
