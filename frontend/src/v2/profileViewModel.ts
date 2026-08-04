import type { LearnerProfile,ProfileFactor,ProfileFactorCategory } from "./types";

export const profileFactorSections:{title:string;categories:ProfileFactorCategory[]}[]=[
  {title:"Communication and access",categories:["communication","receptive_language","language","motor_access"]},
  {title:"Learning strengths",categories:["learning_strength"]},
  {title:"Attention and sensory access",categories:["attention","sensory","visual_access","safety"]},
  {title:"Current interests",categories:["current_interest"]},
  {title:"Reinforcement",categories:["reinforcement"]},
  {title:"Transition support",categories:["transition","regulation"]},
  {title:"Prompting requirements",categories:["prompting","error_correction"]},
  {title:"Generalization",categories:["generalization"]},
  {title:"Historical information",categories:[]},
  {title:"Not approved or prohibited",categories:[]},
  {title:"Needs teacher confirmation",categories:[]},
];

export function visibleFactorsForSection(factors:ProfileFactor[],title:string,categories:ProfileFactorCategory[]):ProfileFactor[]{
  return factors.filter((factor)=>title==="Historical information"?factor.status==="historical":title==="Not approved or prohibited"?factor.category==="prohibited_item"||["not_approved","not_meaningful","omitted","rejected"].includes(factor.status):title==="Needs teacher confirmation"?factor.status==="unconfirmed":categories.includes(factor.category)&&["confirmed_current","teacher_confirmed","teacher_edited","derived"].includes(factor.status));
}

export function factorStatusLabel(factor:ProfileFactor):string{
  if(factor.status==="unconfirmed")return "Needs confirmation";
  if(factor.status==="historical")return "Historical";
  if(factor.status==="not_approved"||factor.status==="not_meaningful"||factor.status==="omitted"||factor.status==="rejected")return "Not approved";
  if(["sensory","visual_access","motor_access","safety","prohibited_item"].includes(factor.category))return "Safety/access requirement";
  return "Confirmed";
}

export function profileSummaryView(learner:LearnerProfile){
  const summary=learner.normalizedProfile?.summary;
  return {
    communication:summary?.communication||learner.communicationMode,
    supports:summary?.supports||learner.supportNeeds,
    currentInterests:summary?.currentInterests||learner.interests,
    learningFormat:summary?.learningFormat||learner.attentionProfile,
    keyTeachingNotes:summary?.keyTeachingNotes||[learner.notes].filter(Boolean),
  };
}
