import { redirect } from "next/navigation";

/**
 * Web app root.
 *
 * With ``basePath: "/app"`` the file at ``app/page.tsx`` is served at
 * ``/app``. We don't want a landing page here — the marketing app owns
 * the public face. Anyone hitting ``/app`` directly is bounced to the
 * chat workspace, which the middleware will in turn bounce to
 * ``/app/sign-in`` if there's no session.
 *
 * We pass the basePath-inclusive ``/app/chat`` to ``redirect()``
 * explicitly rather than the bare ``/chat``. Next auto-prepends
 * basePath to bare paths, but that code path interacts badly with the
 * trailing-slash normalizer when the incoming request is ``/app`` vs
 * ``/app/`` — we have observed it emitting ``Location: /app`` which
 * bounces off any nginx rule that then rewrites ``/app`` back.
 * Passing the full prefixed path sidesteps the ambiguity.
 */
export default function AppRoot(): never {
  redirect("/app/chat");
}
