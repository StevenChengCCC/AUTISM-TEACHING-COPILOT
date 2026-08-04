import type {
  PdfDownloadState,
  PrintableLessonKitArtifact,
} from "./types";

export const initialPdfDownloadState: PdfDownloadState = {
  phase: "idle",
  message: "",
  retryable: false,
};

export class PdfDownloadFlowError extends Error {
  code: string;
  retryable: boolean;

  constructor(
    message: string,
    code: string,
    retryable: boolean,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
  }
}

export function canStartPdfDownload(state: PdfDownloadState): boolean {
  return !["preparing", "download_starting"].includes(state.phase);
}

export function isPdfArtifactExpired(
  artifact: PrintableLessonKitArtifact,
  now = Date.now(),
): boolean {
  const expiresAt = Date.parse(artifact.expiresAt);
  return !Number.isFinite(expiresAt) || expiresAt <= now + 10_000;
}

export function validatePdfArtifactMetadata(
  artifact: PrintableLessonKitArtifact,
): void {
  if (artifact.status !== "ready") {
    throw new PdfDownloadFlowError(
      "The PDF is not ready yet. Try preparing it again.",
      "pdf_not_ready",
      true,
    );
  }
  if (
    artifact.contentType !== "application/pdf" ||
    artifact.sizeBytes <= 0 ||
    artifact.pageCount <= 0
  ) {
    throw new PdfDownloadFlowError(
      "The prepared PDF is empty or invalid. Prepare it again.",
      "invalid_pdf_artifact",
      true,
    );
  }
  if (!artifact.filename.toLowerCase().endsWith(".pdf")) {
    throw new PdfDownloadFlowError(
      "The server returned an invalid PDF filename.",
      "invalid_pdf_filename",
      false,
    );
  }
  let parsed: URL;
  try {
    const base =
      typeof window === "undefined" ? "http://localhost" : window.location.origin;
    parsed = new URL(artifact.downloadUrl, base);
  } catch {
    throw new PdfDownloadFlowError(
      "The PDF download address is invalid. Prepare it again.",
      "invalid_download_url",
      true,
    );
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new PdfDownloadFlowError(
      "The PDF download address is not supported.",
      "invalid_download_url",
      false,
    );
  }
}

export function startSignedPdfDownload(
  artifact: PrintableLessonKitArtifact,
  documentObject: Document = document,
): void {
  validatePdfArtifactMetadata(artifact);
  const anchor = documentObject.createElement("a");
  anchor.href = artifact.downloadUrl;
  anchor.download = artifact.filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  documentObject.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function errorDetails(reason: unknown): PdfDownloadFlowError {
  if (reason instanceof PdfDownloadFlowError) return reason;
  if (reason instanceof Error) {
    const record = reason as Error & {
      code?: unknown;
      retryable?: unknown;
    };
    return new PdfDownloadFlowError(
      reason.message || "The PDF download failed.",
      typeof record.code === "string" ? record.code : "pdf_download_failed",
      typeof record.retryable === "boolean" ? record.retryable : true,
    );
  }
  return new PdfDownloadFlowError(
    "The PDF download failed. Check your connection and retry.",
    "pdf_download_failed",
    true,
  );
}

export async function executePdfArtifactDownload({
  prepareArtifact,
  startDownload = startSignedPdfDownload,
  onState,
  now = () => Date.now(),
}: {
  prepareArtifact: () => Promise<PrintableLessonKitArtifact>;
  startDownload?: (artifact: PrintableLessonKitArtifact) => void;
  onState: (state: PdfDownloadState) => void;
  now?: () => number;
}): Promise<PrintableLessonKitArtifact> {
  onState({
    phase: "preparing",
    message: "Preparing PDF…",
    retryable: false,
  });
  try {
    let artifact = await prepareArtifact();
    validatePdfArtifactMetadata(artifact);
    onState({
      phase: "ready",
      message: `PDF ready · ${artifact.pageCount} pages`,
      retryable: false,
      artifact,
    });
    if (isPdfArtifactExpired(artifact, now())) {
      onState({
        phase: "preparing",
        message: "Refreshing the expired download link…",
        retryable: false,
        artifact,
      });
      artifact = await prepareArtifact();
      validatePdfArtifactMetadata(artifact);
      if (isPdfArtifactExpired(artifact, now())) {
        throw new PdfDownloadFlowError(
          "The refreshed PDF link is already expired. Try again.",
          "expired_download_url",
          true,
        );
      }
    }
    onState({
      phase: "download_starting",
      message: "Download starting…",
      retryable: false,
      artifact,
    });
    startDownload(artifact);
    onState({
      phase: "downloaded",
      message: `Downloaded ${artifact.filename}`,
      retryable: false,
      artifact,
    });
    return artifact;
  } catch (reason) {
    const error = errorDetails(reason);
    onState({
      phase: "failed",
      message: error.message,
      errorCode: error.code,
      retryable: error.retryable,
    });
    throw error;
  }
}
