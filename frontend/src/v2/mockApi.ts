import { mockLearners } from "./data/mockLearners";
import { createEmptyChat,createQuestionsFromTeacherRequest } from "./data/mockLessonDraft";
import { createMockPackage } from "./data/mockLessonPackage";
import { mockMaterials } from "./data/mockMaterials";
import { mockRecentLessons } from "./data/mockRecentLessons";
import { mockRecords } from "./data/mockRecords";
import { mockSessions,mockSessionStats } from "./data/mockSessions";
import type { AIChatState, AIQuestion, ExportJob, GeneratedMaterial, LearnerProfile, LearnerProfileExtraction, LearnerProgressSummary, LessonDesignDraft, LessonPackage, LessonPackageUpdateInput, LessonSession, LessonSessionSummary, MaterialLibraryItem, MaterialQuickEditAction, ProgressDataPoint, ProgressSignal } from "./types";

const chats = new Map<string, AIChatState>();
const packages = new Map<string, LessonPackage>();
const copy = <T,>(value:T):T => structuredClone(value);
const pause = async <T,>(value:T):Promise<T> => Promise.resolve(copy(value));
const learners=copy(mockLearners);const records=copy(mockRecords);const sessions=copy(mockSessions);const materials=copy(mockMaterials);const progressData:ProgressDataPoint[]=[];

function applyQuestionToDraft(chat:AIChatState, question:AIQuestion) {
  const values = question.selectedOptionIds
    .map((id) => question.options.find((item) => item.id === id && item.source === "ai_generated")?.value)
    .filter((value): value is string => Boolean(value));
  const custom = question.customAnswer.trim();
  if (question.field === "responseLevel") chat.draft.responseLevel = custom || values[0] || "";
  if (question.field === "scenarios") chat.draft.scenarios = [...values, ...(custom ? [custom] : [])];
  if (question.field === "selectedMaterials") chat.draft.selectedMaterials = [...values, ...(custom ? [custom] : [])];
  if (question.field === "customNotes") chat.draft.customNotes = custom;
}

function isAnswered(question:AIQuestion) {
  if (!question.required) return true;
  return question.selectedOptionIds.length > 0 || question.customAnswer.trim().length > 0;
}

export const lessonKitMockApi = {
  getLearners: () => pause(learners),
  getLearnerById: (id:string) => pause(learners.find((learner) => learner.id === id) ?? null),
  createLearner: async (payload:Omit<LearnerProfile,"id">) => {const learner={...payload,id:`learner-local-${learners.length+1}`};learners.push(learner);return pause(learner);},
  updateLearner: async (id:string,payload:Partial<LearnerProfile>) => {const index=learners.findIndex((item)=>item.id===id);if(index<0)throw new Error("Learner not found");learners[index]={...learners[index],...payload};return pause(learners[index]);},
  getRecordsForLearner: (learnerId:string) => pause(records.filter((record) => record.learnerId === learnerId)),
  addRecordForLearner: async (learnerId:string,payload:{fileName:string;fileType:string;text:string}) => {const record={id:`record-local-${records.length+1}`,learnerId,fileName:payload.fileName,fileType:payload.fileType,status:"ready" as const,uploadedAt:"Just now",extractedText:payload.text};records.push(record);return pause(record);},
  getExtractedLearnerProfile: async (learnerId:string):Promise<LearnerProfileExtraction> => {
    const learner=learners.find((item)=>item.id===learnerId);
    if(!learner) throw new Error("Learner not found");
    const learnerRecords=records.filter((record)=>record.learnerId===learnerId);
    return pause({learner,records:learnerRecords,insights:["Use visual supports","Keep activities short","Add multiple examples"],analyzedRecordCount:learnerRecords.length,status:"complete"});
  },
  getInitialLessonChat: async (learnerId:string) => {
    const key=`conversation-${learnerId}`;
    const chat=createEmptyChat(learnerId);
    chats.set(key,chat);
    return pause(chat);
  },
  /** Future backend equivalent: POST /api/v2/lesson-chat returning AIChatState. */
  submitLessonRequest: async (conversationId:string,content:string) => {
    const chat=chats.get(conversationId);
    if(!chat) throw new Error("Conversation not found");
    const cleanContent=content.trim();
    if(!cleanContent) return pause(chat);
    const sequence=chat.messages.length+1;
    chat.messages.push({id:`message-${sequence}`,role:"teacher",content:cleanContent,createdAt:"Just now"});
    if(chat.questions.length===0) {
      const generated=createQuestionsFromTeacherRequest(chat.learnerId,cleanContent);
      chat.questions=generated.questions;
      chat.draft=generated.draft;
      chat.messages.push({id:`message-${sequence+1}`,role:"assistant",content:"Great. I’ll ask a few quick questions so we can generate the right teaching materials.",createdAt:"Just now"});
    } else {
      chat.draft.customNotes=[chat.draft.customNotes,cleanContent].filter(Boolean).join(" ");
      chat.messages.push({id:`message-${sequence+1}`,role:"assistant",content:"Thanks. I’ve kept your lesson choices and added that note to the draft.",createdAt:"Just now"});
    }
    chat.canGenerate=chat.questions.length>0&&chat.questions.every(isAnswered);
    return pause(chat);
  },
  updateAIQuestionAnswer: async (conversationId:string,questionId:string,selectedOptionIds:string[],customAnswer="") => {
    const chat=chats.get(conversationId);
    if (!chat) throw new Error("Conversation not found");
    const question=chat.questions.find((item) => item.id === questionId);
    if (!question) throw new Error("Question not found");
    const customId=`custom-${question.id}`;
    question.options=question.options.filter((option)=>option.id!==customId);
    const baseIds=selectedOptionIds.filter((id)=>id!==customId);
    question.selectedOptionIds=question.inputType === "single_select" ? baseIds.slice(-1) : baseIds.slice(0,question.maxSelections);
    question.customAnswer=customAnswer;
    if(customAnswer.trim()) {
      question.options.push({ id:customId,label:customAnswer.trim(),value:customAnswer.trim(),description:"Added by the teacher",icon:"✎",recommended:false,source:"teacher_custom" });
      question.selectedOptionIds=question.inputType === "single_select" ? [customId] : [...question.selectedOptionIds,customId];
    }
    applyQuestionToDraft(chat,question);
    chat.canGenerate=chat.questions.every(isAnswered);
    return pause(chat);
  },
  clearLessonChat: async (conversationId:string) => {
    const chat=chats.get(conversationId);
    if(!chat) throw new Error("Conversation not found");
    chat.messages=[];
    return pause(chat);
  },
  generateLessonPackageFromDraft: async (draft:LessonDesignDraft) => {
    const lessonPackage=createMockPackage(draft);
    packages.set(lessonPackage.id,lessonPackage);
    return pause(lessonPackage);
  },
  getLessonPackage: async (packageId:string) => {const value=packages.get(packageId);if(!value)throw new Error("Package not found");return pause(value);},
  updateLessonPackage: async (packageId:string,payload:LessonPackageUpdateInput) => {const value=packages.get(packageId);if(!value)throw new Error("Package not found");const updated={...value,...payload,materials:value.materials,safetyReview:value.safetyReview,standardsChecks:value.standardsChecks};packages.set(packageId,updated);return pause(updated);},
  getGeneratedMaterials: async (packageId:string) => pause(packages.get(packageId)?.materials ?? []),
  updateGeneratedMaterial: async (materialId:string,payload:{title:string;content:GeneratedMaterial["content"];printLayout:GeneratedMaterial["printLayout"]}) => updateLocalMaterial(materialId,(item)=>({...item,...payload})),
  approveGeneratedMaterial: async (materialId:string) => updateLocalMaterial(materialId,(item)=>({...item,status:"approved"})),
  quickEditGeneratedMaterial: async (materialId:string,action:MaterialQuickEditAction) => updateLocalMaterial(materialId,(item)=>{const content={...item.content};if(action==="simplify_wording")content.instruction="Ask for help.";if(action==="regenerate_artwork")content.artwork="Updated classroom artwork";if(action==="adjust_reward")content.reward="Choice activity";return {...item,content};}),
  exportLessonPackage: (packageId:string,format:ExportJob["format"]):Promise<ExportJob> => pause({exportId:`export-${packageId}-${format}`,status:"ready",format,downloadUrl:`/mock-downloads/${packageId}.${format}`}),
  getSessions: () => pause(sessions),
  getSessionStats: () => pause(mockSessionStats.map((stat)=>({...stat,count:sessions.filter((item)=>item.status===stat.status).length}))),
  createSession: async (payload:Omit<LessonSession,"id"|"updatedAt">) => {const session={...payload,id:`session-local-${sessions.length+1}`,updatedAt:"Just now"};sessions.push(session);return pause(session);},
  duplicateSession: async (id:string) => {const source=sessions.find((item)=>item.id===id);if(!source)throw new Error("Session not found");const duplicate={...source,id:`session-local-${sessions.length+1}`,status:"draft" as const,updatedAt:"Just now"};sessions.push(duplicate);return pause(duplicate);},
  getSessionSummary: async (id:string):Promise<LessonSessionSummary> => {const session=sessions.find((item)=>item.id===id);if(!session)throw new Error("Session not found");return pause({...session,overview:"Progress includes independence, prompting, participation, engagement, and regulation.",highlights:["Small wins matter."],nextSteps:["Continue gradual prompt fading."]});},
  getRecentLessonsForLearner: (learnerId:string) => pause(mockRecentLessons.filter((lesson)=>lesson.learnerId===learnerId)),
  getMaterials: () => pause(materials),
  createMaterial: async (payload:{title:string;type:string;thumbnailLabel:string;reusable?:boolean}) => {const item:MaterialLibraryItem={...payload,id:`material-local-${materials.length+1}`,source:"template",reusable:payload.reusable??true,createdAt:"Just now"};materials.push(item);return pause(item);},
  duplicateMaterial: async (id:string) => {const source=materials.find((item)=>item.id===id);if(!source)throw new Error("Material not found");const item={...source,id:`material-local-${materials.length+1}`,title:`${source.title} Copy`,createdAt:"Just now"};materials.push(item);return pause(item);},
  getProgressSummaryForLearner: (learnerId:string):Promise<LearnerProgressSummary> => pause({learnerId,currentGoal:"Asking for Help",accuracyPercent:58,independencePercent:42,sessionsPracticed:4,currentPromptLevel:"Level 2",trend:"Slow, uneven growth",message:"Plateau does not mean no progress."}),
  getProgressSignalsForLearner: ():Promise<ProgressSignal[]> => pause([{id:"engagement",type:"engagement",label:"Engagement",description:"Participation is growing.",status:"improving"},{id:"prompt",type:"prompt_fading",label:"Prompt Fading",description:"Moving toward lighter prompts.",status:"emerging"},{id:"generalization",type:"generalization",label:"Generalization Attempts",description:"Trying the skill in new routines.",status:"emerging"},{id:"regulation",type:"regulation_recovery",label:"Regulation / Recovery",description:"Returns after a short break.",status:"stable"},{id:"participation",type:"participation",label:"Participation",description:"Joins supported opportunities.",status:"stable"}]),
  getProgressDataForLearner: (learnerId:string) => pause(progressData.filter((point)=>point.learnerId===learnerId)),
  saveSessionDataRecord: async (payload:{learnerId:string;goal:string;opportunities:number;correct:number;independent:number;promptLevel:string;signalsHighlighted:string[];teacherNotes:string}) => {progressData.push({id:`progress-local-${progressData.length+1}`,learnerId:payload.learnerId,sessionDate:"Today",goal:payload.goal,opportunities:payload.opportunities,accuracyPercent:Math.round(payload.correct/payload.opportunities*100),independencePercent:Math.round(payload.independent/payload.opportunities*100),promptLevel:payload.promptLevel,signalsHighlighted:payload.signalsHighlighted,teacherNotes:payload.teacherNotes});return lessonKitMockApi.getProgressSummaryForLearner(payload.learnerId);},
};

async function updateLocalMaterial(materialId:string,update:(item:GeneratedMaterial)=>GeneratedMaterial):Promise<GeneratedMaterial>{for(const [id,lessonPackage] of packages){const index=lessonPackage.materials.findIndex((item)=>item.id===materialId);if(index>=0){lessonPackage.materials[index]=update(lessonPackage.materials[index]);packages.set(id,lessonPackage);return pause(lessonPackage.materials[index]);}}throw new Error("Generated material not found");}
