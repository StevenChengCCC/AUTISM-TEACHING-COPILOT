import { resolveBackendAssetUrl } from "../api/backendClient";
import type { GeneratedMaterial } from "../types";

function asStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

type VisualItem = {
  id: string;
  label: string;
  quantity?: number;
  imageUrl?: string | null;
  imageBase64?: string | null;
  imageAltText?: string;
  generationStatus?: string;
};

function visualItems(value: unknown): VisualItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, index) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Record<string, unknown>;
    return [{
      id: String(candidate.id ?? `visual-${index}`),
      label: String(candidate.label ?? ""),
      quantity: typeof candidate.quantity === "number" ? candidate.quantity : undefined,
      imageUrl: typeof candidate.imageUrl === "string" ? candidate.imageUrl : null,
      imageBase64: typeof candidate.imageBase64 === "string" ? candidate.imageBase64 : null,
      imageAltText: typeof candidate.imageAltText === "string" ? candidate.imageAltText : undefined,
      generationStatus: typeof candidate.generationStatus === "string" ? candidate.generationStatus : undefined,
    }];
  });
}

function itemImage(item: VisualItem | undefined): string | null {
  if (!item) return null;
  return resolveBackendAssetUrl(item.imageUrl)
    ?? (item.imageBase64 ? `data:image/png;base64,${item.imageBase64}` : null);
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

function countForLabel(label: string): number | null {
  const match = label.trim().match(/^\d{1,2}$/);
  if (!match) return null;
  const value = Number(match[0]);
  return value >= 1 && value <= 10 ? value : null;
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
  const plannedVisuals = visualItems(content.visualItems);
  const legacyImageUrl = resolveBackendAssetUrl(content.imageUrl)
    ?? (typeof content.imageBase64 === "string" ? `data:image/png;base64,${content.imageBase64}` : null);
  const imageStatus = String(content.imageGenerationStatus ?? "");
  const heading = title || material.title;
  const direction = instruction || String(content.instruction ?? "");

  if (material.type === "matching_page") {
    const labels = plannedVisuals.length
      ? plannedVisuals.map((item) => item.label)
      : countingLabels(material);
    return <div className="v2-printable-canvas v2-printable-canvas--matching">
      <header><h2>{heading}</h2><p>{direction || "Match each numeral to the same quantity."}</p></header>
      <div className="v2-matching-sheet">
        {(labels.length ? labels : ["1", "2", "3", "4", "5"]).slice(0, 8).map((label, index) => {
          const visual = plannedVisuals[index] ?? plannedVisuals[0];
          const imageUrl = itemImage(visual) ?? legacyImageUrl;
          const quantity = visual?.quantity ?? countForLabel(label) ?? 1;
          return <article key={`${label}-${index}`}>
            <strong>{label}</strong>
            <span aria-hidden>↔</span>
            <div>
              {imageUrl
                ? <span className="v2-count-objects" aria-label={`${quantity} ${visual?.imageAltText ?? "countable objects"}`}>
                    {Array.from({ length: Math.min(quantity, 10) }, (_, itemIndex) => <img key={itemIndex} src={imageUrl} alt="" aria-hidden />)}
                  </span>
                : <span className="v2-visual-placeholder" aria-label="Custom visual is being prepared" />}
            </div>
          </article>;
        })}
      </div>
    </div>;
  }

  if (
    material.type === "quantity_cards"
    || material.type === "visual_card"
    || material.type === "scenario_cards"
    || material.type === "sequence_cards"
    || material.type === "social_narrative"
    || material.type === "sorting_page"
    || material.type === "visual_schedule"
    || material.type === "task_analysis_cards"
    || material.type === "emotion_scale"
  ) {
    const labels = plannedVisuals.length
      ? plannedVisuals.map((item) => item.label)
      : asStrings(content.examples).length
      ? asStrings(content.examples)
      : asStrings(content.items).length
        ? asStrings(content.items)
        : countingLabels(material).length
          ? countingLabels(material)
          : [String(content.label ?? content.phrase ?? direction ?? heading)];
    return <div className="v2-printable-canvas v2-printable-canvas--cards">
      <header><h2>{heading}</h2>{direction && <p>{direction}</p>}</header>
      {!legacyImageUrl && (imageStatus === "pending" || imageStatus === "processing") && <div className="v2-image-generation-state" role="status">Creating every visual in this material set…</div>}
      {!legacyImageUrl && imageStatus === "failed" && <div className="v2-image-generation-state v2-image-generation-state--failed" role="status">Custom visuals need to be regenerated.</div>}
      <div className="v2-card-sheet">{labels.slice(0, 8).map((label, index) => {
        const count = countForLabel(label);
        const visual = plannedVisuals.find((item) => item.label === label) ?? plannedVisuals[index] ?? plannedVisuals[0];
        const imageUrl = itemImage(visual) ?? legacyImageUrl;
        const quantity = visual?.quantity ?? count ?? 1;
        return <article key={`${label}-${index}`}>
          {imageUrl && quantity > 1
            ? <span className="v2-count-objects" aria-label={`${quantity} ${visual?.imageAltText ?? "countable objects"}`}>
                {Array.from({ length: Math.min(quantity, 10) }, (_, itemIndex) => <img key={itemIndex} src={imageUrl} alt="" aria-hidden />)}
              </span>
            : imageUrl
              ? <img src={imageUrl} alt={visual?.imageAltText ?? String(content.imageAltText ?? label)} />
              : null}
          <strong>{label}</strong>
        </article>;
      })}</div>
    </div>;
  }

  if (material.type === "help_card" || material.type === "break_card" || material.type === "teacher_cue_card") {
    const phrase = String(content.phrase ?? content.requestText ?? direction ?? heading);
    const requestImage = itemImage(plannedVisuals[0]) ?? legacyImageUrl;
    return <div className="v2-printable-canvas v2-printable-canvas--request">
      <h2>{heading}</h2>
      {requestImage && <img src={requestImage} alt={plannedVisuals[0]?.imageAltText ?? String(content.imageAltText ?? phrase)} />}
      <strong>{phrase}</strong>
      {direction && direction !== phrase && <p>{direction}</p>}
    </div>;
  }

  if (material.type === "choice_board" || material.type === "first_then_board" || material.type === "core_word_board") {
    const labels = plannedVisuals.length
      ? plannedVisuals.map((item) => item.label)
      : asStrings(content.words).length
        ? asStrings(content.words)
        : asStrings(content.options).length ? asStrings(content.options) : asStrings(content.examples);
    const options = labels.length
      ? labels.slice(0, material.type === "core_word_board" ? 8 : 4)
      : material.type === "first_then_board"
        ? [String(content.firstText ?? "First"), String(content.thenText ?? "Then")]
        : ["Choice 1", "Choice 2"];
    return <div className="v2-printable-canvas v2-printable-canvas--choice">
      <h2>{heading}</h2><div>{options.map((label, index) => {
        const visual = plannedVisuals.find((item) => item.label === label) ?? plannedVisuals[index];
        const imageUrl = itemImage(visual);
        return <article key={`${label}-${index}`}>{imageUrl
          ? <img src={imageUrl} alt={visual?.imageAltText ?? label} />
          : <span className="v2-visual-placeholder" aria-label="Visual is being prepared" />}<strong>{label}</strong></article>;
      })}</div>
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
  const tokenImage = itemImage(plannedVisuals[0]) ?? legacyImageUrl;
  return <div className="v2-printable-canvas v2-printable-canvas--tokens">
    <header><small>MY MOTIVATION BOARD</small><h2>{heading}</h2><p>{direction || "Finish each step. Add a star. Then choose your reward."}</p></header>
    <div className="v2-token-board-body">
      <section className="v2-token-stars" aria-label={`${count} token spaces`}>
        {Array.from({ length: Math.min(Math.max(count, 2), 10) }, (_, index) =>
          <span key={index}><b>★</b><small>{index + 1}</small></span>)}
      </section>
      <aside>
        <small>WORKING FOR</small>
        {tokenImage
          ? <img src={tokenImage} alt={plannedVisuals[0]?.imageAltText ?? String(content.imageAltText ?? heading)} />
          : imageStatus === "pending" || imageStatus === "processing"
            ? <div className="v2-image-generation-state" role="status">Artwork is generating…</div>
            : <span className="v2-token-reward-placeholder">★</span>}
        <strong>{reward || String(content.reward ?? content.rewardLabel ?? "My choice")}</strong>
      </aside>
    </div>
    {artwork && <small>{artwork}</small>}
  </div>;
}
