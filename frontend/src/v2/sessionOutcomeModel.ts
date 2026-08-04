import type { CompleteSessionInput,SessionCompletionTemplate,SessionRunDraftTrial,SessionTrialObservation,SessionTrialOutcome } from "./types";

export function createSessionTrials(template:SessionCompletionTemplate):SessionRunDraftTrial[] {
  return Array.from({length:template.plannedOpportunities},(_,index)=>({
      trialId:`${template.sessionId}-trial-${index+1}`,
      opportunityNumber:index+1,
      contextId:null,
      contextLabel:null,
      valid:null,
      outcome:null,
      responseMode:null,
      promptLevel:null,
      latencySeconds:null,
      breakRequested:null,
      breakDelivered:null,
      returnedAfterBreak:null,
      materialIdsUsed:[],
      note:"",
  }));
}

export function applyTrialOutcome(trial:SessionRunDraftTrial,outcome:SessionTrialOutcome):SessionRunDraftTrial {
  if(outcome==="cancelled")return {...trial,outcome,valid:false,responseMode:null,promptLevel:null,latencySeconds:null,breakRequested:null,breakDelivered:null,returnedAfterBreak:null};
  if(outcome==="no_response")return {...trial,outcome,valid:true,responseMode:null};
  return {...trial,outcome,valid:true};
}

export function buildSessionCompletionInput(template:SessionCompletionTemplate,startedAt:string,trials:SessionTrialObservation[],teacherNotes:string,engagementLevel:number|null,regulationLevel:number|null):CompleteSessionInput {
  return {
    expectedLessonPackageId:template.lessonPackageId,
    expectedLessonSpecId:template.lessonSpecId,
    expectedGoalId:template.goalId,
    startedAt,
    completedAt:new Date().toISOString(),
    trials,
    generalization:{status:"not_attempted",people:[],settings:[],materials:[]},
    helpfulMaterialIds:[],
    unhelpfulMaterialIds:[],
    observations:{engagementLevel,regulationLevel,teacherNotes,rawCountsConfirmed:true},
  };
}
