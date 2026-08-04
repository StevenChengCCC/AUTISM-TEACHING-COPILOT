import type {
  PrintPreset,
  PrintTextProfile,
  PrintableLessonKitArtifact,
} from "./types";

export const printPresetOrder: PrintPreset[] = [
  "complete_kit",
  "teacher_desk",
  "classroom_materials",
  "data_and_closeout",
];

export const printPresetLabels: Record<PrintPreset, string> = {
  complete_kit: "Complete Kit",
  teacher_desk: "Teacher Desk Copy",
  classroom_materials: "Classroom Materials",
  data_and_closeout: "Data & Closeout",
};

const selectionKey = (packageId: string) => `atc:print-preset:${packageId}`;
const pageSizeKey = (packageId: string) => `atc:print-page-size:${packageId}`;
const textProfileKey = (packageId: string) => `atc:print-text-profile:${packageId}`;
const artifactKey = (packageId: string) => `atc:print-artifact:${packageId}`;

export function readSelectedPrintPreset(packageId: string): PrintPreset {
  try {
    const value = window.localStorage.getItem(selectionKey(packageId));
    return printPresetOrder.includes(value as PrintPreset)
      ? (value as PrintPreset)
      : "complete_kit";
  } catch {
    return "complete_kit";
  }
}

export function rememberSelectedPrintPreset(
  packageId: string,
  preset: PrintPreset,
): void {
  try {
    window.localStorage.setItem(selectionKey(packageId), preset);
  } catch {
    // Printing remains available when browser storage is unavailable.
  }
}

export function readSelectedPageSize(packageId: string): "Letter" | "A4" {
  try {
    return window.localStorage.getItem(pageSizeKey(packageId)) === "A4"
      ? "A4"
      : "Letter";
  } catch {
    return "Letter";
  }
}

export function rememberSelectedPageSize(
  packageId: string,
  pageSize: "Letter" | "A4",
): void {
  try {
    window.localStorage.setItem(pageSizeKey(packageId), pageSize);
  } catch {
    // Printing remains available when browser storage is unavailable.
  }
}

export function readSelectedTextProfile(packageId: string): PrintTextProfile {
  try {
    return window.localStorage.getItem(textProfileKey(packageId)) === "large"
      ? "large"
      : "standard";
  } catch {
    return "standard";
  }
}

export function rememberSelectedTextProfile(
  packageId: string,
  textProfile: PrintTextProfile,
): void {
  try {
    window.localStorage.setItem(textProfileKey(packageId), textProfile);
  } catch {
    // Printing remains available when browser storage is unavailable.
  }
}

export function rememberPrintableArtifact(
  artifact: PrintableLessonKitArtifact,
): void {
  try {
    window.localStorage.setItem(artifactKey(artifact.packageId), JSON.stringify(artifact));
  } catch {
    // Optional session lineage can be omitted when browser storage is unavailable.
  }
}

export function readPrintableArtifact(
  packageId: string,
): PrintableLessonKitArtifact | null {
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(artifactKey(packageId)) ?? "null",
    ) as PrintableLessonKitArtifact | null;
    return parsed?.packageId === packageId ? parsed : null;
  } catch {
    return null;
  }
}
