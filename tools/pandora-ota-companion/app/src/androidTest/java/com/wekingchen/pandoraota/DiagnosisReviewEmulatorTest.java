package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;
import static org.junit.Assert.*;

/** Offline GitHub-API simulation: review is never inferred from a green run alone. */
@RunWith(AndroidJUnit4.class)
public final class DiagnosisReviewEmulatorTest {
    private static final String REPO=StageClient.REPO;
    private static final String BUILD="OS4.0.6.0.XBLCNXM";
    private static final String STOCK="a".repeat(64);
    private static final String SHA="b".repeat(64);
    private static final String HEAD="c".repeat(40);
    private static final int RUN=12345;
    private static final int REVIEW=45678;
    private final DiagnosisUploader.Receipt receipt=new DiagnosisUploader.Receipt(
            77,88,RUN,SHA,"","pandora-ota-diagnostic-12345-"+"d".repeat(32),true);

    DiagnosisClient.Task task()throws Exception{
        return new DiagnosisClient.Task(new JSONObject()
                .put("source_run_id",RUN).put("source_head_sha",HEAD)
                .put("stock_build",BUILD).put("stock_input_sha256",STOCK)
                .put("candidate_commit","e".repeat(40))
                .put("checks",new JSONArray().put(new JSONObject().put("id","binder_runtime")))
                .put("issues",new JSONArray().put(new JSONObject().put("code",DiagnosisClient.RUST))));
    }
    static final class Response extends HttpURLConnection{
        private final byte[] content;
        Response(URL url,byte[] body){super(url);content=body;}
        public void connect(){}
        public void disconnect(){}
        public boolean usingProxy(){return false;}
        public int getResponseCode(){return 200;}
        public InputStream getInputStream(){return new ByteArrayInputStream(content);}
    }
    static class Mock implements FeedbackClient.Transport {
        String runStatus="completed",conclusion="success",digest=SHA;
        boolean artifactPresent=true;
        final List<String> paths=new ArrayList<>();
        byte[] zip()throws Exception{
            JSONObject review=new JSONObject().put("schema","pandora-ota-diagnostic-review-v1")
                    .put("review","REVIEW_REQUIRED").put("source_run_id",RUN)
                    .put("stock_build",BUILD).put("stock_input_sha256",STOCK)
                    .put("payload_sha256",digest)
                    .put("safe_to_flash",false).put("oem_gate_unlocked",false)
                    .put("lkg_promotion",false);
            ByteArrayOutputStream buffer=new ByteArrayOutputStream();
            try(ZipOutputStream zip=new ZipOutputStream(buffer)){
                JSONObject plan=new JSONObject().put("schema","pandora-ota-v2-recovery-plan-v1")
                        .put("source_run_id",RUN).put("stock_build",BUILD)
                        .put("stock_input_sha256",STOCK).put("evidence_sha256",SHA)
                        .put("automatic_rebuild_authorized",false)
                        .put("fastboot_boot_authorized",false).put("lkg_promotion_authorized",false)
                        .put("actions",new JSONArray().put(
                                new JSONObject().put("title","先核对 vendor_boot 提供者")));
                for(String name:new String[]{"diagnostic-review.json","diagnostic-evidence.json",
                        "diagnostic-recovery-plan.json"}){
                    zip.putNextEntry(new ZipEntry(name));
                    zip.write((name.equals("diagnostic-review.json")?review.toString():
                            name.equals("diagnostic-recovery-plan.json")?plan.toString():"{}")
                            .getBytes(StandardCharsets.UTF_8));
                    zip.closeEntry();
                }
            }
            return buffer.toByteArray();
        }
        @Override public HttpURLConnection open(URL url)throws Exception{
            String path=url.toString().substring((StageClient.API+"/").length());
            paths.add(path);
            byte[] result;
            if(path.startsWith("actions/workflows/")){
                JSONObject run=new JSONObject().put("id",REVIEW)
                        .put("head_sha",HEAD).put("head_branch","dev")
                        .put("event","workflow_dispatch")
                        .put("path",".github/workflows/"+DiagnosisReviewClient.WORKFLOW)
                        .put("status",runStatus).put("conclusion",conclusion)
                        .put("display_title",DiagnosisReviewClient.title(new DiagnosisUploader.Receipt(
                                77,88,RUN,SHA,"","",true)));
                result=new JSONObject().put("workflow_runs",new JSONArray().put(run))
                        .toString().getBytes(StandardCharsets.UTF_8);
            }else if(path.equals("actions/runs/"+REVIEW+"/artifacts?per_page=100")){
                JSONArray artifacts=new JSONArray();
                if(artifactPresent)artifacts.put(new JSONObject().put("id",444)
                        .put("expired",false)
                        .put("name","pandora-OTA-V2-DIAGNOSTIC-REVIEW-"+RUN+"-"+REVIEW));
                result=new JSONObject().put("artifacts",artifacts)
                        .toString().getBytes(StandardCharsets.UTF_8);
            }else if(path.equals("actions/artifacts/444/zip"))result=zip();
            else throw new IOException("Unexpected network endpoint "+path);
            return new Response(url,result);
        }
    }
    @Test public void pendingRunningAndFailedAreNotConfusedWithReviewSuccess()throws Exception{
        Mock stub=new Mock();DiagnosisReviewClient client=new DiagnosisReviewClient(REPO,"pat",stub);
        stub.runStatus="queued";
        assertEquals("QUEUED",client.latest(receipt,task()).state);
        stub.runStatus="in_progress";
        assertEquals("RUNNING",client.latest(receipt,task()).state);
        stub.runStatus="completed";stub.conclusion="failure";
        assertEquals("FAILED",client.latest(receipt,task()).state);
        assertFalse(stub.paths.stream().anyMatch(p->p.contains("artifacts?")));
    }
    @Test public void successRequiresExactMatchingReviewArtifact()throws Exception{
        Mock stub=new Mock();
        DiagnosisReviewClient client=new DiagnosisReviewClient(REPO,"pat",stub);
        DiagnosisReviewClient.Status state=client.latest(receipt,task());
        assertEquals("REVIEW_REQUIRED",state.state);
        assertEquals(REVIEW,state.runId);
        assertTrue(state.description.contains("ABI"));
        assertTrue(state.description.contains("先核对 vendor_boot 提供者"));
        assertTrue(stub.paths.contains("actions/artifacts/444/zip"));
        stub.digest="f".repeat(64);
        try{client.latest(receipt,task());fail("Wrong upload proof accepted");}
        catch(IOException expected){assertTrue(expected.getMessage().contains("不一致"));}
    }
    @Test public void greenRunWithoutProofIsNotAccepted()throws Exception{
        Mock stub=new Mock();stub.artifactPresent=false;
        try{new DiagnosisReviewClient(REPO,"pat",stub).latest(receipt,task());fail();}
        catch(IOException expected){assertTrue(expected.getMessage().contains("缺失"));}
    }
    @Test public void failedOrUnconfirmedDispatchCannotClaimReviewed()throws Exception{
        DiagnosisUploader.Receipt pending=new DiagnosisUploader.Receipt(
                77,88,RUN,SHA,"","",false);
        Mock stub=new Mock();
        try{new DiagnosisReviewClient(REPO,"pat",stub).latest(pending,task());fail();}
        catch(IOException expected){assertTrue(expected.getMessage().contains("未确认"));}
        assertTrue(stub.paths.isEmpty());
    }
}
