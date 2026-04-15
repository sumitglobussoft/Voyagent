"use server";

import { redirect } from "next/navigation";

import { setSessionCookies, signIn } from "@/lib/auth";
import { safeNextPath } from "@/lib/next-url";

export type SignInState = {
  error: string | null;
};

export async function signInAction(
  _prevState: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  // `next` arrives without the /app basePath because the middleware
  // strips it before passing through. Default redirects also live under
  // basePath so they're un-prefixed here. safeNextPath() rejects any
  // value that could turn this form into an open-redirect (protocol,
  // protocol-relative, backslash, non-leading-slash).
  const next = safeNextPath(
    typeof formData.get("next") === "string"
      ? (formData.get("next") as string)
      : "",
  );

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

  await setSessionCookies(
    result.access_token,
    result.refresh_token,
    result.expires_in,
  );
  redirect(next);
}
