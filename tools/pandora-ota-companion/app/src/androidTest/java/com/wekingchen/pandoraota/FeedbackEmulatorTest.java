package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import android.app.Activity;
import android.content.*;
import android.widget.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.Field;
import java.util.*;
import java.util.zip.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class FeedbackEmulatorTest {
    static final String REPO="wekingchen/GKI_KernelSU_SUSFS", BUILD="OS4.0.6.0.XBLCNXM", UNAME="6.12.80-android16-6-test-4k", SHA="a".repeat(64), ID="b".repeat(32);
    DeviceEvidence evidence(){return new DeviceEvidence("pandora",BUILD,"1",UNAME,"zram 1 0 - Live 0x0\n","",100);}
    JSONObject form(String result,DeviceEvidence e,boolean recovered,boolean image,boolean desktop,boolean modules)throws Exception{
        return FeedbackForm.inputs(123,SHA,result,e,BUILD,UNAME,recovered,image,desktop,modules,"实测备注",ID);
    }
    @Test public void passPayloadMapsExactlyToOriginalWorkflowAndKeepsHumanConfirmation()throws Exception{
        JSONObject j=form("pass",evidence(),false,true,true,true);
        assertEquals(9,j.length());assertEquals("123",j.getString("source_run_id"));assertEquals(SHA,j.getString("tested_boot_sha256"));
        assertEquals(BUILD,j.getString("observed_build"));assertEquals(UNAME,j.getString("observed_uname"));
        assertEquals("true",j.getString("confirmed_boot_completed"));assertEquals("true",j.getString("confirmed_modules"));
        assertEquals(ID,j.getString("client_request_id"));
    }
    @Test public void automaticEvidenceCannotSupplyMissingHumanAttestations()throws Exception{
        for(boolean[] confirms:new boolean[][]{{false,true,true},{true,false,true},{true,true,false}}){
            try{form("pass",evidence(),false,confirms[0],confirms[1],confirms[2]);fail();}catch(IllegalArgumentException expected){}
        }
    }
    @Test public void recoveredFailureBlanksAllRuntimeEvidenceAndConfirmationFlags()throws Exception{
        JSONObject j=form("fail",evidence(),true,true,true,true);
        assertEquals("",j.getString("observed_build"));assertEquals("",j.getString("observed_uname"));
        assertEquals("false",j.getString("confirmed_boot_completed"));assertEquals("false",j.getString("confirmed_modules"));
        try{form("pass",evidence(),true,true,true,true);fail();}catch(IllegalArgumentException expected){}
    }
    @Test public void wrongDeviceIncompleteBootAndMismatchedBuildCannotPass()throws Exception{
        for(DeviceEvidence e:Arrays.asList(new DeviceEvidence("other",BUILD,"1",UNAME,"","",1),
                new DeviceEvidence("pandora",BUILD,"0",UNAME,"","",1),new DeviceEvidence("pandora","OS4.0.7.0.XBLCNXM","1",UNAME,"","",1),
                new DeviceEvidence("pandora",BUILD,"1","6.12.80-android16-6-other-4k","","",1))){
            try{form("pass",e,false,true,true,true);fail();}catch(IllegalArgumentException expected){}
        }
    }
    @Test public void normalFailureMayLeaveFunctionalConfirmationUnchecked()throws Exception{
        JSONObject j=form("fail",evidence(),false,true,false,false);assertEquals("false",j.getString("confirmed_modules"));assertEquals(BUILD,j.getString("observed_build"));
    }
    @Test public void fiveChecksAreReadOnlyAndRootIsOnlyFallbackForModules(){
        List<String> calls=new ArrayList<>();DeviceEvidence e=DeviceEvidence.collect(name->{calls.add(name);if(name.equals("modules"))throw new IOException("denied");
            switch(name){case"device":return"pandora";case"build":return BUILD;case"boot":return"1";case"uname":return UNAME;default:return"zram 1 0 - Live 0x0";}});
        assertEquals(Arrays.asList("device","build","boot","uname","modules","root_modules"),calls);assertTrue(e.bootReady());assertTrue(e.moduleError.isEmpty());
    }
    @Test public void unavailableModulesNeverBecomeSuccessfulModuleCheck(){
        DeviceEvidence e=DeviceEvidence.collect(name->{if(name.contains("modules"))throw new IOException("denied");return"";});
        assertTrue(e.modules.isEmpty());assertFalse(e.moduleError.isEmpty());assertFalse(e.bootReady());
    }
    JSONObject manifest()throws Exception{return new JSONObject().put("schema","pandora-mobile-feedback-v1").put("repository",REPO).put("source_run_id",123)
            .put("source_head_sha","c".repeat(40)).put("device","pandora").put("build",BUILD).put("expected_uname",UNAME).put("tested_boot_sha256",SHA)
            .put("filename","pandora-"+BUILD+"-UNVERIFIED-FASTBOOT-BOOT-ONLY.img").put("eligible_for_fastboot_boot",true);}
    @Test public void sidecarMustMatchRunCommitBuildAndImageIdentity()throws Exception{
        JSONObject j=manifest();assertEquals(SHA,FeedbackClient.parseManifest(j,123,BUILD,"c".repeat(40),REPO).sha);
        for(String key:Arrays.asList("repository","source_head_sha","build","device","tested_boot_sha256","filename")){
            JSONObject bad=new JSONObject(j.toString()).put(key,"wrong");
            try{FeedbackClient.parseManifest(bad,123,BUILD,"c".repeat(40),REPO);fail(key);}catch(IOException expected){}
        }
    }
    static class Fake implements FeedbackClient.Transport{
        final List<HttpURLConnection> connections=new ArrayList<>();
        final List<String> calls=new ArrayList<>();JSONObject posted;int dispatchStatus=204;boolean offline=false, foreignRun=false, noManifest=false;byte[] zip;
        Fake(byte[] zip){this.zip=zip;}
        public HttpURLConnection open(URL url)throws Exception{
            if(offline)throw new IOException("timeout");
            HttpURLConnection c=new HttpURLConnection(url){
                final ByteArrayOutputStream out=new ByteArrayOutputStream();
                public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
                public OutputStream getOutputStream(){return out;}
                public int getResponseCode()throws IOException{
                    calls.add(method+" "+url.getPath());
                    if(url.getHost().endsWith("blob.core.windows.net")){assertNull(getRequestProperty("Authorization"));return 200;}
                    assertEquals("Bearer synthetic",getRequestProperty("Authorization"));
                    if(url.getPath().endsWith("/dispatches")){try{posted=new JSONObject(out.toString());}catch(Exception e){throw new IOException(e);}return dispatchStatus;}
                    if(url.getPath().endsWith("/zip"))return 302;return 200;
                }
                public String getHeaderField(String name){return name.equals("Location")?"https://synthetic.blob.core.windows.net/signed/test.zip":null;}
                public InputStream getInputStream(){
                    if(url.getHost().endsWith("blob.core.windows.net"))return new ByteArrayInputStream(zip);
                    String body="{}",source="{\"id\":123,\"head_branch\":\"dev\",\"status\":\"completed\",\"conclusion\":\"success\",\"event\":\"workflow_dispatch\",\"head_sha\":\""+"c".repeat(40)+"\",\"path\":\".github/workflows/"+FeedbackClient.SOURCE+"\"}";
                    if(url.getPath().endsWith("/artifacts"))body="{\"artifacts\":[{\"name\":\"pandora-OTA-OEM-ABI-TESTBOOT-"+BUILD+"-123\"},{\"name\":\"pandora-OTA-UNVERIFIED-GKI-"+BUILD+"-123\"}"
                            +(noManifest?"":",{\"id\":555,\"name\":\"pandora-OTA-MOBILE-FEEDBACK-"+BUILD+"-123\"}")+"]}";
                    else if(url.getPath().endsWith("/runs/123"))body=source;
                    else if(url.getPath().endsWith("/runs"))body="{\"workflow_runs\":[{\"id\":777,\"head_branch\":\""+(foreignRun?"other":"dev")+"\",\"event\":\"workflow_dispatch\",\"path\":\".github/workflows/"+FeedbackClient.WORKFLOW+"\",\"display_title\":\""+FeedbackClient.TITLE+ID+"\"}]}";
                    return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
                }
            };connections.add(c);return c;
        }
    }
    byte[] archive()throws Exception{
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(ZipOutputStream z=new ZipOutputStream(bytes)){z.putNextEntry(new ZipEntry("mobile-test-feedback.json"));z.write(manifest().toString().getBytes(StandardCharsets.UTF_8));z.closeEntry();}return bytes.toByteArray();
    }
    @Test public void candidateDownloadsOnlyTinyManifestAndNeverForwardsPatToBlobStorage()throws Exception{
        Fake f=new Fake(archive());FeedbackClient.Candidate c=new FeedbackClient(REPO,"synthetic",f).candidate(123,true);
        assertEquals(SHA,c.sha);assertEquals(4,f.connections.size());
        for(String call:f.calls)assertFalse(call.contains(".img"));
    }
    @Test public void legacyCandidateRequiresManualShaRatherThanInventedValue()throws Exception{
        Fake f=new Fake(archive());f.noManifest=true;FeedbackClient.Candidate c=new FeedbackClient(REPO,"synthetic",f).candidate(123,true);
        assertEquals("",c.sha);assertEquals(2,f.connections.size());
    }
    @Test public void submissionUsesOriginalWorkflowOnDevWithExactInputs()throws Exception{
        Fake f=new Fake(archive());JSONObject inputs=form("pass",evidence(),false,true,true,true);
        new FeedbackClient(REPO,"synthetic",f).submit(inputs);
        assertEquals("dev",f.posted.getString("ref"));assertEquals(inputs.toString(),f.posted.getJSONObject("inputs").toString());
        assertEquals(Collections.singletonList("POST /repos/"+REPO+"/actions/workflows/"+FeedbackClient.WORKFLOW+"/dispatches"),f.calls);
    }
    @Test public void dispatchPermissionFailureIsExplicitAndDoesNotRetry()throws Exception{
        Fake f=new Fake(archive());f.dispatchStatus=403;
        try{new FeedbackClient(REPO,"synthetic",f).submit(form("pass",evidence(),false,true,true,true));fail();}
        catch(FeedbackClient.ApiException e){assertEquals(403,e.status);assertTrue(e.getMessage().contains("Actions"));}
        assertEquals(1,f.calls.size());
    }
    @Test public void onlyExactRequestAndTrustedBranchCanMatchFeedbackRun()throws Exception{
        Fake f=new Fake(archive());FeedbackClient c=new FeedbackClient(REPO,"synthetic",f);
        assertEquals(777,c.findRun(ID).getLong("id"));assertNull(c.findRun("d".repeat(32)));f.foreignRun=true;assertNull(c.findRun(ID));
    }
    @Test public void dispatchJournalSurvivesReopenWithoutResending()throws Exception{
        Context ctx=InstrumentationRegistry.getInstrumentation().getTargetContext();SharedPreferences raw=ctx.getSharedPreferences("boot_feedback_v1",0);
        Map<String,?> backup=raw.getAll();raw.edit().clear().commit();
        try{FeedbackStore s=new FeedbackStore(ctx);s.submission(new JSONObject().put("request_id",ID).put("state","响应待核对").put("terminal",false));
            FeedbackStore reopened=new FeedbackStore(ctx);assertEquals(ID,reopened.submission().getString("request_id"));assertFalse(reopened.submission().getBoolean("terminal"));assertEquals(1,reopened.history().length());
            s.submission(new JSONObject().put("request_id",ID).put("terminal",true));assertEquals(1,s.history().length());
        }finally{SharedPreferences.Editor e=raw.edit().clear();for(Map.Entry<String,?> v:backup.entrySet())e.putString(v.getKey(),(String)v.getValue());e.commit();}
    }
    private <T>T field(Object object,String name,Class<T> type)throws Exception{Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return type.cast(f.get(object));}
    @Test public void nativeFormHasNoPrecheckedPassAndRecoveryClearsDesktopAndModuleAttestations()throws Exception{
        android.app.Instrumentation inst=InstrumentationRegistry.getInstrumentation();Context ctx=inst.getTargetContext();
        SharedPreferences prefs=ctx.getSharedPreferences("boot_feedback_v1",0);Map<String,?> backup=prefs.getAll();prefs.edit().clear().commit();
        Activity activity=inst.startActivitySync(new Intent(ctx,FeedbackActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try{inst.waitForIdleSync();inst.runOnMainSync(()->{try{
            assertFalse(field(activity,"passRadio",RadioButton.class).isChecked());assertFalse(field(activity,"modulesConfirm",CheckBox.class).isChecked());
            field(activity,"recovered",CheckBox.class).setChecked(true);
            assertTrue(field(activity,"failRadio",RadioButton.class).isChecked());assertFalse(field(activity,"desktopConfirm",CheckBox.class).isChecked());
            assertFalse(field(activity,"modulesConfirm",CheckBox.class).isChecked());assertFalse(field(activity,"passRadio",RadioButton.class).isEnabled());
        }catch(Exception e){throw new AssertionError(e);}});
            android.graphics.Bitmap preview=inst.getUiAutomation().takeScreenshot();
            if(preview!=null){try(OutputStream out=new FileOutputStream(new File(ctx.getExternalFilesDir(null),"feedback-form.png"))){preview.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}preview.recycle();}
        }finally{inst.runOnMainSync(activity::finish);inst.waitForIdleSync();SharedPreferences.Editor e=prefs.edit().clear();for(Map.Entry<String,?> v:backup.entrySet())e.putString(v.getKey(),(String)v.getValue());e.commit();}
    }
}
