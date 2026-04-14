import { SignUp } from "@clerk/nextjs";

/**
 * Sign-up page.
 *
 * Mirrors `sign-in/[[...sign-in]]` — Clerk handles every nested step
 * (email verification, invited-member flows, etc.) beneath this route.
 */
export default function SignUpPage() {
  return (
    <main
      style={{
        minHeight: "calc(100dvh - 56px)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <SignUp path="/sign-up" />
    </main>
  );
}
