import { useEffect, useMemo, useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { LearnerProfile } from "../types";
import { LearnerAvatar } from "../components/Avatar";
import { UsabilityStudyPanel } from "../components/UsabilityStudyPanel";

export function StartNewLessonPage({ onSelectExisting,onCreateNew,onFeedback }: { onSelectExisting:(id:string)=>void;onCreateNew:()=>void;onFeedback:(message:string)=>void }) {
  const [allLearners,setAllLearners]=useState<LearnerProfile[]>([]);
  const [query,setQuery]=useState("");
  const [selectedId,setSelectedId]=useState("");
  const [loading,setLoading]=useState(true);
  const [fixtureBusy,setFixtureBusy]=useState(false);
  useEffect(()=>{
    void lessonKitApi.getLearners()
      .then((items)=>{setAllLearners(items);setSelectedId((current)=>current||items[0]?.id||"");})
      .catch((error)=>onFeedback(error instanceof Error?error.message:"Learners could not be loaded."))
      .finally(()=>setLoading(false));
  },[onFeedback]);
  const learners=useMemo(()=>allLearners.filter((learner)=>learner.code.toLowerCase().includes(query.toLowerCase())),[allLearners,query]);
  const resetN482=async()=>{setFixtureBusy(true);try{const fixture=await lessonKitApi.resetSyntheticN482Fixture();const items=await lessonKitApi.getLearners();setAllLearners(items);setSelectedId(fixture.learnerId);setQuery("Synthetic N-482");onFeedback("Synthetic N-482 was reset to its current approved acceptance state.");}catch(error){onFeedback(error instanceof Error?error.message:"The synthetic fixture could not be reset.");}finally{setFixtureBusy(false);}};
  return <>
    <div className="v2-page-heading"><h1>Start a New Lesson</h1><p>Choose an existing learner or create a new learner profile before planning the lesson.</p></div>
    <div className="v2-start-grid">
      <Card className="v2-start-card"><h2><span className="v2-heading-icon">♙</span> Use Existing Learner</h2><label className="v2-search"><span>⌕</span><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search learners by code" /></label>
        <div className="v2-learner-list" aria-label="Learners">{loading?<p className="v2-empty-state">Loading learners…</p>:learners.length===0?<p className="v2-empty-state">No learners match this search.</p>:learners.map((learner)=><button key={learner.id} className={selectedId===learner.id?"is-selected":""} onClick={()=>setSelectedId(learner.id)} onDoubleClick={()=>onSelectExisting(learner.id)} title="Select once, or double-click to open"><LearnerAvatar learnerId={learner.id} avatar={learner.avatar} alt="" size={58}/><span className="v2-list-copy"><strong>{learner.code}</strong><small>{learner.age>0?`Age ${learner.age}`:"Age to confirm"}</small></span><span className="v2-list-tags">{learner.tags.slice(0,2).map((tag,index)=><Tag tone={index?"green":"blue"} key={tag}>{tag}</Tag>)}</span><span className="v2-chevron">›</span></button>)}</div>
        <Button fullWidth disabled={!selectedId} onClick={()=>onSelectExisting(selectedId)}>Select Learner</Button>
        {import.meta.env.DEV&&<div className="v2-synthetic-fixture"><strong>Development acceptance fixture</strong><p>Fully synthetic. Resetting restores current approved N-482 package revisions and local fallbacks.</p><Button variant="secondary" fullWidth disabled={fixtureBusy} onClick={()=>void resetN482()}>{fixtureBusy?"Resetting synthetic N-482…":"Load / reset synthetic N-482"}</Button></div>}
      </Card>
      <Card className="v2-start-card v2-new-card"><h2><span className="v2-heading-icon">♙</span> Create New Learner</h2><p>Create a learner profile first, then upload records and review the information.</p><div className="v2-new-layout"><ol className="v2-create-steps"><li><span>♙</span>Create learner code</li><li><span>♡</span>Add basic support needs</li><li><span>⇧</span>Upload records next</li></ol><div className="v2-profile-preview"><strong>New learner profile</strong><LearnerAvatar learnerId="new-learner" alt="" size={84}/><div><b>Learner N-501</b><Tag>New</Tag><i/><i/></div></div></div><Button fullWidth onClick={onCreateNew}>Create New Learner</Button><Button variant="secondary" fullWidth onClick={()=>onFeedback("Choose Create New Learner, then add records and review the extracted profile.")}>ⓘ &nbsp; Learn how this works</Button></Card>
    </div><div className="v2-path-hint"><span><b>Existing learner</b> → Review &amp; update learner information</span><span><b>New learner</b> → Upload records, then review &amp; edit information</span></div>
    {import.meta.env.DEV&&<UsabilityStudyPanel/>}
  </>;
}
