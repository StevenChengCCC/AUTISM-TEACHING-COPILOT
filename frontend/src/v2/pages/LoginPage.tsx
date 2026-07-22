import { useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthProvider";
import { BRAND } from "../brand";
import { BrandMark } from "../components/BrandMark";
import { Button } from "../components/Button";
import { Card } from "../components/Card";

const COOLDOWN_KEY = "autism-teaching-copilot.sign-in-cooldown";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export function LoginPage() {
  const { status, error, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const startedAt = useRef(Date.now());
  const expired = status === "expired";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const now = Date.now();
    const cooldownUntil = Number(sessionStorage.getItem(COOLDOWN_KEY) ?? 0);
    if (cooldownUntil > now) {
      setFormError("Please wait a moment before trying again.");
      return;
    }
    // This honeypot and timing check reduce basic scripted submissions. Cognito
    // remains the authentication trust boundary and applies its own throttling.
    if (website || now - startedAt.current < 800) {
      sessionStorage.setItem(COOLDOWN_KEY, String(now + 5_000));
      setFormError("We could not verify this sign-in attempt. Please try again.");
      return;
    }
    const normalized = email.trim();
    if (!isValidEmail(normalized)) {
      setFormError("Enter a valid email address.");
      return;
    }
    setSubmitting(true);
    try {
      await signIn(normalized);
    } catch (reason) {
      setSubmitting(false);
      setFormError(reason instanceof Error ? reason.message : "Sign-in could not be started.");
    }
  }

  return (
    <div className="autism-teaching-copilot v2-login-page">
      <header className="v2-login-header">
        <div className="v2-login-header-inner">
          <div className="v2-login-brand" aria-label={BRAND.productName}>
            <BrandMark />
            <span className="v2-brand-copy">
              <strong>{BRAND.productName}</strong>
              <small>{BRAND.descriptor}</small>
            </span>
          </div>
          <span className="v2-login-workspace-label">Teacher workspace</span>
        </div>
      </header>

      <main className="v2-login-main">
        <section className="v2-login-welcome" aria-labelledby="login-welcome-title">
          <p className="v2-login-kicker">Teacher-led lesson preparation</p>
          <h1 id="login-welcome-title">Prepare individualized lessons with clarity.</h1>
          <p>Bring learner context, guided planning, and printable materials together in one focused workspace.</p>
          <div className="v2-login-flow" aria-label="Lesson preparation workflow">
            <span><b>01</b>Review learner context</span>
            <span><b>02</b>Plan with guided support</span>
            <span><b>03</b>Approve classroom materials</span>
          </div>
        </section>

        <Card className="v2-login-card" aria-labelledby="login-title">
          <p className="v2-eyebrow">Welcome back</p>
          <h2 id="login-title">{expired ? "Your session expired" : "Teacher sign in"}</h2>
          <p className="v2-login-intro">
            {expired
              ? "Sign in again to continue your work."
              : "Use your authorized teacher email to continue."}
          </p>

          <form className="v2-login-form" onSubmit={(event) => void submit(event)} noValidate>
            <label className="v2-login-field" htmlFor="teacher-identifier">
              <span>Email address</span>
              <input
                id="teacher-identifier"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={submitting}
                required
              />
            </label>

            <label className="v2-bot-trap" aria-hidden="true">
              Leave this field empty
              <input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
            </label>

            {(error || formError) && <div className="v2-auth-error" role="alert">{formError || error}</div>}
            <Button type="submit" fullWidth disabled={submitting || !email}>
              {submitting ? "Opening sign in…" : expired ? "Sign in again" : "Continue"}
            </Button>
          </form>
        </Card>
      </main>
    </div>
  );
}
