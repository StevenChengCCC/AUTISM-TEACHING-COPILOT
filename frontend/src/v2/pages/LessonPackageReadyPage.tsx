import { useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { lessonKitApi } from "../api/lessonKitApi";
import type { LearnerProfile,LessonPackage } from "../types";

export function LessonPackageReadyPage({ lessonPackage,onReview,onEdit,onStartOver,onFeedback }:{ lessonPackage:LessonPackage|null;onReview:()=>void;onEdit:()=>void;onStartOver:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);const [exports,setExports]=useState<Record<string,boolean>>({pdf:true});
  useEffect(()=>{if(lessonPackage)void lessonKitApi.getLearnerById(lessonPackage.learnerId).then(setLearner);},[lessonPackage]);
  if(!lessonPackage)return <section className="v2-empty"><h2>No lesson package yet</h2><Button onClick={onStartOver}>Start a New Lesson</Button></section>;
  const goalTitle=lessonPackage.goal.toLowerCase().includes("ask for help")?"Asking for Help":lessonPackage.goal;
  const toggle=(id:string)=>{setExports((current)=>({...current,[id]:current[id]===false}));onFeedback("Export selection updated.");};
  return <section><div className="v2-page-heading"><h1>Lesson Package Ready</h1><p>Review the generated teaching package before exporting or printing.</p></div>
    <div className="v2-package-layout"><div><Card className="v2-summary-strip"><div><span>{learner?.avatar??"👦🏻"}</span><small>Learner</small><strong>{learner?.code??"Learner"}</strong></div><div><span>◎</span><small>Goal</small><strong>{goalTitle}</strong></div><div><span>◷</span><small>Duration</small><strong>{lessonPackage.duration}</strong></div><div><span>🚙</span><small>Theme</small><strong>{lessonPackage.theme}</strong></div></Card>
      <div className="v2-package-modules"><Card><h2><span>▤</span> 1. Lesson Brief</h2><strong>{lessonPackage.lessonBrief}</strong><hr/><h3>Key Strategies</h3>{["Visual support","Model and prompt","Positive reinforcement"].map((item)=><p key={item}>✓ &nbsp; {item}</p>)}</Card><Card><h2><span>⌘</span> 2. Teaching Flow</h2>{lessonPackage.teachingFlow.map((step,index)=><div className="v2-flow-step" key={step.id}><b>{index+1}</b><strong>{step.title}</strong><span>{step.description}</span></div>)}</Card>
        <Card><h2><span>▰</span> 3. Materials Included</h2><div className="v2-included-materials">{lessonPackage.materials.filter((item)=>item.type!=="summary_template").map((material)=><div key={material.id}><span>{material.type==="visual_card"?"🚙":material.type==="help_card"?"💬":material.type==="token_board"?"○○○⭐":"▦"}</span><small>{material.title}</small></div>)}</div></Card><Card><h2><span>▧</span> 4. Post-Lesson Summary Template</h2>{["What worked well?","What was challenging?","Next steps / Notes"].map((item)=><div className="v2-summary-line" key={item}><span>{item}</span><i/></div>)}</Card></div>
    </div><Card className="v2-export-panel"><h2>⇩ &nbsp; Export Options</h2><p>Select the items to include in your export.</p>{[{id:"pdf",label:"Printable PDF"},...lessonPackage.materials.map((item)=>({id:item.id,label:item.title}))].map((item)=><label key={item.id}><input type="checkbox" checked={exports[item.id]!==false} onChange={()=>toggle(item.id)}/><span>▧</span>{item.label}</label>)}<Button fullWidth onClick={onReview}>Review Printable Content</Button><Button variant="secondary" fullWidth onClick={onEdit}>Back to Edit Lesson</Button></Card></div>
    <div className="v2-how-it-works"><strong>How this works &nbsp; ⓘ</strong><span>⇩ <b>Review outputs</b><small>Preview the teaching materials</small></span><i>→</i><span>✓ <b>Export or print</b><small>Choose items and export</small></span><i>→</i><span>▣ <b>Use in session</b><small>Bring materials to your session</small></span></div>
  </section>;
}
