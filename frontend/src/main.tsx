import React from "react";
import { createRoot } from "react-dom/client";
import { LessonKitStudioApp } from "./v2/LessonKitStudioApp";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LessonKitStudioApp />
  </React.StrictMode>,
);
