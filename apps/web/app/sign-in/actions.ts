"use server";

import { redirect } from "next/navigation";

import { setSessionCookies, signIn } from "@/lib/auth";

export type SignInState = {
  error: string | null;
};

export async function signInAction(
  _prevState: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "") || "/app/chat";

  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  const result = await signIn({ email, password });
  if ("error" in result) {
    if (result.error === "invalid_credentials") {
      return { error: "Email or password is incorrect." };
    }
    return { error: "Something went wrong. Please try again." };
  }

  setSessionCookies(result.access_token, result.refresh_token, result.expires_in);
  redirect(next);
}
