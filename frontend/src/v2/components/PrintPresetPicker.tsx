import type { PrintPreset, PrintPresetCatalog } from "../types";
import { printPresetLabels } from "../printPresetModel";

export function PrintPresetPicker({
  catalog,
  selected,
  onSelect,
  compact = false,
}: {
  catalog: PrintPresetCatalog | null;
  selected: PrintPreset;
  onSelect: (preset: PrintPreset) => void;
  compact?: boolean;
}) {
  const preview = catalog?.presets.find((item) => item.printPreset === selected);
  return <div className={`v2-print-presets ${compact ? "is-compact" : ""}`} aria-label="Print preset">
    <div className="v2-print-preset-tabs" role="radiogroup" aria-label="Choose pages to print">
      {(catalog?.presets ?? []).map((item) => <button
        type="button"
        role="radio"
        aria-checked={item.printPreset === selected}
        className={item.printPreset === selected ? "is-selected" : ""}
        disabled={!item.available}
        key={item.printPreset}
        onClick={() => onSelect(item.printPreset)}
      >
        <strong>{item.displayName}</strong>
        <small>{item.estimatedPageCount} pages estimated</small>
      </button>)}
    </div>
    {!catalog && <p role="status">Loading print choices…</p>}
    {!compact && preview && <div className="v2-print-preset-preview">
      <p>{preview.description}</p>
      {!preview.available && <p role="alert">{preview.unavailableReason}</p>}
      <strong>Included</strong>
      <ul>{preview.includedEntries.map((entry) => <li key={`${entry.entryType}:${entry.entryId}`}>
        <span>{entry.title}{entry.revision ? ` · revision ${entry.revision}` : ""}</span>
        <small>{entry.reason}</small>
      </li>)}</ul>
      {preview.excludedEntries.length > 0 && <details>
        <summary>{preview.excludedEntries.length} excluded sections or materials</summary>
        <ul>{preview.excludedEntries.map((entry) => <li key={`${entry.entryType}:${entry.entryId}`}>
          <span>{entry.title}</span><small>{entry.reason}</small>
        </li>)}</ul>
      </details>}
    </div>}
    {!compact && selected !== "complete_kit" && <button type="button" className="v2-print-return-complete" onClick={() => onSelect("complete_kit")}>
      Return to {printPresetLabels.complete_kit}
    </button>}
  </div>;
}
