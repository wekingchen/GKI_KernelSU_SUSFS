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

@RunWith(AndroidJUnit4.class)
public class StageEmulatorTest {
    static final String SHA="a".repeat(64),HEAD="b".repeat(40),BUILD="OS4.0.6.0.XBLCNXM";
    JSONObject run()throws Exception{return new JSONObject().put("id",55).put("head_branch","dev").put("head_sha",HEAD)
        .put("event","workflow_dispatch").put("path",".github/workflows/"+StageClient.WORKFLOW).put("status","completed").put("conclusion","success");}
    JSONObject fixed()throws Exception{return new JSONObject().put("tag_name","pandora-os4-stock-input").put("draft",false)
        .put("assets",new JSONArray().put(new JSONObject().put("id",77).put("name","xm.zip").put("digest","sha256:"+SHA)));}
    JSONObject stage(String name)throws Exception{return new JSONObject().put("schema","pandora-os4-stage-v1")
        .put("repository",StageClient.REPO).put("device","pandora").put("producer_run_id",55).put("producer_head_sha",HEAD)
        .put("build",BUILD).put("stock_asset_id",77).put("stock_input_sha256",SHA).put("stage",name).put("safe_to_flash",false)
        .put("source_run_id",12).put("source_head_sha",HEAD).put("release_assets",new JSONArray());}
    @Test public void allStageTitlesAndNextActionsRemainExplicit()throws Exception{
        Set<String> titles=new HashSet<>();
        for(String name:StageClient.STAGES){StageClient.State s=new StageClient.State(stage(name));assertFalse(s.title().isEmpty());assertFalse(s.next().isEmpty());titles.add(s.title());}
        assertEquals(8,titles.size());
        assertTrue(new StageClient.State(stage("WAITING_HUMAN")).next().contains("电脑"));
        assertTrue(new StageClient.State(stage("CUSTOM_UNVERIFIED")).title().contains("待验证"));
    }
    @Test public void verifiedLkgGenerationAndSnapshotTimeArePresentedWithoutTechnicalIds()throws Exception{
        JSONObject lkg=stage("LKG_ARCHIVED");
        lkg.put("detail","本次 OTA 检测可能仅为 NOOP");
        for(int i=0;i<3;i++)lkg.getJSONArray("release_assets").put(
                new JSONObject().put("tag","pandora-os4-lkg-gen4").put("id",100+i));
        StageClient.State current=new StageClient.State(lkg,"2026-11-02T03:59:10Z");
        assertEquals("已归档稳定内核 · Gen 4",current.title());
        assertEquals("Gen 4",current.lkgGeneration());
        assertFalse(current.friendlyDetail().contains("NOOP"));
        assertTrue(current.friendlyDetail().contains("不代表"));
        assertTrue(current.verifiedAt.matches("[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}"));
        assertFalse(current.title().contains("100"));
        assertTrue(current.technicalDetails().contains("输入 Asset #77"));
        JSONObject different=stage("LKG_ARCHIVED");
        assertEquals("稳定 LKG 已长期归档",new StageClient.State(different).title());
        assertEquals("未取得",new StageClient.State(different,"not-a-time").verifiedAt);
        JSONObject noop=stage("NO_NEW_OTA").put("detail","仅为 NOOP");
        assertTrue(new StageClient.State(noop).friendlyDetail().contains("无需重复处理"));
    }
    @Test public void noopEnvelopeCannotClaimAnyOtherStageWithoutEvidence()throws Exception{
        StageClient.validateEnvelope(stage("NO_NEW_OTA"),run(),fixed());
        for(String name:StageClient.STAGES){if(name.equals("NO_NEW_OTA"))continue;reject(stage(name),run(),fixed());}
    }
    void reject(JSONObject j,JSONObject r,JSONObject f)throws Exception{
        try{StageClient.validateEnvelope(j,r,f);fail("invalid snapshot accepted");}catch(IOException expected){}
    }
    @Test public void mismatchedProducerCommitRepositoryBuildOrUnknownStageIsRejected()throws Exception{
        for(String[] mutation:new String[][]{{"repository","other/repo"},{"producer_head_sha","c".repeat(40)},
                {"producer_run_id","56"},{"stock_asset_id","78"},{"stock_input_sha256","d".repeat(64)},
                {"stage","SUCCESS"},{"build","wrong"},{"device","other"},{"safe_to_flash","true"}}){
            JSONObject j=stage("NO_NEW_OTA");j.put(mutation[0],mutation[1]);reject(j,run(),fixed());
        }
    }
    @Test public void doubleInputMissingDigestAndStaleInputFailClosed()throws Exception{
        JSONObject f=fixed();f.getJSONArray("assets").put(new JSONObject().put("id",78).put("name","new-xm.zip").put("digest","sha256:"+SHA));reject(stage("NO_NEW_OTA"),run(),f);
        f=fixed();f.getJSONArray("assets").getJSONObject(0).remove("digest");reject(stage("NO_NEW_OTA"),run(),f);
        f=fixed();f.getJSONArray("assets").getJSONObject(0).put("digest","sha256:"+"f".repeat(64));reject(stage("NO_NEW_OTA"),run(),f);
    }
    @Test public void successOnWrongWorkflowBranchOrUnfinishedRunIsRejected()throws Exception{
        for(String[] mutation:new String[][]{{"head_branch","fix/test"},{"path",".github/workflows/other.yml"},{"status","in_progress"},{"event","pull_request"},{"conclusion","failure"}}){
            JSONObject r=run();r.put(mutation[0],mutation[1]);reject(stage("NO_NEW_OTA"),r,fixed());
        }
    }
    static class Connection extends HttpURLConnection {
        final byte[] bytes;Connection(URL url,byte[] bytes){super(url);this.bytes=bytes;}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public int getResponseCode(){return 200;}public InputStream getInputStream(){return new ByteArrayInputStream(bytes);}
    }
    byte[] zip(JSONObject j)throws Exception{
        ByteArrayOutputStream b=new ByteArrayOutputStream();try(ZipOutputStream z=new ZipOutputStream(b)){z.putNextEntry(new ZipEntry("os4-stage.json"));z.write(j.toString().getBytes(StandardCharsets.UTF_8));z.closeEntry();}return b.toByteArray();
    }
    @Test public void liveStatusFetchIsReadOnlyAndValidatesSourceRun()throws Exception{
        Map<String,byte[]> responses=new HashMap<>();
        responses.put("actions/workflows/"+StageClient.WORKFLOW+"/runs?branch=dev&per_page=1",new JSONObject().put("workflow_runs",new JSONArray().put(run())).toString().getBytes(StandardCharsets.UTF_8));
        responses.put("actions/runs/55/artifacts?per_page=100",new JSONObject().put("artifacts",new JSONArray().put(new JSONObject().put("id",88).put("name","pandora-OTA-STAGE-55").put("expired",false))).toString().getBytes(StandardCharsets.UTF_8));
        responses.put("actions/artifacts/88/zip",zip(stage("NO_NEW_OTA")));
        responses.put("releases/tags/pandora-os4-stock-input",fixed().toString().getBytes(StandardCharsets.UTF_8));
        JSONObject source=run().put("id",12).put("path",".github/workflows/"+FeedbackClient.SOURCE);
        responses.put("actions/runs/12",source.toString().getBytes(StandardCharsets.UTF_8));
        List<Connection> connections=new ArrayList<>();
        StageClient client=new StageClient(StageClient.REPO,"test-token",url->{
            String path=url.toString().substring((StageClient.API+"/").length());
            byte[] bytes=responses.get(path);if(bytes==null)throw new IOException("unexpected endpoint "+path);
            Connection c=new Connection(url,bytes);connections.add(c);return c;
        });
        assertEquals("NO_NEW_OTA",client.latest().stage);
        for(Connection c:connections)assertEquals("GET",c.getRequestMethod());
        source.put("head_branch","experiment");responses.put("actions/runs/12",source.toString().getBytes(StandardCharsets.UTF_8));
        try{client.latest();fail();}catch(IOException expected){assertTrue(expected.getMessage().contains("来源"));}
    }
}
