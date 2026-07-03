import { useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { lessonKitMockApi } from "../mockApi";
import type { LearnerProfile,LearnerRecord } from "../types";

export function UploadRecordsPage({ learnerId,onContinue,onFeedback }:{ learnerId:string;onContinue:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);const [records,setRecords]=useState<LearnerRecord[]>([]);const [showPaste,setShowPaste]=useState(false);
  useEffect(()=>{void Promise.all([lessonKitMockApi.getLearnerById(learnerId),lessonKitMockApi.getRecordsForLearner(learnerId)]).then(([profile,items])=>{setLearner(profile);setRecords(items);});},[learnerId]);
  const addMockFile=(name="Supplemental classroom notes.txt")=>{if(records.some((record)=>record.fileName===name)){onFeedback(`${name} is already in the upload list.`);return;}setRecords((current)=>[...current,{id:`mock-${current.length+1}`,learnerId,fileName:name,fileType:"TXT",status:"ready",uploadedAt:"Just now",extractedText:"Mock upload ready for profile extraction."}]);onFeedback(`${name} added.`);};
  return <section><div className="v2-page-heading"><h1>Upload Learner Records</h1><p>Upload notes, assessments, or session documents for {learner?.code??"the learner"}.</p></div><div className="v2-upload-layout">
    <Card className="v2-upload-main"><div className="v2-upload-learner"><span>{learner?.avatar??"🧒🏻"}</span><div><h2>{learner?.code??"Learner N-501"} <small>· Age {learner?.age??7}</small></h2><div>{learner?.tags.map((tag)=><Tag key={tag}>{tag}</Tag>)}</div></div></div>
      <button className="v2-dropzone" type="button" onClick={()=>addMockFile("Mock observation notes.txt")}><span>☁</span><h2>Drag and drop files here</h2><p>PDF, DOCX, TXT, or Markdown · up to 25 MB</p></button><div className="v2-or"><span/>or<span/></div><button className="v2-paste-link" onClick={()=>setShowPaste((value)=>!value)}>▣ &nbsp; Paste text instead</button>{showPaste&&<textarea autoFocus className="v2-paste-area" placeholder="Paste learner notes here…" onChange={(event)=>{if(event.target.value.length===1)onFeedback("Pasted text will be included in the mock extraction.");}}/>}
      <h3>Recent uploads</h3><div className="v2-upload-list">{records.map((record)=><div key={record.id}><span className={`v2-file-icon v2-file-${record.fileType.toLowerCase()}`}>{record.fileType}</span><strong>{record.fileName}</strong><Tag tone="green">{record.status==="ready"?"Ready":"Uploaded"}</Tag><small>{record.uploadedAt}</small><button onClick={()=>onFeedback(`${record.fileName} is ready for review.`)} aria-label={`More options for ${record.fileName}`}>⋮</button></div>)}</div><div className="v2-upload-actions"><Button variant="secondary" onClick={()=>addMockFile()}>＋ Add another file</Button><Button onClick={onContinue}>Continue</Button></div>
    </Card><Card className="v2-next-panel"><h2>What happens next</h2><ol><li><b>1</b><span>▤</span><strong>AI extracts strengths,<br/>needs, and goals</strong></li><li><b>2</b><span>♙</span><strong>You review and edit<br/>learner information</strong></li><li><b>3</b><span>◎</span><strong>You define the<br/>lesson goal</strong></li></ol><div className="v2-upload-complete">✓ &nbsp; {records.length} files uploaded</div></Card>
  </div></section>;
}
