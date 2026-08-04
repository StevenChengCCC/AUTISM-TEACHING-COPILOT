import type { ClassroomRunSheet } from "../classroomRunSheetModel";

export function ClassroomRunSheetPreview({ sheet }: { sheet: ClassroomRunSheet }) {
  return <article className="v2-run-sheet-preview" aria-labelledby="classroom-run-sheet-title">
    <header><div><small>INCLUDED IN THE COMPLETE PDF</small><h2 id="classroom-run-sheet-title">Classroom Run Sheet</h2></div><span>{sheet.totalDuration}</span></header>
    <dl className="v2-run-sheet-glance"><div><dt>Learner code</dt><dd>{sheet.learnerCode}</dd></div><div><dt>Goal</dt><dd>{sheet.goal}</dd></div><div><dt>Communication</dt><dd>{sheet.communicationModes.join(", ")}</dd></div><div><dt>Success</dt><dd>{sheet.successCriterion}</dd></div></dl>
    <div className="v2-run-sheet-columns"><section><h3>Before class</h3>{sheet.beforeClassChecklist.map((item)=><p key={item}>□ {item}</p>)}</section><section><h3>Materials needed</h3>{sheet.materialsNeeded.map((item)=><p key={item}>• {item}</p>)}</section></div>
    <section className="v2-run-sheet-flow"><h3>Timed lesson flow</h3>{sheet.steps.map((step,index)=><div key={step.id}><b>{index+1}</b><span><strong>{step.title} · {step.duration}</strong><small>{step.teacherScript&&<><b>Say:</b> {step.teacherScript} · </>}<b>Do:</b> {step.teacherAction}</small><small><b>Look for:</b> {step.expectedLearnerResponse} · <b>Wait:</b> {step.waitTime}</small><small><b>Prompt/fade:</b> {step.promptAction}</small><small><b>Reinforce/correct:</b> {step.reinforcementAction} · {step.errorCorrectionAction}</small><small><b>Record:</b> {step.dataToRecord.join(", ")} · <b>Transition:</b> {step.transitionCue}</small>{step.breakOption&&<small><b>Break:</b> {step.breakOption}</small>}</span></div>)}</section>
    <div className="v2-run-sheet-columns"><section><h3>In-the-moment data</h3>{sheet.dataReminder.map((item)=><p key={item}>• {item}</p>)}</section><section><h3>Two-minute closeout</h3>{sheet.closeout.map((item)=><p key={item}>□ {item}</p>)}</section></div>
    <footer><b>{sheet.teacherJudgmentNote}</b></footer>
  </article>;
}
