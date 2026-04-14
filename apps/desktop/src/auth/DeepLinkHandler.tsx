/**
 * Listens for `voyagent://auth/callback?session=<token>` redirects coming
 * out of the hosted Clerk flow and forwards the captured session token to
 * the Clerk client via `applySession`.
 *
 * The deep-link plugin also fires once on cold start with the URL the app
 * was launched from, which is the happy-path case when Windows / macOS
 * hand off the callback URL directly (vs. routing it into a running
 * instance).
 */
import { onOpenUrl } from "@tauri-apps/plugin-deep-link";
import { useEffect, type ReactElement } from "react";

import type { ClerkClient } from "./ClerkClient.js";

export interface DeepLinkHandlerProps {
  clerk: ClerkClient;
  /** Called after a callback URL has been fully processed. */
  onCaptured?: () => void;
}

function extractSessionToken(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl);
    // Accept both `?session=...` and `#session=...` — Clerk has used
    // both depending on the hosted-page configuration.
    const fromQuery = url.searchParams.get("session");
    if (fromQuery) return fromQuery;
    if (url.hash.length > 1) {
      const hash = new URLSearchParams(url.hash.slice(1));
      const fromHash = hash.get("session");
      if (fromHash) return fromHash;
    }
    return null;
  } catch {
    return null;
  }
}

export function DeepLinkHandler({
  clerk,
  onCaptured,
}: DeepLinkHandlerProps): ReactElement | null {
  useEffect(() => {
    let cancelled = false;
    const unsubscribePromise = onOpenUrl((urls) => {
      if (cancelled) return;
      for (const raw of urls) {
        if (!raw.startsWith("voyagent://auth/callback")) continue;
        const token = extractSessionToken(raw);
        if (!token) continue;
        void (async () => {
          await clerk.applySession(token);
          onCaptured?.();
        })();
        return;
      }
    });
    return () => {
      cancelled = true;
      void unsubscribePromise.then((unlisten) => {
        try {
          unlisten();
        } catch {
          /* ignore */
        }
      });
    };
  }, [clerk, onCaptured]);

  return null;
}
