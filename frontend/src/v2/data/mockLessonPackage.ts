import type { GeneratedMaterial, LessonDesignDraft, LessonPackage } from "../types";

export function createMockPackage(draft: LessonDesignDraft): LessonPackage {
  const id=`package-${draft.learnerId}`;
  const availableMaterials: GeneratedMaterial[] = [
    { id:"visual-card", packageId:id, type:"visual_card", title:"Visual Card", status:"ready", content:{ instruction:"I need help", artwork:"Communication prompt" }, printLayout:{ pageSize:"Letter",orientation:"portrait",color:"blue" } },
    { id:"help-card", packageId:id, type:"help_card", title:"Help Card", status:"ready", content:{ instruction:"Help, please", artwork:"Raised hand" }, printLayout:{ pageSize:"Letter",orientation:"portrait",color:"green" } },
    { id:"token-board", packageId:id, type:"token_board", title:"Token Board", status:"ready", content:{ instruction:"Earn 5 stars, then get a reward!", reward:"Car", tokens:5 }, printLayout:{ pageSize:"Letter",orientation:"landscape",color:"blue" } },
    { id:"data-sheet", packageId:id, type:"data_sheet", title:"Data Sheet", status:"ready", content:{ columns:["Scenario","Independent","Prompted","Notes"] }, printLayout:{ pageSize:"Letter",orientation:"portrait",color:"blue" } },
    { id:"summary-template", packageId:id, type:"summary_template", title:"Summary Template", status:"ready", content:{ instruction:"Record what worked, challenges, and next steps." }, printLayout:{ pageSize:"Letter",orientation:"portrait",color:"blue" } },
  ];
  const selectedTitles=new Set(draft.selectedMaterials.map((item)=>item.replace(/s$/, "")));
  const materials=availableMaterials.filter((item)=>item.type==="help_card"||item.type==="summary_template"||selectedTitles.has(item.title));
  return { id,learnerId:draft.learnerId,draftId:draft.id,goal:draft.goalText,duration:draft.duration,theme:draft.theme,lessonBrief:"Practice asking for help across familiar, motivating situations.",teachingFlow:[
    { id:"step-1",title:"Warm-up",description:"Preview the help card and model the target phrase.",duration:"2 min",teacherAction:"Model and point to the visual.",learnerAction:"Attend and imitate when ready." },
    { id:"step-2",title:"Guided practice",description:"Practice selected scenarios with prompt fading.",duration:"6 min",teacherAction:"Create a help opportunity and wait.",learnerAction:"Use the target phrase to ask for help." },
    { id:"step-3",title:"Independent practice",description:"Fade prompts during a second scenario.",duration:"2 min",teacherAction:"Wait and reinforce an independent request.",learnerAction:"Ask for help with less support." },
    { id:"step-4",title:"Generalize",description:"Use the phrase in a new situation.",duration:"2 min",teacherAction:"Create a natural opportunity and celebrate success.",learnerAction:"Use the skill in a new context." },
  ],materials,summaryTemplate:"Note what worked, prompt level, and a next-step recommendation." };
}
