import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {deleteLocalStudyEvents,readLocalStudyEvents,recordLocalStudyEvent,setTelemetryOptIn,telemetryOptedIn,validateStudyEvent} from "../src/v2/usabilityTelemetry.ts";

function memoryStorage(){const values=new Map();return {getItem:(key)=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:(key)=>values.delete(key)};}
function event(changes={}){return {schemaVersion:"usability-event-v1",eventId:"event-1",participantId:"P-001",syntheticCaseId:"SYN-N482-E2E",eventName:"task_completed",taskName:"record_valid_trial",occurredAt:"2026-08-04T08:00:00Z",durationMs:12000,interactionCount:3,outcome:"success",...changes};}

test("study measurement is visibly opt-in and local only",()=>{const storage=memoryStorage();assert.equal(telemetryOptedIn(storage),false);assert.throws(()=>recordLocalStudyEvent(event(),storage),/disabled/);setTelemetryOptIn(true,storage);assert.equal(recordLocalStudyEvent(event(),storage).length,1);assert.equal(readLocalStudyEvents(storage)[0].participantId,"P-001");deleteLocalStudyEvents(storage);assert.deepEqual(readLocalStudyEvents(storage),[]);});
test("privacy schema rejects direct IDs, real cases, free text, and extra fields",()=>{assert.throws(()=>validateStudyEvent(event({participantId:"Learner N-482"})));assert.throws(()=>validateStudyEvent(event({syntheticCaseId:"REAL-001"})));assert.throws(()=>validateStudyEvent(event({errorCategory:"teacher wrote a note"})));assert.throws(()=>validateStudyEvent({...event(),lessonContent:"private"}));});
test("production bundle cannot render the development-only study panel",()=>{const app=readFileSync(new URL("../src/v2/pages/StartNewLessonPage.tsx",import.meta.url),"utf8");assert.match(app,/import\.meta\.env\.DEV&&<UsabilityStudyPanel/);const panel=readFileSync(new URL("../src/v2/components/UsabilityStudyPanel.tsx",import.meta.url),"utf8");assert.match(panel,/Never records learner or lesson content/);assert.match(panel,/I opt in/);});
