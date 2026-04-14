/**
 * React context wrapping the desktop Clerk client.
 *
 * Responsibilities:
 *   - Instantiate `ClerkClient` once and hold it for the app lifetime.
 *   - Mount `<DeepLinkHandler>` so the OAuth redirect is captured.
 *   - Rehydrate the stored token on mount and expose an `isAuthenticated`
 *     boolean consumers can gate UI on.
 *   - Surface `signIn`, `signOut`, and `getToken` to the rest of the app.
 *
 * Environment:
 *   - `VITE_CLERK_PUBLISHABLE_KEY` — required. The Vite build fails fast
 *     if it's missing, but at runtime we degrade to a clear error state
 *     so the dev doesn't have to restart the whole Tauri loop.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { ClerkClient, type DesktopUser } from "./ClerkClient.js";
import { DeepLinkHandler } from "./DeepLinkHandler.js";

export interface AuthContextValue {
  isReady: boolean;
  isAuthenticated: boolean;
  user: DesktopUser | null;
  getToken: () => Promise<string | null>;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readEnv(key: string): string | undefined {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  return typeof raw === "string" && raw.length > 0 ? raw : undefined;
}

export interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps): ReactElement {
  const clerk = useMemo(() => {
    const key = readEnv("VITE_CLERK_PUBLISHABLE_KEY");
    if (!key) {
      // Deferred to runtime so the dev loop keeps running; the sign-in
      // screen surfaces a helpful error below.
      return null;
    }
    return new ClerkClient({
      publishableKey: key,
      redirectUri: "voyagent://auth/callback",
    });
  }, []);

  const [isReady, setIsReady] = useState(false);
  const [tick, setTick] = useState(0);
  const bump = useCallback(() => {
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    if (clerk === null) {
      setIsReady(true);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        await clerk.init();
      } finally {
        if (!cancelled) {
          setIsReady(true);
          bump();
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bump, clerk]);

  const value: AuthContextValue = useMemo(() => {
    // tick is intentionally read so re-renders pick up session changes
    // after signIn / applySession / signOut.
    void tick;
    return {
      isReady,
      isAuthenticated: clerk?.isAuthenticated ?? false,
      user: clerk?.user ?? null,
      getToken: async () => (clerk ? clerk.getToken() : null),
      signIn: async () => {
        if (clerk) await clerk.signIn();
      },
      signOut: async () => {
        if (clerk) {
          await clerk.signOut();
          bump();
        }
      },
    };
  }, [bump, clerk, isReady, tick]);

  return (
    <AuthContext.Provider value={value}>
      {clerk !== null ? (
        <DeepLinkHandler clerk={clerk} onCaptured={bump} />
      ) : null}
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be called inside <AuthProvider>.");
  }
  return ctx;
}
