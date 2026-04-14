import { redirect } from "next/navigation";

/**
 * Web app root.
 *
 * With ``basePath: "/app"`` the file at ``app/page.tsx`` is served at
 * ``/app``. We don't want a landing page here — the marketing app owns
 * the public face. Anyone hitting ``/app`` directly is bounced to the
 * chat workspace, which the middleware will in turn bounce to
 * ``/app/sign-in`` if there's no session.
 */
export default function AppRoot(): never {
  redirect("/chat");
}
