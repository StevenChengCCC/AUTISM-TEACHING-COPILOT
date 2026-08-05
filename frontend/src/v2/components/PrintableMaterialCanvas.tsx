import { resolveBackendAssetUrl } from "../api/backendClient";
import type { GeneratedMaterial } from "../types";
import type { CSSProperties } from "react";
import { buildMaterialRenderModel } from "../materialRendererModel";

function asStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

type VisualItem = {
  id: string;
  label: string;
  role?: string;
  semanticKey?: string;
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
      role: typeof candidate.role === "string" ? candidate.role : undefined,
      semanticKey: typeof candidate.semanticKey === "string" ? candidate.semanticKey : undefined,
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

function displayField(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
  const renderModel = buildMaterialRenderModel(material);
  const content = renderModel.content;
  const plannedVisuals = visualItems(content.visualItems);
  const legacyImageUrl = resolveBackendAssetUrl(content.imageUrl)
    ?? (typeof content.imageBase64 === "string" ? `data:image/png;base64,${content.imageBase64}` : null);
  const imageStatus = String(content.imageGenerationStatus ?? "");
  const heading = title || material.title;
  const direction = instruction || String(content.instruction ?? "");
  if (!renderModel.currentRevision) {
    return <div className="v2-printable-canvas v2-printable-canvas--invalid" role="alert">
      <h2>{heading}</h2><p>This visual plan belongs to an older material revision. Revalidate before printing.</p>
    </div>;
  }

  if (material.type === "blue_line_activity") {
    const stations = plannedVisuals.filter((item) => item.semanticKey?.startsWith("station:"));
    const setup = asStrings(content.teacherSetup);
    const answerKey = asStrings(content.answerKeyOrExpectedSequence);
    return <div className="v2-printable-canvas v2-printable-canvas--route">
      <header><small>ROUTE-BUILDING ACTIVITY</small><h2>{heading}</h2><p>{String(content.learnerAction ?? direction)}</p></header>
      <div className="v2-route-board" aria-label={`Route with ${stations.length} station positions`}>
        <svg viewBox="0 0 760 210" role="img" aria-label="Simple blue route from start to finish"><path d="M70 150 C190 20 300 190 405 80 S610 35 690 120"/><circle cx="70" cy="150" r="22"/><rect x="670" y="98" width="42" height="42" rx="4"/></svg>
        <b className="v2-route-start">START</b><b className="v2-route-finish">FINISH</b>
        <div className="v2-route-stations">{stations.map((station, index) => {
          const source = itemImage(station);
          return <article key={station.id}><span>{index + 1}</span>{source && <img src={source} alt={station.imageAltText ?? station.label}/>}<strong>{station.label}</strong></article>;
        })}</div>
      </div>
      <div className="v2-route-directions"><section><h3>Teacher setup</h3><ol>{setup.map((step)=><li key={step}>{step}</li>)}</ol></section><section><h3>Station sequence / answer key</h3><ol>{answerKey.map((label)=><li key={label}>{label}</li>)}</ol></section></div>
      <p><b>Complete when:</b> {String(content.completionCriterion ?? "")}</p>
      <p><b>Generalize:</b> {String(content.generalizationExtension ?? "")}</p>
    </div>;
  }

  if (material.type === "visual_timer") {
    const duration = Number(content.durationMinutes ?? content.duration ?? 1);
    return <div className="v2-printable-canvas v2-printable-canvas--timer">
      <header><h2>{heading}</h2><p>{String(content.displayFormat ?? "Visual countdown")}</p></header>
      <div className="v2-timer-face" role="img" aria-label={`${duration}-minute visual-only countdown`} style={{"--timer-fill": `${Math.max(0,Math.min(100,duration*25))}%`} as CSSProperties}><span>{duration}:00</span></div>
      <div><strong>{String(content.startLabel ?? "Start")}</strong><span aria-hidden>→</span><strong>{String(content.endLabel ?? "Finished")}</strong></div>
      <p><b>Return cue:</b> {String(content.returnToTaskCue ?? "")}</p>
      {content.audioAllowed === false && <small>No alarm or audio cue.</small>}
    </div>;
  }

  if (material.type === "scenario_cards" && Array.isArray(content.scenarios)) {
    const scenarios = content.scenarios.filter((item): item is Record<string,unknown> => Boolean(item) && typeof item === "object");
    return <div className="v2-printable-canvas v2-printable-canvas--scenarios">
      <header><h2>{heading}</h2><p>Practice the same independent request across distinct transitions.</p></header>
      <div>{scenarios.map((scenario,index)=>{
        const visual=plannedVisuals[index];const source=itemImage(visual);
        return <article key={String(scenario.id ?? index)}>{source&&<img src={source} alt={visual?.imageAltText ?? String(scenario.context)}/>}<h3>{index+1}. {String(scenario.context)}</h3><dl><dt>Situation</dt><dd>{String(scenario.triggerOrTransition)}</dd><dt>Visual cue</dt><dd>{String(scenario.visualCue)}</dd><dt>Teacher wording</dt><dd>{String(scenario.teacherWording)}</dd><dt>Independent opportunity</dt><dd>{String(scenario.learnerOpportunity)}; wait {String(scenario.waitTimeSeconds)} seconds.</dd><dt>Prompt sequence</dt><dd>{asStrings(scenario.promptSequence).join(" → ")}</dd><dt>Accepted response</dt><dd>{asStrings(scenario.acceptedModalities).join(" or ")}: {String(scenario.expectedResponse)}</dd><dt>Outcome</dt><dd>{String(scenario.breakOutcome)}</dd><dt>Return</dt><dd>{String(scenario.returnSupport)}</dd></dl>{Boolean(scenario.generalizationLabel)&&<strong className="v2-scenario-generalization">{String(scenario.generalizationLabel)}</strong>}</article>;
      })}</div>
    </div>;
  }

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
    || material.type === "number_cards"
    || material.type === "visual_card"
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
        const visual = plannedVisuals[index] ?? plannedVisuals[0];
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
      <p>Accepted: {asStrings(content.acceptedCommunicationModes).join(" or ")}</p>
      <p><b>Teacher action:</b> {String(content.teacherResponseAfterUse ?? direction)}</p>
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
    return <div className={`v2-printable-canvas v2-printable-canvas--choice ${material.type === "first_then_board" ? "v2-printable-canvas--first-then" : ""}`}>
      <h2>{heading}</h2><div>{options.map((label, index) => {
        const visual = plannedVisuals[index];
        const imageUrl = itemImage(visual);
        return <article key={`${label}-${index}`}>{imageUrl
          ? <img src={imageUrl} alt={visual?.imageAltText ?? label} />
          : <span className="v2-visual-placeholder" aria-label="Visual is being prepared" />}<strong>{label}</strong></article>;
      })}</div>{material.type === "first_then_board" && <footer><p><b>Complete when:</b> {String(content.completionCriterion ?? "")}</p><p><b>After THEN:</b> {String(content.returnOrTransitionInstruction ?? "")}</p></footer>}
    </div>;
  }

  if (material.type === "data_sheet") {
    const columns = asStrings(content.exactColumns).length ? asStrings(content.exactColumns) : asStrings(content.columns).length ? asStrings(content.columns) : ["Opportunity", "Response", "Prompt", "Notes"];
    return <div className="v2-printable-canvas v2-printable-canvas--data">
      <h2>{heading}</h2><p>{String(content.operationalizedTargetBehavior ?? direction)}</p><div className="v2-data-table-scroll"><table><thead><tr>{columns.map((column) => <th key={column}>{displayField(column)}</th>)}</tr></thead><tbody>{Array.from({ length: 6 }, (_, row) => <tr key={row}>{columns.map((column) => <td key={column}>&nbsp;</td>)}</tr>)}</tbody></table></div><section><h3>Prompt and independence definitions</h3><ul>{asStrings(content.promptLevelDefinitions).map((definition)=><li key={definition}>{definition}</li>)}</ul><p><b>Independent:</b> {String(content.independenceRule ?? "")}</p></section>
    </div>;
  }

  if (material.type === "summary_template" || material.type === "session_summary") {
    const prompts = asStrings(content.reportingFields).length ? asStrings(content.reportingFields) : asStrings(content.prompts).length ? asStrings(content.prompts) : ["What worked well?", "What support was needed?", "What is the next small step?"];
    return <div className="v2-printable-canvas v2-printable-canvas--summary">
      <h2>{heading}</h2><p>{String(content.goal ?? direction)}</p>{prompts.map((prompt) => <label key={prompt}>{prompt}<span /></label>)}
    </div>;
  }

  const count = tokenCount ?? Number(content.tokens ?? content.tokenCount ?? 5);
  const tokenVisual = plannedVisuals.find((item) => item.id.includes("token-master")) ?? plannedVisuals[0];
  const rewardVisual = plannedVisuals.find((item) => item.id.endsWith("-reward"));
  const tokenImage = itemImage(tokenVisual) ?? legacyImageUrl;
  const rewardImage = itemImage(rewardVisual) ?? legacyImageUrl;
  return <div className="v2-printable-canvas v2-printable-canvas--tokens">
    <header><small>REINFORCEMENT BOARD</small><h2>{heading}</h2><p>{direction || `Earn each ${String(content.tokenSymbolOrTheme ?? "token")}, then use the named reward.`}</p></header>
    <div className="v2-token-board-body">
      <section className="v2-token-stars" aria-label={`${count} token spaces`}>
        {Array.from({ length: Math.min(Math.max(count, 2), 10) }, (_, index) =>
          <span key={index}>{tokenImage ? <img src={tokenImage} alt="" aria-hidden /> : <b>★</b>}<small>{index + 1}</small></span>)}
      </section>
      <aside>
        <small>WORKING FOR</small>
        {rewardImage
          ? <img src={rewardImage} alt={rewardVisual?.imageAltText ?? String(content.imageAltText ?? heading)} />
          : imageStatus === "pending" || imageStatus === "processing"
            ? <div className="v2-image-generation-state" role="status">Artwork is generating…</div>
            : <span className="v2-token-reward-placeholder">★</span>}
        <strong>{reward || String(content.reward ?? content.rewardLabel ?? "My choice")}</strong>
        <p>{String(content.picturedRewardDescription ?? "")}</p>
      </aside>
    </div>
    <p><b>Specific praise:</b> {String(content.specificPraise ?? "")}</p>
    {artwork && <small>{artwork}</small>}
  </div>;
}
