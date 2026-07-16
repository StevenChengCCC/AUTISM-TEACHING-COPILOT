import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/Button";

export function LoginPage() {
  const { status, error, signIn } = useAuth();
  const expired = status === "expired";
  return (
    <main className="v2-login-page">
      <section className="v2-login-card" aria-labelledby="login-title">
        <div className="v2-login-logo" aria-hidden="true">▰</div>
        <p className="v2-eyebrow">Lesson Kit Studio</p>
        <h1 id="login-title">{expired ? "Your session expired" : "Teacher sign in"}</h1>
        <p>
          {expired
            ? "Sign in again to continue. Your saved learners and lesson work remain in the workspace."
            : "Use your authorized teacher account to access learner records and lesson kits."}
        </p>
        {error && <div className="v2-auth-error" role="alert">{error}</div>}
        <Button onClick={() => void signIn()}>{expired ? "Sign in again" : "Continue to sign in"}</Button>
        <small>Authentication is handled by Amazon Cognito using authorization code flow with PKCE.</small>
      </section>
    </main>
  );
}

