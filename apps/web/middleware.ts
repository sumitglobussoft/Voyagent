/**
 * Clerk authentication middleware for the Voyagent web app.
 *
 * Gates `/chat(.*)` behind a signed-in user. The landing page (`/`) and
 * the sign-in / sign-up routes are left public so first-time visitors can
 * hit Clerk's hosted flow without a redirect loop.
 *
 * Anything not explicitly matched by `config.matcher` below skips
 * middleware entirely — static assets and Next internals must stay out
 * of the auth path to avoid a perf hit on every file request.
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
]);

const isProtectedRoute = createRouteMatcher(["/chat(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return;
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Match everything except Next internals + static files. Mirrors
    // Clerk's recommended matcher for App Router deployments.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
