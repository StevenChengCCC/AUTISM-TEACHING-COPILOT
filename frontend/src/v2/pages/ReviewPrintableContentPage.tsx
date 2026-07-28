import { useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerAvatar } from "../components/Avatar";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import { PrintableMaterialCanvas } from "../components/PrintableMaterialCanvas";
import type { MaterialQuickEditAction } from "../types";
import type { GeneratedMaterial,LearnerProfile,LessonPackage } from "../types";

const colors=["blue","green","purple","coral","gold"];
const fallbackDesignOptions=[
  {id:"calm-blue",label:"Calm blue",color:"blue",description:"Clear and low-distraction"},
  {id:"playful-green",label:"Playful green",color:"green",description:"Friendly and encouraging"},
  {id:"warm-gold",label:"Warm gold",color:"gold",description:"Warm classroom energy"},
];
const imageMaterialTypes=["quantity_cards","number_cards","visual_card","scenario_cards","sequence_cards","social_narrative","core_word_board","visual_schedule","task_analysis_cards","emotion_scale","sorting_page","matching_page","choice_board","first_then_board","help_card","break_card","teacher_cue_card","token_board"];
function hasCompleteVisualSet(material:GeneratedMaterial):boolean {
  if(!imageMaterialTypes.includes(material.type))return true;
  const items=material.content.visualItems;
  if(Array.isArray(items)&&items.length>0)return items.every((item)=>{
    if(!item||typeof item!=="object")return false;
    const value=item as Record<string,unknown>;
    return Boolean(value.imageUrl||value.imageBase64)&&!["pending","processing","failed"].includes(String(value.generationStatus??""));
  });
  return Boolean(material.content.imageUrl||material.content.imageBase64);
}
export function ReviewPrintableContentPage({ lessonPackage,initialSelectedId="",onBack,onFeedback }:{ lessonPackage:LessonPackage|null;initialSelectedId?:string;onBack:()=>void;onFeedback:(message:string)=>void }) {
  const [materials,setMaterials]=useState<GeneratedMaterial[]>([]);const [learner,setLearner]=useState<LearnerProfile|null>(null);const [selectedId,setSelectedId]=useState("token-board");
  const [title,setTitle]=useState("");const [instruction,setInstruction]=useState("");const [reward,setReward]=useState("Car");const [theme,setTheme]=useState("blue");const [layout,setLayout]=useState("5-token row");const [approved,setApproved]=useState(false);
  const [designId,setDesignId]=useState("calm-blue");const [pageSize,setPageSize]=useState<"Letter"|"A4">("Letter");
  const [artwork,setArtwork]=useState("Classic vehicle artwork");
  const [dirty,setDirty]=useState(false);const [imageBusy,setImageBusy]=useState(false);
  useEffect(()=>{if(!lessonPackage)return;void Promise.all([lessonKitApi.getGeneratedMaterials(lessonPackage.id),lessonKitApi.getLearnerById(lessonPackage.learnerId)]).then(([items,profile])=>{setMaterials(items);setLearner(profile);setSelectedId(items.some((item)=>item.id===initialSelectedId)?initialSelectedId:items[0]?.id??"");});},[lessonPackage?.id,initialSelectedId]);
  const selected=materials.find((item)=>item.id===selectedId)??materials[0];
  const imageStateKey=materials.map((item)=>String(item.content.imageGenerationStatus??"")).join("|");
  useEffect(()=>{if(!lessonPackage||!materials.some((item)=>["pending","processing"].includes(String(item.content.imageGenerationStatus??""))))return;let cancelled=false;const refresh=async()=>{try{const items=await lessonKitApi.getGeneratedMaterials(lessonPackage.id);if(!cancelled)setMaterials(items);}catch{/* Keep the editor usable while background artwork is retried. */}};const timer=window.setInterval(()=>void refresh(),3000);void refresh();return()=>{cancelled=true;window.clearInterval(timer);};},[lessonPackage?.id,imageStateKey]);
  useEffect(()=>{if(!selected)return;setTitle(selected.title);setInstruction(String(selected.content.instruction??""));setReward(String(selected.content.reward??"Car"));setTheme(selected.printLayout.color);setDesignId(String(selected.content.selectedDesignVariant??"calm-blue"));setPageSize(selected.printLayout.pageSize);setArtwork(String(selected.content.artwork??"Classic vehicle artwork"));setApproved(selected.status==="approved");setDirty(false);},[selected]);
  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(!dirty)return;event.preventDefault();event.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
  if(!lessonPackage)return <section className="v2-empty"><h2>No printable content yet</h2><Button onClick={onBack}>Back</Button></section>;
  const goalTitle=lessonPackage.goal.toLowerCase().includes("ask for help")?"Asking for Help":lessonPackage.goal;const tokenCount=layout.startsWith("3")?3:5;const rewardIcon=reward==="Car"?"🚙":reward==="Bubbles"?"🫧":"🎵";
  const imageStatus=String(selected?.content.imageGenerationStatus??"");
  const hasArtwork=Boolean(selected&&hasCompleteVisualSet(selected));
  const needsArtwork=Boolean(selected&&imageMaterialTypes.includes(selected.type));
  const designOptions=selected&&Array.isArray(selected.content.designVariants)
    ? selected.content.designVariants.filter((item):item is Record<string,unknown>=>Boolean(item)&&typeof item==="object").map((item,index)=>({
      id:String(item.id??fallbackDesignOptions[index]?.id??`design-${index+1}`),
      label:String(item.label??fallbackDesignOptions[index]?.label??`Design ${index+1}`),
      color:String(item.color??fallbackDesignOptions[index]?.color??"blue"),
      description:String(item.description??fallbackDesignOptions[index]?.description??"Print-ready design"),
    })).slice(0,3)
    : fallbackDesignOptions;
  const replaceMaterial=(value:GeneratedMaterial)=>setMaterials((current)=>current.map((item)=>item.id===value.id?value:item));
  const save=async()=>{if(!selected)return;const value=await lessonKitApi.updateGeneratedMaterial(selected.id,{title,content:{...selected.content,instruction,reward,artwork,selectedDesignVariant:designId},printLayout:{...selected.printLayout,pageSize,color:theme}});replaceMaterial(value);setDirty(false);onFeedback(`${title} changes saved.`);};
  const approve=async()=>{if(!selected)return;if(dirty)await save();const value=await lessonKitApi.approveGeneratedMaterial(selected.id);replaceMaterial(value);setApproved(true);setDirty(false);onFeedback(`${title} approved for print.`);};
  const quickEdit=async(action:MaterialQuickEditAction)=>{if(!selected)return;try{if(action==="regenerate_artwork"){setImageBusy(true);const value=await lessonKitApi.generateGeneratedMaterialImage(selected.id);replaceMaterial(value);onFeedback("Artwork generation started. You can continue editing while it finishes.");return;}const value=await lessonKitApi.quickEditGeneratedMaterial(selected.id,action);replaceMaterial(value);onFeedback(`${value.title} quick edit applied.`);}catch(reason){onFeedback(reason instanceof Error?reason.message:"The quick edit could not be applied.");}finally{if(action==="regenerate_artwork")setImageBusy(false);}};
  const exportPdf=async()=>{try{
    const visualMaterials=materials.filter((item)=>imageMaterialTypes.includes(item.type));
    const generating=visualMaterials.find((item)=>["pending","processing"].includes(String(item.content.imageGenerationStatus??"")));
    if(generating){setSelectedId(generating.id);onFeedback("Custom artwork is still generating. Review it before printing the complete kit.");return;}
    const missing=visualMaterials.find((item)=>!hasCompleteVisualSet(item));
    if(missing){setSelectedId(missing.id);onFeedback(`${missing.title} is still missing one or more custom visuals. The complete kit will not print until every visual is ready.`);return;}
    const approvedMaterials:GeneratedMaterial[]=[];
    for(const material of materials)approvedMaterials.push(material.status==="approved"?material:await lessonKitApi.approveGeneratedMaterial(material.id));
    const latest=await lessonKitApi.getLessonPackage(lessonPackage.id);
    if(latest.status!=="approved")await lessonKitApi.approveLessonPackage(latest.id,latest.version??1,"Teacher approved complete printable lesson kit");
    setMaterials(approvedMaterials);
    const job=await lessonKitApi.createPrintableLessonKit(lessonPackage.id,{materialIds:approvedMaterials.map((item)=>item.id),pageSize,reviewedConfirmation:true});
    if(job.status!=="completed"){onFeedback(job.message);return;}
    const download=await lessonKitApi.getPrintableLessonKitDownload(job.exportId);
    window.location.assign(download.downloadUrl);
    onFeedback("Complete lesson kit PDF prepared for printing.");
  }catch(reason){onFeedback(reason instanceof Error?reason.message:"Printable lesson kit could not be prepared.");}};
  return <section><div className="v2-page-heading"><h1>Review Printable Content</h1><p>Open a material, inspect the print layout, and make edits before export.</p></div><div className="v2-print-layout">
    <Card className="v2-print-sidebar"><div className="v2-print-learner"><LearnerAvatar learnerId={learner?.id ?? lessonPackage.learnerId} avatar={learner?.avatar} alt={`${learner?.code ?? "Learner"} avatar`} size={64}/><div><strong>{learner?.code??"Learner"}</strong><small>Lesson goal</small><b>{goalTitle}</b></div></div><h3>Materials</h3>{materials.map((material)=><button onClick={()=>setSelectedId(material.id)} className={`v2-material-nav ${selected?.id===material.id?"is-active":""}`} key={material.id}><span>{material.type==="visual_card"?"🚙":material.type==="help_card"?"💬":material.type==="token_board"?"○○":material.type==="data_sheet"?"▦":"▤"}</span><span>{material.title}</span>{material.status==="approved"&&<b>✓</b>}</button>)}</Card>
    <div className="v2-print-center"><Card className="v2-print-preview"><div className="v2-preview-head"><h2>{title||"Material"} Preview</h2><Button variant="secondary" onClick={()=>void exportPdf()}>↓ Print Complete Kit PDF</Button></div>{needsArtwork&&!hasArtwork&&<div className={`v2-artwork-callout ${imageStatus==="failed"?"is-failed":""}`} role="status"><div><strong>{["pending","processing"].includes(imageStatus)?"Creating custom artwork…":"This material needs custom artwork"}</strong><small>{["pending","processing"].includes(imageStatus)?"You can keep editing while it finishes.":"Generate an age-respectful, lesson-specific illustration before printing."}</small></div>{!["pending","processing"].includes(imageStatus)&&<Button disabled={imageBusy} onClick={()=>void quickEdit("regenerate_artwork")}>{imageBusy?"Starting…":"Generate artwork"}</Button>}</div>}{selected&&<div className={`v2-paper v2-paper--${theme}`}><PrintableMaterialCanvas material={selected} title={title} instruction={instruction} reward={`${reward} ${rewardIcon}`} tokenCount={tokenCount} artwork={artwork}/></div>}</Card><Card className="v2-print-controls"><span>▣ &nbsp; Print view</span><label>Page size <select value={pageSize} onChange={(event)=>{setPageSize(event.target.value as "Letter"|"A4");setDirty(true);}}><option>Letter</option><option>A4</option></select></label><label>Zoom <select defaultValue="100%"><option>100%</option><option>80%</option><option>120%</option></select></label><label>Preview in color <input type="checkbox" defaultChecked/></label></Card><Card className="v2-issues"><h3>Issues to review</h3><div className="v2-print-checks"><span>✓ Text is readable</span><span>{hasArtwork||!needsArtwork?"✓":"○"} Artwork reviewed</span><span>✓ Margins are print-safe</span></div></Card></div>
    <Card className="v2-edit-material"><div className="v2-preview-head"><h2>Choose a finished design</h2>{approved&&<Tag tone="green">Approved</Tag>}</div><p className="v2-design-intro">Each option is a complete rendering of this material—not a color swatch.</p><div className="v2-design-options">{designOptions.map((option)=><button type="button" className={`v2-design-option v2-design-option--${option.color} ${designId===option.id?"is-active":""}`} onClick={()=>{setDesignId(option.id);setTheme(option.color);setDirty(true);}} key={option.id}><span className={`v2-design-preview v2-paper--${option.color}`}>{selected&&<PrintableMaterialCanvas material={{...selected,printLayout:{...selected.printLayout,color:option.color}}} title={title} instruction={instruction} reward={`${reward} ${rewardIcon}`} tokenCount={tokenCount} artwork={artwork}/>}</span><b>{option.label}</b><small>{option.description}</small>{designId===option.id&&<em>✓ Selected</em>}</button>)}</div>
      <h3 className="v2-quick-title">✦ Change with AI</h3><button className="v2-quick-edit" onClick={()=>void quickEdit("simplify_wording")}>T² &nbsp; Make wording shorter</button><button className="v2-quick-edit" disabled={imageBusy||["pending","processing"].includes(String(selected?.content.imageGenerationStatus??""))} onClick={()=>void quickEdit("regenerate_artwork")}>↻ &nbsp; {imageBusy||["pending","processing"].includes(String(selected?.content.imageGenerationStatus??""))?"Creating a new illustration…":"Create a new illustration"}</button><button className="v2-quick-edit" onClick={()=>void quickEdit("adjust_reward")}>♢ &nbsp; Suggest another reward</button>
      <details className="v2-optional-edits"><summary>Fine-tune text or layout (optional)</summary><label>Material title<input value={title} onChange={(event)=>{setTitle(event.target.value);setDirty(true);}}/></label><label>Instruction text<input value={instruction} onChange={(event)=>{setInstruction(event.target.value);setDirty(true);}}/></label><label>Reward item<select value={reward} onChange={(event)=>{setReward(event.target.value);setDirty(true);}}><option>Car</option><option>Bubbles</option><option>Music break</option></select></label><label>Theme color<div className="v2-color-row">{colors.map((color)=><button type="button" aria-label={color} className={`${theme===color?"is-active":""} v2-color-${color}`} onClick={()=>{setTheme(color);setDirty(true);}} key={color}>{theme===color?"✓":""}</button>)}</div></label><label>Layout option<select value={layout} onChange={(event)=>{setLayout(event.target.value);setDirty(true);}}><option>5-token row</option><option>5-token grid</option><option>3-token row</option></select></label></details>
      {dirty&&<small role="status">Design change not saved yet</small>}<Button fullWidth onClick={()=>void save()}>Save Design</Button><Button variant="secondary" fullWidth onClick={()=>void approve()}>Approve for Print</Button></Card>
  </div><div className="v2-page-actions"><Button variant="secondary" onClick={onBack}>Back to Package</Button></div></section>;
}
