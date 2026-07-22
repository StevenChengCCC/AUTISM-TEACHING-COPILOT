export type AuthMode = "demo" | "cognito";

export type BrowserSession = {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  expiresAt: number;
};

const SESSION_KEY = "autism-teaching-copilot.auth-session";
const PKCE_KEY = "autism-teaching-copilot.pkce";

export const authConfig = {
  mode: (import.meta.env.VITE_AUTH_MODE ?? "demo") as AuthMode,
  region: import.meta.env.VITE_COGNITO_REGION ?? "",
  userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "",
  clientId: import.meta.env.VITE_COGNITO_APP_CLIENT_ID ?? "",
  domain: (import.meta.env.VITE_COGNITO_DOMAIN ?? "").replace(/\/$/, ""),
  redirectUri: import.meta.env.VITE_COGNITO_REDIRECT_URI ?? window.location.origin,
  logoutUri: import.meta.env.VITE_COGNITO_LOGOUT_URI ?? window.location.origin,
  scopes: import.meta.env.VITE_COGNITO_SCOPES ?? "openid email profile",
  phoneSignInEnabled: import.meta.env.VITE_COGNITO_PHONE_SIGN_IN === "true",
};

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => (binary += String.fromCharCode(value)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomValue(length = 48): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return encodeBase64Url(bytes);
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return encodeBase64Url(new Uint8Array(digest));
}

function requireCognitoConfig(): void {
  if (!authConfig.clientId || !authConfig.domain || !authConfig.redirectUri) {
    throw new Error("Cognito browser configuration is incomplete.");
  }
}

export function readSession(): BrowserSession | null {
  const value = sessionStorage.getItem(SESSION_KEY);
  if (!value) return null;
  try {
    const session = JSON.parse(value) as BrowserSession;
    return session;
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

function saveSession(session: BrowserSession): BrowserSession {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(PKCE_KEY);
}

export function decodeTokenClaims(token: string): Record<string, unknown> {
  try {
    const payload = token.split(".")[1];
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=")));
  } catch {
    return {};
  }
}

export async function beginLogin(loginHint = ""): Promise<void> {
  if (authConfig.mode === "demo") {
    window.location.assign(authConfig.redirectUri);
    return;
  }
  requireCognitoConfig();
  const verifier = randomValue();
  const state = randomValue(24);
  const challenge = await challengeFor(verifier);
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, state }));
  const query = new URLSearchParams({
    response_type: "code",
    client_id: authConfig.clientId,
    redirect_uri: authConfig.redirectUri,
    scope: authConfig.scopes,
    state,
    code_challenge_method: "S256",
    code_challenge: challenge,
  });
  if (loginHint.trim()) query.set("login_hint", loginHint.trim());
  window.location.assign(`${authConfig.domain}/oauth2/authorize?${query}`);
}

async function exchangeToken(body: URLSearchParams): Promise<BrowserSession> {
  requireCognitoConfig();
  const response = await fetch(`${authConfig.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error("Cognito could not complete the sign-in request.");
  const payload = (await response.json()) as {
    access_token: string;
    id_token: string;
    refresh_token?: string;
    expires_in: number;
  };
  const previous = readSession();
  return saveSession({
    accessToken: payload.access_token,
    idToken: payload.id_token,
    refreshToken: payload.refresh_token ?? previous?.refreshToken ?? "",
    expiresAt: Date.now() + payload.expires_in * 1000,
  });
}

export async function completeLoginFromUrl(): Promise<BrowserSession | null> {
  const query = new URLSearchParams(window.location.search);
  if (query.get("error")) {
    window.history.replaceState({}, document.title, window.location.pathname);
    throw new Error(query.get("error_description") ?? "Cognito did not complete sign-in.");
  }
  const code = query.get("code");
  if (!code) return null;
  const returnedState = query.get("state");
  const savedValue = sessionStorage.getItem(PKCE_KEY);
  if (!savedValue) throw new Error("The sign-in request expired. Start again.");
  const saved = JSON.parse(savedValue) as { verifier: string; state: string };
  if (!returnedState || returnedState !== saved.state) {
    throw new Error("The sign-in request could not be verified.");
  }
  const session = await exchangeToken(
    new URLSearchParams({
      grant_type: "authorization_code",
      client_id: authConfig.clientId,
      redirect_uri: authConfig.redirectUri,
      code,
      code_verifier: saved.verifier,
    }),
  );
  sessionStorage.removeItem(PKCE_KEY);
  window.history.replaceState({}, document.title, window.location.pathname);
  return session;
}

export async function refreshSession(): Promise<BrowserSession | null> {
  const current = readSession();
  if (!current?.refreshToken) return null;
  try {
    return await exchangeToken(
      new URLSearchParams({
        grant_type: "refresh_token",
        client_id: authConfig.clientId,
        refresh_token: current.refreshToken,
      }),
    );
  } catch {
    clearSession();
    return null;
  }
}

export async function getBearerToken(): Promise<string | null> {
  if (authConfig.mode !== "cognito") return null;
  let current = readSession();
  if (!current) return null;
  if (current.expiresAt <= Date.now() + 30_000) current = await refreshSession();
  // The ID token carries verified profile and custom organization claims. The
  // backend validates its signature, issuer, app-client audience, and expiry.
  return current?.idToken ?? null;
}

export function logout(): void {
  clearSession();
  if (authConfig.mode !== "cognito" || !authConfig.domain || !authConfig.clientId) {
    window.location.assign(authConfig.logoutUri);
    return;
  }
  const query = new URLSearchParams({
    client_id: authConfig.clientId,
    logout_uri: authConfig.logoutUri,
  });
  window.location.assign(`${authConfig.domain}/logout?${query}`);
}
