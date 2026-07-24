import { resolveBackendAssetUrl } from "../api/backendClient";
import type { GeneratedMaterial } from "../types";

function asStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function countingLabels(material: GeneratedMaterial): string[] {
  const text = [
    material.title,
    material.content.phrase,
    material.content.instruction,
    material.content.example,
  ].filter(Boolean).join(" ");
  const match = text.match(/\b(\d{1,2})\s+(?:to|through|-)\s+(\d{1,2})\b/i);
  if (!match) return [];
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (start < 0 || end < start || end > 20 || end - start > 9) return [];
  return Array.from({ length: end - start + 1 }, (_, index) => String(start + index));
}

export function PrintableMaterialCanvas({
  material,
  title,
  instruction,
  reward,
  tokenCount,
  artwork,
}: {
  material: GeneratedMaterial;
  title?: string;
  instruction?: string;
  reward?: string;
  tokenCount?: number;
  artwork?: string;
}) {
  const content = { ...(material.specification ?? {}), ...material.content };
  const imageUrl = resolveBackendAssetUrl(content.imageUrl)
    ?? (typeof content.imageBase64 === "string" ? `data:image/png;base64,${content.imageBase64}` : null);
  const imageStatus = String(content.imageGenerationStatus ?? "");
  const heading = title || material.title;
  const direction = instruction || String(content.instruction ?? "");

  if (material.type === "visual_card" || material.type === "scenario_cards" || material.type === "sorting_page" || material.type === "matching_page") {
    const labels = asStrings(content.examples).length
      ? asStrings(content.examples)
      : asStrings(content.items).length
        ? asStrings(content.items)
        : countingLabels(material).length
          ? countingLabels(material)
          : [String(content.label ?? content.phrase ?? direction ?? heading)];
    return <div className="v2-printable-canvas v2-printable-canvas--cards">
      <header><h2>{heading}</h2>{direction && <p>{direction}</p>}</header>
      <div className="v2-card-sheet">{labels.slice(0, 8).map((label, index) => <article key={`${label}-${index}`}>
        {imageUrl && index === 0 && <img src={imageUrl} alt={String(content.imageAltText ?? label)} />}
        <strong>{label}</strong>
      </article>)}</div>
    </div>;
  }

  if (material.type === "help_card" || material.type === "break_card" || material.type === "teacher_cue_card") {
    const phrase = String(content.phrase ?? content.requestText ?? direction ?? heading);
    return <div className="v2-printable-canvas v2-printable-canvas--request">
      <h2>{heading}</h2>
      {imageUrl && <img src={imageUrl} alt={String(content.imageAltText ?? phrase)} />}
      <strong>{phrase}</strong>
      {direction && direction !== phrase && <p>{direction}</p>}
    </div>;
  }

  if (material.type === "choice_board" || material.type === "first_then_board") {
    const labels = asStrings(content.options).length ? asStrings(content.options) : asStrings(content.examples);
    const options = labels.length
      ? labels.slice(0, 4)
      : material.type === "first_then_board"
        ? [String(content.firstText ?? "First"), String(content.thenText ?? "Then")]
        : ["Choice 1", "Choice 2"];
    return <div className="v2-printable-canvas v2-printable-canvas--choice">
      <h2>{heading}</h2><div>{options.map((label) => <article key={label}><span /><strong>{label}</strong></article>)}</div>
    </div>;
  }

  if (material.type === "data_sheet") {
    const columns = asStrings(content.columns).length ? asStrings(content.columns).slice(0, 5) : ["Opportunity", "Response", "Prompt", "Notes"];
    return <div className="v2-printable-canvas v2-printable-canvas--data">
      <h2>{heading}</h2><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{Array.from({ length: 6 }, (_, row) => <tr key={row}>{columns.map((column) => <td key={column}>&nbsp;</td>)}</tr>)}</tbody></table>
    </div>;
  }

  if (material.type === "summary_template" || material.type === "session_summary") {
    const prompts = asStrings(content.prompts).length ? asStrings(content.prompts) : ["What worked well?", "What support was needed?", "What is the next small step?"];
    return <div className="v2-printable-canvas v2-printable-canvas--summary">
      <h2>{heading}</h2>{prompts.map((prompt) => <label key={prompt}>{prompt}<span /></label>)}
    </div>;
  }

  const count = tokenCount ?? Number(content.tokens ?? content.tokenCount ?? 5);
  return <div className="v2-printable-canvas v2-printable-canvas--tokens">
    <h2>{heading}</h2><p>{direction || "Earn tokens, then choose a reward."}</p>
    {imageUrl
      ? <img src={imageUrl} alt={String(content.imageAltText ?? heading)} />
      : imageStatus === "pending" || imageStatus === "processing"
        ? <div className="v2-image-generation-state" role="status">Artwork is generating…</div>
        : null}
    <div>{Array.from({ length: Math.min(Math.max(count, 2), 10) }, (_, index) => <span key={index} />)}</div>
    <strong>Reward: {reward || String(content.reward ?? content.rewardLabel ?? "Teacher-confirmed choice")}</strong>
    {artwork && <small>{artwork}</small>}
  </div>;
}
