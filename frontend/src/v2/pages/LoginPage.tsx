import { useRef, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthProvider";
import { authConfig } from "../auth/authSession";
import { BRAND } from "../brand";
import { BrandMark } from "../components/BrandMark";
import { Button } from "../components/Button";

type SignInMethod = "email" | "phone";
type Challenge = { left: number; right: number; answer: number };

const COOLDOWN_KEY = "autism-teaching-copilot.sign-in-cooldown";

function createChallenge(): Challenge {
  const values = crypto.getRandomValues(new Uint8Array(2));
  const left = 2 + (values[0] % 7);
  const right = 1 + (values[1] % 7);
  return { left, right, answer: left + right };
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function isValidPhone(value: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(value);
}

export function LoginPage() {
  const { status, error, signIn } = useAuth();
  const [method, setMethod] = useState<SignInMethod>("email");
  const [identifier, setIdentifier] = useState("");
  const [humanAnswer, setHumanAnswer] = useState("");
  const [website, setWebsite] = useState("");
  const [challenge, setChallenge] = useState<Challenge>(createChallenge);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const startedAt = useRef(Date.now());
  const expired = status === "expired";

  function selectMethod(next: SignInMethod) {
    setMethod(next);
    setIdentifier("");
    setHumanAnswer("");
    setFormError("");
    setChallenge(createChallenge());
    startedAt.current = Date.now();
  }

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
    const normalized = identifier.trim();
    if (method === "email" && !isValidEmail(normalized)) {
      setFormError("Enter a valid email address.");
      return;
    }
    if (method === "phone" && !authConfig.phoneSignInEnabled) {
      setFormError("Phone verification is not enabled yet. Use email sign-in for now.");
      return;
    }
    if (method === "phone" && !isValidPhone(normalized)) {
      setFormError("Enter a phone number with country code, for example +12025550123.");
      return;
    }
    if (Number(humanAnswer) !== challenge.answer) {
      sessionStorage.setItem(COOLDOWN_KEY, String(now + 3_000));
      setHumanAnswer("");
      setChallenge(createChallenge());
      setFormError("The security answer was not correct. Try the new question.");
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
    <main className="v2-login-page">
      <section className="v2-login-card" aria-labelledby="login-title">
        <BrandMark className="v2-login-logo" />
        <p className="v2-eyebrow">{BRAND.productName}</p>
        <p className="v2-login-descriptor">{BRAND.descriptor}</p>
        <h1 id="login-title">{expired ? "Your session expired" : "Teacher sign in"}</h1>
        <p className="v2-login-intro">
          {expired
            ? "Sign in again to continue. Your saved learners and lesson work remain in the workspace."
            : "Verify your teacher account to access learner records and lesson kits."}
        </p>

        <form className="v2-login-form" onSubmit={(event) => void submit(event)} noValidate>
          <div className="v2-sign-in-methods" role="group" aria-label="Choose a verification method">
            <button type="button" className={method === "email" ? "is-active" : ""} aria-pressed={method === "email"} onClick={() => selectMethod("email")}>
              <span aria-hidden="true">@</span>Email
            </button>
            <button type="button" className={method === "phone" ? "is-active" : ""} aria-pressed={method === "phone"} onClick={() => selectMethod("phone")}>
              <span aria-hidden="true">✆</span>Phone
              {!authConfig.phoneSignInEnabled && <small>Setup required</small>}
            </button>
          </div>

          <label className="v2-login-field" htmlFor="teacher-identifier">
            <span>{method === "email" ? "Teacher email" : "Mobile phone"}</span>
            <input
              id="teacher-identifier"
              type={method === "email" ? "email" : "tel"}
              inputMode={method === "email" ? "email" : "tel"}
              autoComplete={method === "email" ? "email" : "tel"}
              placeholder={method === "email" ? "teacher@example.com" : "+1 202 555 0123"}
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              disabled={submitting}
              required
            />
          </label>

          <label className="v2-bot-trap" aria-hidden="true">
            Leave this field empty
            <input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
          </label>

          <fieldset className="v2-human-check">
            <legend>Quick security check</legend>
            <label htmlFor="human-answer">
              <span aria-hidden="true">✓</span>
              <strong>What is {challenge.left} + {challenge.right}?</strong>
              <input
                id="human-answer"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                aria-label={`What is ${challenge.left} plus ${challenge.right}?`}
                value={humanAnswer}
                onChange={(event) => setHumanAnswer(event.target.value.replace(/\D/g, "").slice(0, 2))}
                disabled={submitting}
                required
              />
            </label>
          </fieldset>

          {(error || formError) && <div className="v2-auth-error" role="alert">{formError || error}</div>}
          <Button type="submit" disabled={submitting || !identifier || !humanAnswer}>
            {submitting ? "Opening secure sign in…" : expired ? "Verify and sign in again" : `Continue with ${method}`}
          </Button>
        </form>

        <div className="v2-login-security-note">
          <span aria-hidden="true">🔒</span>
          <small>Verification and sign-in are handled by Amazon Cognito using authorization code flow with PKCE. We never store your password in this website.</small>
        </div>
      </section>
    </main>
  );
}
