import React from "react";
import { createRoot } from "react-dom/client";
import { AutismTeachingCopilotApp } from "./v2/LessonKitStudioApp";
import { AuthProvider, useAuth } from "./v2/auth/AuthProvider";
import { BRAND } from "./v2/brand";
import { BrandMark } from "./v2/components/BrandMark";
import { LoginPage } from "./v2/pages/LoginPage";

function AuthenticatedApplication() {
  const { status } = useAuth();
  if (status === "loading") {
    return <main className="v2-auth-loading" aria-live="polite"><BrandMark decorative={false} /><span className="v2-spinner" /><span>Preparing {BRAND.productName}…</span></main>;
  }
  if (status !== "authenticated") return <LoginPage />;
  return <AutismTeachingCopilotApp />;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider><AuthenticatedApplication /></AuthProvider>
  </React.StrictMode>,
);
