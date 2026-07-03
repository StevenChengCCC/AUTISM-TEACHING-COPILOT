import type { LessonSession,LessonSessionStat } from "../types";
export const mockSessions: LessonSession[] = [
  { id:"s1",learnerId:"a102",goal:"Asking for Help",status:"planned",updatedAt:"Today 2:30 PM" },
  { id:"s2",learnerId:"b214",goal:"Following Directions",status:"completed",updatedAt:"Yesterday" },
  { id:"s3",learnerId:"n501",goal:"Identify Emotions",status:"draft",updatedAt:"Saved 1 hour ago" },
  { id:"s4",learnerId:"c087",goal:"Sorting Objects",status:"in_progress",updatedAt:"Today" },
];
export const mockSessionStats:LessonSessionStat[] = [
  {status:"planned",label:"Planned",count:12,helperText:"Upcoming sessions"},
  {status:"in_progress",label:"In Progress",count:5,helperText:"Active sessions"},
  {status:"completed",label:"Completed",count:18,helperText:"Finished sessions"},
  {status:"draft",label:"Drafts",count:7,helperText:"Not yet scheduled"},
];
