"use server";

import { redirect } from "next/navigation";

import { setSessionCookies } from "@/lib/auth";

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

type AuthPayload = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export async function acceptInviteAction(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "");
  const full_name = String(formData.get("full_name") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm_password") ?? "");

  const fail = (msg: string) =>
    redirect(
      `/accept-invite?token=${encodeURIComponent(token)}&error=${encodeURIComponent(msg)}`,
    );

  if (!token) {
    redirect("/sign-in");
  }
  if (!full_name) fail("Please enter your full name.");
  if (password.length < 12) fail("Password must be at least 12 characters.");
  if (password !== confirm) fail("Passwords do not match.");

  let res: Response | null = null;
  try {
    res = await fetch(`${apiBase()}/api/auth/accept-invite`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ token, password, full_name }),
      cache: "no-store",
    });
  } catch (err) {
    console.error("accept-invite fetch failed", err);
    fail("Something went wrong. Please try again.");
  }
  if (!res || !res.ok) {
    fail("That invite link is invalid, revoked, or expired.");
    return;
  }
  const data = (await res.json()) as AuthPayload;
  await setSessionCookies(
    data.access_token,
    data.refresh_token,
    data.expires_in,
  );
  redirect("/chat?welcome=1");
}
