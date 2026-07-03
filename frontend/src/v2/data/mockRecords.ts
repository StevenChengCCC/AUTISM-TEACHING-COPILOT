import type { LearnerRecord } from "../types";
export const mockRecords: LearnerRecord[] = [
  { id:"r1",learnerId:"a102",fileName:"IEP summary.pdf",fileType:"IEP summary",status:"reviewed",uploadedAt:"Updated Apr 18, 2024",extractedText:"Uses short phrases and benefits from strong visual supports." },
  { id:"r2",learnerId:"a102",fileName:"Assessment.pdf",fileType:"Assessment",status:"ready",uploadedAt:"Updated Jan 22, 2024",extractedText:"Attention improves with short, engaging activities and clear transitions." },
  { id:"r3",learnerId:"a102",fileName:"Session notes.txt",fileType:"Session notes",status:"reviewed",uploadedAt:"Updated Apr 10, 2024",extractedText:"Responds to praise, choices, and car-themed rewards." },
  { id:"r4",learnerId:"n501",fileName:"IEP summary.pdf",fileType:"PDF",status:"ready",uploadedAt:"Just now",extractedText:"Uses short phrases. Visual prompts support understanding and expression." },
  { id:"r5",learnerId:"n501",fileName:"Intake notes.docx",fileType:"DOCX",status:"reviewed",uploadedAt:"2 minutes ago",extractedText:"Enjoys cars and puzzles. Benefits from hands-on structured activities." },
  { id:"r6",learnerId:"n501",fileName:"Session notes May 12.txt",fileType:"TXT",status:"reviewed",uploadedAt:"5 minutes ago",extractedText:"Attention varies; keep activities short and provide multiple examples." },
];
