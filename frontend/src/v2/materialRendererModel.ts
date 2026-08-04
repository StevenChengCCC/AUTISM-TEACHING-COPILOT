import type { GeneratedMaterial } from "./types.ts";

export interface MaterialRenderModel {
  content: Record<string, unknown>;
  currentRevision: boolean;
  requiredVisualCount: number;
  visualLabels: string[];
  rendererKind: "route"|"communication"|"first_then"|"token"|"timer"|"scenarios"|"data"|"summary"|"legacy";
}

export function buildMaterialRenderModel(material: GeneratedMaterial): MaterialRenderModel {
  const typed = (material.materialSpec?.content ?? {}) as Record<string,unknown>;
  const content = {...(material.specification ?? {}),...material.content,...typed};
  const plan = material.visualAssetPlan;
  const currentRevision = !material.materialSpec || !plan || plan.materialRevision === material.materialSpec.revision;
  const kinds:Record<string,MaterialRenderModel["rendererKind"]> = {
    blue_line_activity:"route",help_card:"communication",break_card:"communication",
    first_then_board:"first_then",token_board:"token",visual_timer:"timer",
    scenario_cards:"scenarios",data_sheet:"data",summary_template:"summary",session_summary:"summary",
  };
  return {
    content,
    currentRevision,
    requiredVisualCount:plan?.visualItems.filter((item)=>item.required).length ?? 0,
    visualLabels:plan?.visualItems.map((item)=>item.altText || item.visibleLabel).filter(Boolean) ?? [],
    rendererKind:kinds[material.type] ?? "legacy",
  };
}
