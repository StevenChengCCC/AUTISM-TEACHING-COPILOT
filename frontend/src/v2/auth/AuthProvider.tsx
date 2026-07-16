import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  authConfig,
  beginLogin,
  completeLoginFromUrl,
  decodeTokenClaims,
  logout,
  readSession,
} from "./authSession";

type AuthUser = { subject: string; displayName: string; email?: string };
type AuthState = {
  status: "loading" | "authenticated" | "anonymous" | "expired" | "error";
  user: AuthUser | null;
  error: string;
  signIn: () => Promise<void>;
  signOut: () => void;
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
        if (!active) return;
        const nextUser = userFromSession();
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

  const value = useMemo<AuthState>(
    () => ({ status, user, error, signIn: beginLogin, signOut: logout }),
    [status, user, error],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}

