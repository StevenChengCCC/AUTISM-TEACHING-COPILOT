import { mockLearners } from "./data/mockLearners";
import { createInitialChat } from "./data/mockLessonDraft";
import { createMockPackage } from "./data/mockLessonPackage";
import { mockMaterials } from "./data/mockMaterials";
import { mockRecentLessons } from "./data/mockRecentLessons";
import { mockRecords } from "./data/mockRecords";
import { mockSessions,mockSessionStats } from "./data/mockSessions";
import type { AIChatState, AIQuestion, LearnerProfileExtraction, LessonDesignDraft, LessonPackage } from "./types";

const chats = new Map<string, AIChatState>();
const packages = new Map<string, LessonPackage>();
const copy = <T,>(value:T):T => structuredClone(value);
const pause = async <T,>(value:T):Promise<T> => Promise.resolve(copy(value));

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
  getLearners: () => pause(mockLearners),
  getLearnerById: (id:string) => pause(mockLearners.find((learner) => learner.id === id) ?? null),
  getRecordsForLearner: (learnerId:string) => pause(mockRecords.filter((record) => record.learnerId === learnerId)),
  getExtractedLearnerProfile: async (learnerId:string):Promise<LearnerProfileExtraction> => {
    const learner=mockLearners.find((item)=>item.id===learnerId);
    if(!learner) throw new Error("Learner not found");
    const records=mockRecords.filter((record)=>record.learnerId===learnerId);
    return pause({learner,records,insights:["Use visual supports","Keep activities short","Add multiple examples"],analyzedRecordCount:records.length,status:"complete"});
  },
  getInitialLessonChat: async (learnerId:string) => {
    const key=`conversation-${learnerId}`;
    if (!chats.has(key)) chats.set(key,createInitialChat(learnerId));
    return pause(chats.get(key)!);
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
  sendChatMessage: async (conversationId:string,content:string) => {
    const chat=chats.get(conversationId);
    if(!chat) throw new Error("Conversation not found");
    const sequence=chat.messages.length+1;
    chat.messages.push(
      {id:`message-${sequence}`,role:"teacher",content,createdAt:"Just now"},
      {id:`message-${sequence+1}`,role:"assistant",content:"Got it. I’ve added that guidance to the lesson conversation.",createdAt:"Just now"},
    );
    chat.draft.customNotes=[chat.draft.customNotes,content].filter(Boolean).join(" ");
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
  getGeneratedMaterials: async (packageId:string) => pause(packages.get(packageId)?.materials ?? []),
  getSessions: () => pause(mockSessions),
  getSessionStats: () => pause(mockSessionStats),
  getRecentLessonsForLearner: (learnerId:string) => pause(mockRecentLessons.filter((lesson)=>lesson.learnerId===learnerId)),
  getMaterials: () => pause(mockMaterials),
};
