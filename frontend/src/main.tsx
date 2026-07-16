import React from "react";
import { createRoot } from "react-dom/client";
import { LessonKitStudioApp } from "./v2/LessonKitStudioApp";
import { AuthProvider, useAuth } from "./v2/auth/AuthProvider";
import { LoginPage } from "./v2/pages/LoginPage";

function AuthenticatedApplication() {
  const { status } = useAuth();
  if (status === "loading") {
    return <main className="v2-auth-loading" aria-live="polite"><span className="v2-spinner" />Preparing your workspace…</main>;
  }
  if (status !== "authenticated") return <LoginPage />;
  return <LessonKitStudioApp />;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider><AuthenticatedApplication /></AuthProvider>
  </React.StrictMode>,
);
