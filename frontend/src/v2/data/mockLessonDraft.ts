import type { AIChatState, AIQuestion, LessonDesignDraft } from "../types";

export const createLessonDraft = (learnerId: string): LessonDesignDraft => ({
  id:`draft-${learnerId}`, learnerId, goalText:"Learner will ask for help using a short phrase.",
  responseLevel:"Short phrase", scenarios:["Toy car stuck","Closed box"],
  selectedMaterials:["Visual Cards","Token Board","Data Sheet"], theme:"Vehicles", duration:"10–12 min", customNotes:"",
});

const option = (id:string,label:string,icon:string,recommended=false) => ({ id,label,value:label,description:"",icon,recommended,source:"ai_generated" as const });

export const lessonQuestions: AIQuestion[] = [
  { id:"response-level", prompt:"What level of response should we target?", helperText:"Choose a level that is achievable with the learner’s current communication skills.", field:"responseLevel", inputType:"single_select", options:[option("single-word","Single word","①"),option("short-phrase","Short phrase","💬",true),option("full-sentence","Full sentence","▤")], selectedOptionIds:["short-phrase"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:1 },
  { id:"scenarios", prompt:"Which scenarios would you like to include?", helperText:"Select familiar situations where asking for help is useful.", field:"scenarios", inputType:"multi_select", options:[option("toy-car","Toy car stuck","🚙",true),option("closed-box","Closed box","▣",true),option("backpack","Backpack zipper","🎒")], selectedOptionIds:["toy-car","closed-box"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:3 },
  { id:"materials", prompt:"Which materials would you like to use?", helperText:"The suggested set supports prompting, reinforcement, and data collection.", field:"selectedMaterials", inputType:"hybrid", options:[option("visual-cards","Visual Cards","▧",true),option("token-board","Token Board","☆",true),option("data-sheet","Data Sheet","▦",true),option("summary","Summary Template","▤")], selectedOptionIds:["visual-cards","token-board","data-sheet"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:4 },
];

export const createInitialChat = (learnerId:string): AIChatState => ({
  conversationId:`conversation-${learnerId}`, learnerId,
  messages:[
    { id:"m1", role:"teacher", content:`I want to teach ${learnerId==="a102"?"Learner A-102":"this learner"} to ask for help.`, createdAt:"10:24 AM" },
  ], questions:structuredClone(lessonQuestions), draft:createLessonDraft(learnerId), canGenerate:true,
});
