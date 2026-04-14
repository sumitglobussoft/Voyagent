import { SignIn } from "@clerk/nextjs";

/**
 * Sign-in page.
 *
 * The `[[...sign-in]]` optional catch-all lets Clerk own nested routes
 * (e.g. `/sign-in/factor-one`) without us re-declaring them. The
 * component reads its styling defaults from the Clerk dashboard.
 */
export default function SignInPage() {
  return (
    <main
      style={{
        minHeight: "calc(100dvh - 56px)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <SignIn path="/sign-in" />
    </main>
  );
}
