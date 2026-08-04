import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  printPresetLabels,
  printPresetOrder,
  readPrintableArtifact,
  readSelectedPageSize,
  readSelectedPrintPreset,
  readSelectedTextProfile,
  rememberPrintableArtifact,
  rememberSelectedPageSize,
  rememberSelectedPrintPreset,
  rememberSelectedTextProfile,
} from "../src/v2/printPresetModel.ts";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  };
}

test("named presets are fixed, ordered, and default to Complete Kit", () => {
  globalThis.window = { localStorage: memoryStorage() };
  assert.deepEqual(printPresetOrder, [
    "complete_kit", "teacher_desk", "classroom_materials", "data_and_closeout",
  ]);
  assert.equal(readSelectedPrintPreset("package-1"), "complete_kit");
  assert.equal(printPresetLabels.teacher_desk, "Teacher Desk Copy");
});

test("selection and current artifact lineage survive reload storage", () => {
  globalThis.window = { localStorage: memoryStorage() };
  rememberSelectedPrintPreset("package-1", "teacher_desk");
  rememberSelectedPageSize("package-1", "A4");
  rememberSelectedTextProfile("package-1", "large");
  assert.equal(readSelectedPrintPreset("package-1"), "teacher_desk");
  assert.equal(readSelectedPageSize("package-1"), "A4");
  assert.equal(readSelectedTextProfile("package-1"), "large");
  const artifact = {
    artifactId: "print-kit-1", packageId: "package-1", packageRevision: 4,
    manifestVersion: 2, printPreset: "teacher_desk", pageSize: "LETTER",
    textProfile: "large",
    materialRevisions: {}, status: "ready", filename: "desk.pdf",
    contentType: "application/pdf", sizeBytes: 10, pageCount: 2,
    sha256: "a".repeat(64), downloadUrl: "https://example.test/desk.pdf",
    expiresAt: "2026-08-05T00:00:00Z", reused: false,
  };
  rememberPrintableArtifact(artifact);
  assert.deepEqual(readPrintableArtifact("package-1"), artifact);
  assert.equal(readPrintableArtifact("package-2"), null);
});

test("both existing print screens use server preset inventory and fixed payloads", () => {
  const ready = readFileSync(new URL("../src/v2/pages/LessonPackageReadyPage.tsx", import.meta.url), "utf8");
  const review = readFileSync(new URL("../src/v2/pages/ReviewPrintableContentPage.tsx", import.meta.url), "utf8");
  for (const source of [ready, review]) {
    assert.match(source, /getPrintPresetCatalog/);
    assert.match(source, /PrintPresetPicker/);
    assert.match(source, /materialIds:\s*\[\]/);
    assert.match(source, /textProfile/);
    assert.match(source, /Large Print/);
    assert.match(source, /rememberSelectedTextProfile/);
  }
  assert.match(ready, /rememberPrintableArtifact/);
  assert.match(review, /rememberPrintableArtifact/);
});

test("session start forwards only matching stored artifact lineage", () => {
  const sessions = readFileSync(new URL("../src/v2/pages/SessionsPage.tsx", import.meta.url), "utf8");
  assert.match(sessions, /artifact\?\.packageRevision===selected\.lessonPackageRevision/);
  assert.match(sessions, /pdfExportId:currentArtifact\?\.artifactId/);
  assert.match(sessions, /printPreset:currentArtifact\?\.printPreset/);
});
