import { useEffect, useState } from "react";
import { API_BASE } from "../api/backendClient";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import type {
  AIImageGenerationResult,
  AILessonQuestionsTestResult,
  AIProviderStatus,
} from "../types";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The backend AI check failed.";
}

function imageSource(result: AIImageGenerationResult | null): string | null {
  if (!result) return null;
  if (result.imageBase64) return `data:image/png;base64,${result.imageBase64}`;
  if (!result.imageUrl) return null;
  if (/^https?:\/\//.test(result.imageUrl)) return result.imageUrl;
  const backendOrigin = new URL(API_BASE, window.location.origin).origin;
  return `${backendOrigin}${result.imageUrl}`;
}

export function DeveloperAISettingsPage() {
  const [status, setStatus] = useState<AIProviderStatus | null>(null);
  const [questions, setQuestions] = useState<AILessonQuestionsTestResult | null>(null);
  const [image, setImage] = useState<AIImageGenerationResult | null>(null);
  const [busy, setBusy] = useState<"status" | "questions" | "image" | null>("status");
  const [error, setError] = useState("");

  useEffect(() => {
    void lessonKitApi.getAIStatus()
      .then(setStatus)
      .catch((reason: unknown) => setError(errorMessage(reason)))
      .finally(() => setBusy(null));
  }, []);

  async function testQuestions() {
    setBusy("questions"); setError(""); setQuestions(null);
    try {
      setQuestions(await lessonKitApi.testAILessonQuestions("I want to teach asking for help."));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  async function testImage() {
    setBusy("image"); setError(""); setImage(null);
    try {
      setImage(await lessonKitApi.testAIImageGeneration({
        learnerId: "a102",
        materialType: "visual_card",
        prompt: "A simple classroom visual card showing a toy car stuck and a child asking for help.",
        style: "clean printable educational illustration",
        size: "1024x1024",
      }));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  const preview = imageSource(image);
  return <>
    <div className="v2-page-heading">
      <h1>AI Provider Status</h1>
      <p>Development checks for the backend provider boundary.</p>
    </div>
    <div className="v2-dev-warning">API keys are backend-only. Do not enter keys in the frontend.</div>
    {error&&<div className="v2-dev-error" role="alert">{error}</div>}
    <div className="v2-dev-grid">
      <Card className="v2-dev-status">
        <h2>Backend configuration</h2>
        {busy==="status"?<p>Loading provider status…</p>:status?<dl>
          <div><dt>Provider</dt><dd>{status.provider}</dd></div>
          <div><dt>Text model</dt><dd>{status.textModel}</dd></div>
          <div><dt>Image model</dt><dd>{status.imageModel}</dd></div>
          <div><dt>API key configured</dt><dd>{status.hasApiKey?"Yes":"No"}</dd></div>
        </dl>:<p>Status unavailable.</p>}
        <div className="v2-dev-actions">
          <Button onClick={()=>void testQuestions()} disabled={busy!==null}>{busy==="questions"?"Testing…":"Test Lesson Questions"}</Button>
          <Button variant="secondary" onClick={()=>void testImage()} disabled={busy!==null}>{busy==="image"?"Generating…":"Test Image Generation"}</Button>
        </div>
      </Card>
      <Card className="v2-dev-result">
        <h2>Test output</h2>
        {!questions&&!image&&<p>Run a backend test to inspect its safe response.</p>}
        {questions&&<pre>{JSON.stringify(questions,null,2)}</pre>}
        {image&&<>
          {preview?<img src={preview} alt="Generated educational material test"/>:<div className="v2-dev-image-placeholder">Mock mode returned no image.</div>}
          <pre>{JSON.stringify({...image,imageBase64:image.imageBase64?"[base64 image omitted]":null},null,2)}</pre>
        </>}
      </Card>
    </div>
  </>;
}
