import { useEffect, useMemo, useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { LearnerProfile } from "../types";

export function StartNewLessonPage({ onSelectExisting,onCreateNew,onFeedback }: { onSelectExisting:(id:string)=>void;onCreateNew:()=>void;onFeedback:(message:string)=>void }) {
  const [allLearners,setAllLearners]=useState<LearnerProfile[]>([]);
  const [query,setQuery]=useState("");
  const [selectedId,setSelectedId]=useState("a102");
  useEffect(()=>{ void lessonKitApi.getLearners().then(setAllLearners); },[]);
  const learners=useMemo(()=>allLearners.filter((learner)=>["a102","b214","c087"].includes(learner.id)&&learner.code.toLowerCase().includes(query.toLowerCase())),[allLearners,query]);
  return <>
    <div className="v2-page-heading"><h1>Start a New Lesson</h1><p>Choose an existing learner or create a new learner profile before planning the lesson.</p></div>
    <div className="v2-start-grid">
      <Card className="v2-start-card"><h2><span className="v2-heading-icon">♙</span> Use Existing Learner</h2><label className="v2-search"><span>⌕</span><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search learners by code" /></label>
        <div className="v2-learner-list">{learners.map((learner)=><button key={learner.id} className={selectedId===learner.id?"is-selected":""} onClick={()=>{setSelectedId(learner.id);onSelectExisting(learner.id);}}><span className="v2-list-avatar">{learner.avatar}</span><span className="v2-list-copy"><strong>{learner.code}</strong><small>Age {learner.age}</small></span><span className="v2-list-tags">{learner.tags.slice(0,2).map((tag,index)=><Tag tone={index?"green":"blue"} key={tag}>{tag}</Tag>)}</span><span className="v2-chevron">›</span></button>)}</div>
        <Button fullWidth disabled={!selectedId} onClick={()=>onSelectExisting(selectedId)}>Select Learner</Button>
      </Card>
      <Card className="v2-start-card v2-new-card"><h2><span className="v2-heading-icon">♙</span> Create New Learner</h2><p>Create a learner profile first, then upload records and review the information.</p><div className="v2-new-layout"><ol className="v2-create-steps"><li><span>♙</span>Create learner code</li><li><span>♡</span>Add basic support needs</li><li><span>⇧</span>Upload records next</li></ol><div className="v2-profile-preview"><strong>New learner profile</strong><span className="v2-preview-avatar">🧒🏻</span><div><b>Learner N-501</b><Tag>New</Tag><i/><i/></div></div></div><Button fullWidth onClick={onCreateNew}>Create New Learner</Button><Button variant="secondary" fullWidth onClick={()=>onFeedback("Choose Create New Learner, then add records and review the extracted profile.")}>ⓘ &nbsp; Learn how this works</Button></Card>
    </div><div className="v2-path-hint"><span><b>Existing learner</b> → Review &amp; update learner information</span><span><b>New learner</b> → Upload records, then review &amp; edit information</span></div>
  </>;
}
