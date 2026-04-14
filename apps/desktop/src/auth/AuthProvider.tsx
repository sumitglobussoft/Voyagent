/**
 * React context wrapping the in-house Voyagent auth client.
 *
 * Holds one `VoyagentAuthClient` for the app lifetime, hydrates the
 * stored session on mount, and exposes `signIn`, `signUp`, `signOut`
 * to the rest of the app. Token refresh is handled inside the client
 * via `getAccessToken()` — callers should use that getter rather than
 * caching the token themselves.
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

import {
  VoyagentAuthClient,
  type DesktopUser,
  type SignInInput,
  type SignUpInput,
} from "./VoyagentAuthClient.js";

export interface AuthContextValue {
  isReady: boolean;
  isAuthenticated: boolean;
  user: DesktopUser | null;
  getToken: () => Promise<string | null>;
  signIn: (input: SignInInput) => Promise<void>;
  signUp: (input: SignUpInput) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readEnv(key: string, fallback: string): string {
  const raw = (import.meta.env as Record<string, string | undefined>)[key];
  return typeof raw === "string" && raw.length > 0 ? raw : fallback;
}

export interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps): ReactElement {
  const client = useMemo(
    () =>
      new VoyagentAuthClient({
        baseUrl: readEnv("VITE_VOYAGENT_API_URL", "http://localhost:8000"),
      }),
    [],
  );

  const [isReady, setIsReady] = useState(false);
  const [tick, setTick] = useState(0);
  const bump = useCallback(() => {
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await client.init();
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
  }, [bump, client]);

  const value: AuthContextValue = useMemo(() => {
    void tick;
    return {
      isReady,
      isAuthenticated: client.isAuthenticated,
      user: client.user,
      getToken: () => client.getAccessToken(),
      signIn: async (input) => {
        await client.signIn(input);
        bump();
      },
      signUp: async (input) => {
        await client.signUp(input);
        bump();
      },
      signOut: async () => {
        await client.signOut();
        bump();
      },
    };
  }, [bump, client, isReady, tick]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be called inside <AuthProvider>.");
  }
  return ctx;
}
