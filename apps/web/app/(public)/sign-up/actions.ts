"use server";

import { redirect } from "next/navigation";

import { setSessionCookies, signUp } from "@/lib/auth";
import { safeNextPath } from "@/lib/next-url";

export type SignUpState = {
  error: string | null;
};

export async function signUpAction(
  _prevState: SignUpState,
  formData: FormData,
): Promise<SignUpState> {
  const full_name = String(formData.get("full_name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const agency_name = String(formData.get("agency_name") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm_password") ?? "");
  // Mirror sign-in: if sign-up was reached via a deep link (e.g.
  // /app/sign-up?next=/enquiries) honour the target after account
  // creation. Fresh accounts land on /chat?welcome=1 when there's no
  // explicit next; otherwise they go to the requested page.
  const rawNext =
    typeof formData.get("next") === "string"
      ? (formData.get("next") as string)
      : "";
  const validatedNext = safeNextPath(rawNext);
  const hadExplicitNext = rawNext !== "" && validatedNext === rawNext;

  if (!full_name || !email || !agency_name || !password) {
    return { error: "All fields are required." };
  }
  if (password.length < 12) {
    return { error: "Password must be at least 12 characters." };
  }
  if (password !== confirm) {
    return { error: "Passwords do not match." };
  }

  const result = await signUp({ email, password, full_name, agency_name });
  if ("error" in result) {
    if (result.error === "email_already_registered") {
      return { error: "An account with that email already exists." };
    }
    if (result.error === "invalid_request") {
      return { error: "Please double-check the form and try again." };
    }
    return { error: "Something went wrong. Please try again." };
  }

  await setSessionCookies(
    result.access_token,
    result.refresh_token,
    result.expires_in,
  );
  redirect(hadExplicitNext ? validatedNext : "/chat?welcome=1");
}
