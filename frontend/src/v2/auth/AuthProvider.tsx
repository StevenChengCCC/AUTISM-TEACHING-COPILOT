import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  authConfig,
  beginLogin,
  beginPasswordReset,
  completeLoginFromUrl,
  decodeTokenClaims,
  getBearerToken,
  logout,
  readSession,
} from "./authSession";

type AuthUser = { subject: string; displayName: string; email?: string };
type AuthState = {
  status: "loading" | "authenticated" | "anonymous" | "expired" | "error";
  user: AuthUser | null;
  error: string;
  signIn: (loginHint?: string) => Promise<void>;
  resetPassword: (loginHint?: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

function userFromSession(): AuthUser | null {
  const session = readSession();
  if (!session) return null;
  const claims = decodeTokenClaims(session.idToken);
  return {
    subject: String(claims.sub ?? "teacher"),
    displayName: String(claims.name ?? claims.given_name ?? claims.email ?? "Teacher"),
    email: claims.email ? String(claims.email) : undefined,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function initialize() {
      if (authConfig.mode === "demo") {
        if (active) {
          setUser({ subject: "demo-teacher", displayName: "Demo Teacher" });
          setStatus("authenticated");
        }
        return;
      }
      try {
        await completeLoginFromUrl();
        const token = await getBearerToken();
        if (!active) return;
        const nextUser = token ? userFromSession() : null;
        setUser(nextUser);
        setStatus(nextUser ? "authenticated" : "anonymous");
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Sign-in could not be completed.");
        setStatus("error");
      }
    }
    void initialize();
    const expired = () => {
      setUser(null);
      setStatus("expired");
    };
    window.addEventListener("lessonkit:session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("lessonkit:session-expired", expired);
    };
  }, []);

  useEffect(() => {
    if (status !== "authenticated") return;
    let disposed = false;
    let timer = 0;

    const schedule = () => {
      const session = readSession();
      if (!session) return;
      const delay = Math.max(5_000, session.expiresAt - Date.now() - 2 * 60 * 1000);
      timer = window.setTimeout(() => void maintain(), delay);
    };
    const maintain = async () => {
      window.clearTimeout(timer);
      try {
        const token = await getBearerToken();
        if (disposed) return;
        if (!token) {
          setUser(null);
          setStatus("expired");
          return;
        }
        setUser(userFromSession());
        setError("");
        schedule();
      } catch {
        if (!disposed) {
          // A transient network/provider failure must not destroy a valid local
          // session. Retry shortly and let API calls surface a retryable error.
          timer = window.setTimeout(() => void maintain(), 30_000);
        }
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void maintain();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    schedule();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [status]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      error,
      signIn: beginLogin,
      resetPassword: beginPasswordReset,
      signOut: logout,
    }),
    [status, user, error],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
