package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.junit.Assert.*;

/** In-memory transport: never contacts GitHub or creates real Draft releases. */
@RunWith(AndroidJUnit4.class)
public final class DiagnosisUploaderEmulatorTest {
    static final String REPO=DiagnosisUploader.REPO;
    static class Connection extends HttpURLConnection {
        final ByteArrayOutputStream body=new ByteArrayOutputStream();
        final URL requestedUrl;
        final int response;
        final String payload;
        Connection(URL url,int status,String responseJson){
            super(url);requestedUrl=url;response=status;payload=responseJson;
        }
        @Override public void connect(){}
        @Override public void disconnect(){}
        @Override public boolean usingProxy(){return false;}
        @Override public OutputStream getOutputStream(){return body;}
        @Override public int getResponseCode(){return response;}
        @Override public InputStream getInputStream(){
            String text=payload;
            if(url.getHost().equals("uploads.github.com"))
                text="{\"id\":88,\"size\":"+body.size()+"}";
            return new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8));
        }
    }
    static final class Transport implements DiagnosisUploader.Transport {
        final List<Connection> calls=new ArrayList<>();
        String uploadBase="https://uploads.github.com/repos/"+REPO+"/releases/77/assets{?name,label}";
        int dispatchStatus=204;
        @Override public HttpURLConnection open(URL url){
            String host=url.getHost(),path=url.getPath();
            int status=201;
            String body;
            if(host.equals("api.github.com")&&path.endsWith("/releases")){
                body="{\"id\":77,\"html_url\":\"https://github.com/"+REPO+
                        "/releases/tag/draft\",\"upload_url\":\""+uploadBase+"\"}";
            }else if(host.equals("uploads.github.com")){
                body="{}";
            }else if(host.equals("api.github.com")&&path.endsWith("/dispatches")){
                status=dispatchStatus;body="{}";
            }else throw new AssertionError("Unexpected network URL: "+url);
            Connection c=new Connection(url,status,body);calls.add(c);return c;
        }
    }
    JSONObject data()throws Exception{
        return new JSONObject().put("schema",DiagnosisCollector.SCHEMA)
                .put("source_run_id",12345).put("stock_build","OS4.0.6.0.XBLCNXM")
                .put("device_write_allowed",false).put("safe_to_flash",false)
                .put("lkg_promotion",false).put("observations",new JSONObject()
                        .put("identity",new JSONObject().put("device","pandora")));
    }
    @Test public void appRequiresExplicitDraftUploadThenSeparateWorkflowDispatch()throws Exception{
        Transport fake=new Transport();
        DiagnosisUploader uploader=new DiagnosisUploader(REPO,"fake-pat-never-logged",fake);
        DiagnosisUploader.Receipt receipt=uploader.upload(data());
        assertTrue(receipt.dispatched);
        assertEquals(77,receipt.releaseId);assertEquals(88,receipt.assetId);
        assertEquals(12345,receipt.sourceRun);
        assertEquals(3,fake.calls.size());
        JSONObject draft=new JSONObject(fake.calls.get(0).body.toString(StandardCharsets.UTF_8.name()));
        assertTrue(draft.getBoolean("draft"));assertTrue(draft.getBoolean("prerelease"));
        assertEquals("dev",draft.getString("target_commitish"));
        assertEquals("api.github.com",fake.calls.get(0).requestedUrl.getHost());
        assertEquals("uploads.github.com",fake.calls.get(1).requestedUrl.getHost());
        assertEquals("diagnostic-evidence.json",fake.calls.get(1).requestedUrl.getQuery().split("=")[1]);
        JSONObject sent=new JSONObject(fake.calls.get(1).body.toString(StandardCharsets.UTF_8.name()));
        assertFalse(sent.optBoolean("safe_to_flash",true));
        assertFalse(sent.has("cmdline"));assertFalse(sent.has("module_addresses"));
        JSONObject dispatch=new JSONObject(fake.calls.get(2).body.toString(StandardCharsets.UTF_8.name()));
        assertEquals("dev",dispatch.getString("ref"));
        assertEquals("12345",dispatch.getJSONObject("inputs").getString("source_run_id"));
        assertEquals(receipt.sha,dispatch.getJSONObject("inputs").getString("evidence_sha256"));
        for(Connection c:fake.calls)assertFalse(c.requestedUrl.toString().contains("fake-pat"));
    }
    @Test public void unexpectedUploadHostIsRefusedBeforeSendingEvidence()throws Exception{
        Transport fake=new Transport();fake.uploadBase="https://example.org/not-github/{?name,label}";
        try{new DiagnosisUploader(REPO,"fake-pat",fake).upload(data());fail();}
        catch(IOException expected){assertTrue(expected.getMessage().contains("地址"));}
        assertEquals(1,fake.calls.size());
    }
    @Test public void notificationFailureDoesNotCauseSecondUpload()throws Exception{
        Transport fake=new Transport();fake.dispatchStatus=500;
        DiagnosisUploader.Receipt pending=new DiagnosisUploader(REPO,"fake-pat",fake).upload(data());
        assertFalse(pending.dispatched);
        assertEquals(3,fake.calls.size());
        fake.dispatchStatus=204;
        new DiagnosisUploader(REPO,"fake-pat",fake).notifyIntake(pending);
        assertEquals(4,fake.calls.size());
        assertEquals("api.github.com",fake.calls.get(3).requestedUrl.getHost());
        assertTrue(fake.calls.get(3).requestedUrl.getPath().contains(DiagnosisUploader.WORKFLOW));
    }
    @Test public void appRejectsNonReadOnlyReportsAndWrongRepo()throws Exception{
        Transport fake=new Transport();
        try{new DiagnosisUploader("other/repo","fake-pat",fake);fail();}
        catch(IllegalArgumentException expected){}
        JSONObject data=data().put("safe_to_flash",true);
        try{new DiagnosisUploader(REPO,"fake-pat",fake).upload(data);fail();}
        catch(IOException expected){}
        assertTrue(fake.calls.isEmpty());
    }
    /** A real interrupted-upload state machine, with no external GitHub writes. */
    static final class RecoveryTransport implements DiagnosisUploader.Transport {
        boolean draftCreated,assetPresent,failFirstAsset=true,wrongDraft,wrongDigest;
        int draftAttempts,listReads,assetAttempts,dispatches,assetLength;
        String savedTag="",savedBody="",assetSha="";
        static String sha(byte[] data)throws Exception {
            StringBuilder hex=new StringBuilder();
            for(byte b:MessageDigest.getInstance("SHA-256").digest(data))
                hex.append(String.format(Locale.ROOT,"%02x",b&255));
            return hex.toString();
        }
        JSONObject release()throws Exception {
            JSONArray assets=new JSONArray();
            if(assetPresent)assets.put(new JSONObject()
                    .put("id",88).put("name","diagnostic-evidence.json")
                    .put("size",assetLength).put("state","uploaded")
                    .put("digest","sha256:"+(wrongDigest?"f".repeat(64):assetSha)));
            return new JSONObject().put("id",77).put("tag_name",savedTag)
                    .put("body",wrongDraft?"tampered":savedBody)
                    .put("draft",true).put("prerelease",true).put("assets",assets)
                    .put("upload_url","https://uploads.github.com/repos/"+REPO+
                            "/releases/77/assets{?name,label}")
                    .put("html_url","https://github.com/"+REPO+"/releases/edit/"+savedTag);
        }
        @Override public HttpURLConnection open(URL url)throws Exception {
            String path=url.getPath();
            if(url.getHost().equals("api.github.com")&&path.endsWith("/releases")){
                // The first POST creates a Draft, later POSTs hit GitHub's 422.
                return new Connection(url,201,"{\"id\":77,\"upload_url\":\"https://uploads.github.com/repos/"+
                        REPO+"/releases/77/assets{?name,label}\"}"){
                    @Override public int getResponseCode()throws IOException {
                        draftAttempts++;
                        if(draftCreated)return 422;
                        try{
                            JSONObject input=new JSONObject(body.toString(StandardCharsets.UTF_8.name()));
                            savedTag=input.getString("tag_name");
                            savedBody=input.getString("body");
                        }catch(Exception ex){throw new IOException(ex);}
                        draftCreated=true;
                        return 201;
                    }
                };
            }
            if(url.getHost().equals("api.github.com")&&path.endsWith("/releases")
                    &&url.getQuery()!=null){
                listReads++;
                return new Connection(url,200,new JSONArray().put(release()).toString());
            }
            if(url.getHost().equals("uploads.github.com")){
                return new Connection(url,201,"{}"){
                    @Override public int getResponseCode()throws IOException {
                        assetAttempts++;
                        if(failFirstAsset){failFirstAsset=false;return 503;}
                        try{assetSha=sha(body.toByteArray());}catch(Exception ex){throw new IOException(ex);}
                        assetLength=body.size();
                        assetPresent=true;
                        return 201;
                    }
                };
            }
            if(url.getHost().equals("api.github.com")&&path.endsWith("/dispatches")){
                return new Connection(url,204,"{}"){
                    @Override public int getResponseCode(){dispatches++;return 204;}
                };
            }
            throw new IOException("Unexpected URL "+url);
        }
    }
    @Test public void retryAfterInterruptedUploadReusesExactlyOneDraftAndAsset()throws Exception{
        RecoveryTransport fake=new RecoveryTransport();
        DiagnosisUploader uploader=new DiagnosisUploader(REPO,"test-token",fake);
        JSONObject evidence=data();
        try{uploader.upload(evidence);fail("Expected simulated HTTP 503");}
        catch(IOException expected){assertTrue(expected.getMessage().contains("HTTP 503"));}
        assertTrue(fake.draftCreated);
        assertFalse(fake.assetPresent);
        assertEquals(0,fake.dispatches);
        DiagnosisUploader.Receipt completed=uploader.upload(evidence);
        assertTrue(completed.dispatched);
        assertEquals(77,completed.releaseId);
        assertEquals(88,completed.assetId);
        assertEquals(2,fake.draftAttempts);
        assertEquals(1,fake.listReads);
        assertEquals(2,fake.assetAttempts);
        // A crash after successful upload but before storing the receipt must
        // not re-upload an identical asset.
        DiagnosisUploader.Receipt restored=uploader.upload(evidence);
        assertTrue(restored.dispatched);
        assertEquals(completed.sha,restored.sha);
        assertEquals(completed.tag,restored.tag);
        assertEquals(completed.assetId,restored.assetId);
        assertEquals(3,fake.draftAttempts);
        assertEquals(2,fake.listReads);
        assertEquals(2,fake.assetAttempts);
    }
    @Test public void conflictingDraftOrAssetDigestStopsWithoutReplacingEvidence()throws Exception{
        RecoveryTransport fake=new RecoveryTransport();
        DiagnosisUploader uploader=new DiagnosisUploader(REPO,"test-token",fake);
        JSONObject evidence=data();
        try{uploader.upload(evidence);fail();}
        catch(IOException expected){}
        fake.wrongDraft=true;
        try{uploader.upload(evidence);fail("Unexpectedly reused tampered Draft");}
        catch(IOException expected){assertTrue(expected.getMessage().contains("身份不一致"));}
        assertEquals(1,fake.assetAttempts);
        fake.wrongDraft=false;
        uploader.upload(evidence);
        fake.wrongDigest=true;
        try{uploader.upload(evidence);fail("Unexpectedly accepted tampered asset");}
        catch(IOException expected){assertTrue(expected.getMessage().contains("摘要不一致"));}
        assertEquals(2,fake.assetAttempts);
    }

}
