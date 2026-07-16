const deploymentBuild = Boolean(process.env.AWS_BRANCH || process.env.AWS_APP_ID);
if (!deploymentBuild) {
  console.log("Local build: deployment environment validation skipped.");
  process.exit(0);
}

const required = [
  "VITE_API_BASE",
  "VITE_COGNITO_REGION",
  "VITE_COGNITO_USER_POOL_ID",
  "VITE_COGNITO_APP_CLIENT_ID",
  "VITE_COGNITO_DOMAIN",
  "VITE_COGNITO_REDIRECT_URI",
  "VITE_COGNITO_LOGOUT_URI",
];
const missing = required.filter((name) => !process.env[name]);
const errors = [];
if (process.env.VITE_AUTH_MODE !== "cognito") errors.push("VITE_AUTH_MODE must be cognito.");
if (missing.length) errors.push(`Missing public deployment variables: ${missing.join(", ")}.`);
for (const name of ["VITE_API_BASE", "VITE_COGNITO_DOMAIN", "VITE_COGNITO_REDIRECT_URI", "VITE_COGNITO_LOGOUT_URI"]) {
  const value = process.env[name];
  if (value && !value.startsWith("https://")) errors.push(`${name} must use HTTPS.`);
}
const forbidden = Object.keys(process.env).filter((name) =>
  /(?:OPENAI_API_KEY|DATABASE_URL|RDS_PASSWORD|AWS_SECRET_ACCESS_KEY)/.test(name),
);
if (forbidden.length) errors.push(`Backend-only secrets must not be configured in Amplify: ${forbidden.join(", ")}.`);

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("Amplify public environment configuration is ready.");

