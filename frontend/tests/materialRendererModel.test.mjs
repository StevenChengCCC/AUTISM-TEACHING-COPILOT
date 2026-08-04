import assert from "node:assert/strict";
import test from "node:test";
import { buildMaterialRenderModel } from "../src/v2/materialRendererModel.ts";

function material(overrides={}) {
  return {
    id:"material-1",packageId:"package-1",type:"first_then_board",title:"First–Then",
    status:"teacher_review_needed",content:{firstTask:"stale task"},
    printLayout:{pageSize:"Letter",orientation:"landscape",color:"blue"},
    materialSchemaVersion:1,
    materialSpec:{revision:2,content:{firstTask:"Complete 3 items",thenOutcome:"Map break"}},
    visualAssetPlan:{materialRevision:2,visualItems:[
      {required:true,altText:"Table-work items",visibleLabel:"FIRST"},
      {required:true,altText:"Transit-route map",visibleLabel:"THEN"},
    ]},
    ...overrides,
  };
}

test("typed MaterialSpec content overrides stale compatibility projection",()=>{
  const model=buildMaterialRenderModel(material());
  assert.equal(model.rendererKind,"first_then");
  assert.equal(model.content.firstTask,"Complete 3 items");
  assert.equal(model.requiredVisualCount,2);
  assert.deepEqual(model.visualLabels,["Table-work items","Transit-route map"]);
});

test("stale visual plan is rejected by the component render model",()=>{
  const value=material();
  value.visualAssetPlan.materialRevision=1;
  assert.equal(buildMaterialRenderModel(value).currentRevision,false);
});
