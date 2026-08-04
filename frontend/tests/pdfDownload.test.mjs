import assert from "node:assert/strict";
import test from "node:test";
import {
  canStartPdfDownload,
  executePdfArtifactDownload,
  startSignedPdfDownload,
} from "../src/v2/pdfDownload.ts";

function artifact(overrides={}) {
  return {
    artifactId:"artifact-1",
    packageId:"package-1",
    packageRevision:3,
    materialRevisions:{"material-1":2},
    status:"ready",
    filename:"learner-N-482-break-request-kit.pdf",
    contentType:"application/pdf",
    sizeBytes:74819,
    pageCount:17,
    sha256:"a".repeat(64),
    downloadUrl:"https://private.example.test/signed-pdf",
    expiresAt:new Date(Date.now()+300_000).toISOString(),
    reused:false,
    ...overrides,
  };
}

test("signed URL download emits the complete visible state sequence",async()=>{
  const states=[];
  const started=[];
  const result=await executePdfArtifactDownload({
    prepareArtifact:async()=>artifact(),
    startDownload:(value)=>started.push(value),
    onState:(state)=>states.push(state),
  });

  assert.deepEqual(states.map((state)=>state.phase),[
    "preparing","ready","download_starting","downloaded",
  ]);
  assert.equal(started.length,1);
  assert.equal(started[0].filename,result.filename);
});

test("zero-byte PDF metadata is rejected before browser download",async()=>{
  const states=[];
  let downloadCalls=0;
  await assert.rejects(
    executePdfArtifactDownload({
      prepareArtifact:async()=>artifact({sizeBytes:0}),
      startDownload:()=>{downloadCalls+=1;},
      onState:(state)=>states.push(state),
    }),
    (error)=>error.code==="invalid_pdf_artifact",
  );
  assert.equal(downloadCalls,0);
  assert.equal(states.at(-1).phase,"failed");
  assert.equal(states.at(-1).retryable,true);
});

test("typed JSON API error remains actionable and retryable",async()=>{
  const states=[];
  const error=Object.assign(new Error("The current package revision is stale."),{
    code:"version_conflict",
    retryable:true,
  });
  await assert.rejects(
    executePdfArtifactDownload({
      prepareArtifact:async()=>{throw error;},
      startDownload:()=>assert.fail("download must not start"),
      onState:(state)=>states.push(state),
    }),
    (reason)=>reason.code==="version_conflict",
  );
  assert.equal(states.at(-1).message,error.message);
  assert.equal(states.at(-1).errorCode,"version_conflict");
});

test("expired signed URL is refreshed before the direct GET starts",async()=>{
  const prepared=[
    artifact({expiresAt:new Date(Date.now()-1_000).toISOString()}),
    artifact({artifactId:"artifact-1",reused:true}),
  ];
  const states=[];
  let prepareCalls=0;
  let downloaded;
  await executePdfArtifactDownload({
    prepareArtifact:async()=>prepared[prepareCalls++],
    startDownload:(value)=>{downloaded=value;},
    onState:(state)=>states.push(state),
  });
  assert.equal(prepareCalls,2);
  assert.equal(downloaded.reused,true);
  assert.ok(states.some((state)=>state.message.includes("Refreshing")));
});

test("failed preparation can be retried successfully",async()=>{
  const states=[];
  let attempts=0;
  const prepare=async()=>{
    attempts+=1;
    if(attempts===1)throw new Error("Temporary storage failure");
    return artifact();
  };
  await assert.rejects(executePdfArtifactDownload({
    prepareArtifact:prepare,startDownload:()=>{},onState:(state)=>states.push(state),
  }));
  await executePdfArtifactDownload({
    prepareArtifact:prepare,startDownload:()=>{},onState:(state)=>states.push(state),
  });
  assert.equal(attempts,2);
  assert.equal(states.at(-1).phase,"downloaded");
});

test("busy phases disable duplicate click starts",()=>{
  assert.equal(canStartPdfDownload({phase:"preparing",message:"",retryable:false}),false);
  assert.equal(canStartPdfDownload({phase:"download_starting",message:"",retryable:false}),false);
  assert.equal(canStartPdfDownload({phase:"failed",message:"",retryable:true}),true);
});

test("browser adapter uses the returned filename without a blank tab",()=>{
  const events=[];
  const anchor={
    href:"",download:"",rel:"",style:{display:""},
    click(){events.push("click");},
    remove(){events.push("remove");},
  };
  const fakeDocument={
    createElement(name){assert.equal(name,"a");return anchor;},
    body:{appendChild(value){assert.equal(value,anchor);events.push("append");}},
  };
  startSignedPdfDownload(artifact(),fakeDocument);
  assert.equal(anchor.download,"learner-N-482-break-request-kit.pdf");
  assert.equal(anchor.href,"https://private.example.test/signed-pdf");
  assert.deepEqual(events,["append","click","remove"]);
});
