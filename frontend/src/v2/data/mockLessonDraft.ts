import type { AIChatState, AIQuestion, LessonDesignDraft } from "../types";

const option = (id:string,label:string,icon:string,recommended=false) => ({ id,label,value:label,description:"",icon,recommended,source:"ai_generated" as const });

const generatedQuestions: AIQuestion[] = [
  { id:"response-level", prompt:"What level of response should we target?", helperText:"Choose a level that is achievable with the learner’s current communication skills.", field:"responseLevel", inputType:"single_select", options:[option("single-word","Single word","①"),option("short-phrase","Short phrase","💬",true),option("full-sentence","Full sentence","▤")], selectedOptionIds:["short-phrase"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:1 },
  { id:"scenarios", prompt:"Which scenarios would you like to include?", helperText:"Select familiar situations where asking for help is useful.", field:"scenarios", inputType:"multi_select", options:[option("toy-car","Toy car stuck","🚙",true),option("closed-box","Closed box","▣",true),option("backpack","Backpack zipper","🎒")], selectedOptionIds:["toy-car","closed-box"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:3 },
  { id:"materials", prompt:"Which materials would you like to use?", helperText:"The suggested set supports prompting, reinforcement, and data collection.", field:"selectedMaterials", inputType:"hybrid", options:[option("visual-cards","Visual Cards","▧",true),option("token-board","Token Board","☆",true),option("data-sheet","Data Sheet","▦",true),option("summary","Summary Template","▤")], selectedOptionIds:["visual-cards","token-board","data-sheet"], allowCustomAnswer:true, customAnswer:"", required:true, maxSelections:4 },
];

const createEmptyDraft = (learnerId:string):LessonDesignDraft => ({
  id:`draft-${learnerId}`,learnerId,goalText:"",responseLevel:"",scenarios:[],selectedMaterials:[],theme:"",duration:"",customNotes:"",
});

export function createEmptyChat(learnerId:string):AIChatState {
  return {
    conversationId:`conversation-${learnerId}`,
    learnerId,
    messages:[{id:"greeting",role:"assistant",content:"Tell me what you want to teach today, and I’ll help turn it into a lesson kit.",createdAt:"Just now"}],
    questions:[],
    draft:createEmptyDraft(learnerId),
    canGenerate:false,
  };
}

export function createQuestionsFromTeacherRequest(learnerId:string,teacherRequest:string) {
  const asksForHelp=teacherRequest.toLowerCase().includes("ask for help")||teacherRequest.toLowerCase().includes("asking for help");
  const draft:LessonDesignDraft={
    id:`draft-${learnerId}`,
    learnerId,
    goalText:asksForHelp?"Learner will ask for help using a short phrase.":"Learner will practice the requested skill with teacher support.",
    responseLevel:"Short phrase",
    scenarios:["Toy car stuck","Closed box"],
    selectedMaterials:["Visual Cards","Token Board","Data Sheet"],
    theme:"Vehicles",
    duration:"10–12 min",
    customNotes:asksForHelp?"":teacherRequest,
  };
  return {questions:structuredClone(generatedQuestions),draft};
}
