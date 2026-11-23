package com.wekingchen.pandoraota;

import android.graphics.Bitmap;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.TextView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.*;
import static org.junit.Assert.*;

/** Simulated OTA task data; never assumes emulator is pandora or can collect OEM files. */
@RunWith(AndroidJUnit4.class)
public final class DiagnosisEmulatorTest {
    private static final String BUILD="OS4.0.6.0.XBLCNXM", STOCK="a".repeat(64), HEAD="b".repeat(40);
    private JSONObject rawTask()throws Exception{
        return new JSONObject().put("schema","pandora-ota-diagnostic-task-v1")
                .put("repository",StageClient.REPO).put("device","pandora")
                .put("source_run_id",12345).put("source_head_sha",HEAD)
                .put("stock_build",BUILD).put("stock_input_sha256",STOCK)
                .put("candidate_commit","c".repeat(40))
                .put("status","ABI_BLOCKED_DIAGNOSABLE")
                .put("issues",new JSONArray().put(new JSONObject()
                        .put("code",DiagnosisClient.RUST).put("count",71))
                        .put(new JSONObject().put("code",DiagnosisClient.PROVIDER).put("count",27)))
                .put("checks",new JSONArray().put(new JSONObject()
                        .put("id","binder_runtime").put("label","Binder 活动状态"))
                        .put(new JSONObject().put("id","loaded_module_identity").put("label","已加载模块来源")))
                .put("requires_manual_review",true).put("commands",new JSONArray())
                .put("device_write_allowed",false).put("upload_requires_confirmation",true)
                .put("safe_to_flash",false).put("promote_lkg",false);
    }
    private StageClient.State stage()throws Exception{
        return new StageClient.State(new JSONObject()
                .put("stage","ABI_BLOCKED").put("build",BUILD)
                .put("producer_run_id",77).put("source_run_id",12345)
                .put("source_head_sha",HEAD).put("stock_input_sha256",STOCK));
    }
    private JSONObject source()throws Exception{
        return new JSONObject().put("id",12345).put("head_branch","dev")
                .put("head_sha",HEAD).put("event","workflow_dispatch")
                .put("path",".github/workflows/"+DiagnosisClient.SOURCE)
                .put("status","completed").put("conclusion","success");
    }
    private DiagnosisClient.Task verifiedTask()throws Exception{
        return DiagnosisClient.validate(rawTask(),stage(),source());
    }
    private static void reject(JSONObject task,StageClient.State stage,JSONObject source)throws Exception{
        try{DiagnosisClient.validate(task,stage,source);fail("Unsafe diagnostic task accepted");}
        catch(IOException expected){}
    }
    @Test public void serverTaskMustBeExactCurrentBuildAndNeverContainCommands()throws Exception{
        DiagnosisClient.Task valid=verifiedTask();
        assertEquals(2,valid.checks.size());
        assertEquals("需要确认 Binder 实际模式，以及压缩内存模块的来源",valid.plainSummary());
        assertTrue(valid.issuesForHuman().contains("71 项"));
        assertTrue(valid.issuesForHuman().contains("27 项"));
        JSONObject bad=rawTask().put("commands",new JSONArray().put("cat /proc/kallsyms"));
        reject(bad,stage(),source());
        bad=rawTask().put("device_write_allowed",true);reject(bad,stage(),source());
        bad=rawTask().put("stock_input_sha256","d".repeat(64));reject(bad,stage(),source());
        bad=rawTask().put("stock_build","OS4.0.5.0.XBLCNXM");reject(bad,stage(),source());
        bad=rawTask().put("source_run_id",12346);reject(bad,stage(),source());
        bad=rawTask().put("promote_lkg",true);reject(bad,stage(),source());
        bad=rawTask().put("checks",new JSONArray().put(new JSONObject()
                .put("id","execute_shell").put("label","执行命令")));reject(bad,stage(),source());
    }
    @Test public void wrongRunOrStageOrSourceCannotLaunchTrustworthyTask()throws Exception{
        reject(rawTask(),new StageClient.State(new JSONObject()
                .put("stage","LKG_ARCHIVED").put("build",BUILD)
                .put("producer_run_id",77).put("source_run_id",12345).put("source_head_sha",HEAD)
                .put("stock_input_sha256",STOCK)),source());
        reject(rawTask(),stage(),source().put("head_branch","untrusted"));
        reject(rawTask(),stage(),source().put("head_sha","d".repeat(40)));
    }
    @Test public void fixedReadOnlyCollectorRedactsFullCmdlineAndKernelAddresses()throws Exception{
        Map<String,String> values=new HashMap<>();
        values.put("device","pandora");values.put("build",BUILD);
        values.put("boot","1");values.put("slot","_b");
        values.put("uname","6.12.69-android16-6-test-4k");
        values.put("modules","rust_binder 9876 0 - Live 0xffff0000\n"+
                "node_cache 5 0 - Live 0xffa000\nzram 1 0 - Live 0xffff\nzsmalloc 1 1 - Live 0xffaa\n");
        values.put("binder_impl","c");values.put("binder_active_impl","c");
        values.put("cmdline","androidboot.serialno=SECRET_IDENT module_blacklist=kernelsu pandora_rust_binder_eexist=1 root=secret");
        for(String name:new String[]{"node_cache","zram","zsmalloc"})
            values.put("note_"+name,"d".repeat(64)+" /sys/module/"+name+"/notes/.note.gnu.build-id");
        JSONObject result=DiagnosisCollector.capture(verifiedTask(),key->values.get(key));
        assertEquals("CAPTURED_READ_ONLY",result.getString("status"));
        String serialized=result.toString();
        assertFalse(serialized.contains("SECRET_IDENT"));
        assertFalse(serialized.contains("0xffff"));
        assertFalse(serialized.contains("root=secret"));
        assertFalse(serialized.contains("modprobe"));
        assertFalse(result.optBoolean("device_write_allowed",true));
        assertFalse(result.optBoolean("lkg_promotion",true));
        assertEquals("d".repeat(64),result.getJSONObject("observations")
                .getJSONObject("loaded_module_identity").getJSONObject("zsmalloc")
                .getString("gnu_note_sha256"));
    }
    @Test public void missingRootNoteIsPartialNeverFakedAsSuccess()throws Exception{
        JSONObject result=DiagnosisCollector.capture(verifiedTask(),key->{
            if("device".equals(key))return "pandora";
            if("build".equals(key))return BUILD;
            if("boot".equals(key))return "1";
            if("slot".equals(key))return "_b";
            if("uname".equals(key))return "6.12.69-android16-6-test-4k";
            if("modules".equals(key))return "node_cache 1\nzram 1\nzsmalloc 1\n";
            if("binder_impl".equals(key)||"binder_active_impl".equals(key))return "c";
            throw new IOException("permission denied");
        });
        assertEquals("PARTIAL_READ_ONLY",result.getString("status"));
        assertTrue(result.getJSONObject("observations")
                .getJSONObject("loaded_module_identity").getJSONObject("zsmalloc")
                .isNull("gnu_note_sha256"));
    }
    @Test public void currentBuildMustMatchBeforeReadingTaskEvidence()throws Exception{
        try{
            DiagnosisCollector.capture(verifiedTask(),key->{
                if("device".equals(key))return "pandora";
                if("build".equals(key))return "OS4.0.5.0.XBLCNXM";
                return "1";
            });
            fail("Old or different build captured");
        }catch(IOException expected){assertTrue(expected.getMessage().contains("OTA"));}
    }
    private static <T> T field(Object object,String name,Class<T> type)throws Exception{
        Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return type.cast(f.get(object));
    }
    private static void set(Object target,String name,Object value)throws Exception{
        Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);
    }
    @Test public void nativeDiagnosisPagePreservesThreeStepFlowAndExplicitConsent()throws Exception{
        // No online GitHub calls are faked as successful. The emulator is not pandora.
        try(ActivityScenario<DiagnosisActivity> scenario=ActivityScenario.launch(DiagnosisActivity.class)){
            Thread.sleep(400);
            scenario.onActivity(activity->{
                try{
                    assertNotNull(field(activity,"taskInfo",TextView.class));
                    assertFalse(field(activity,"submitButton",Button.class).isEnabled());
                    assertEquals(View.GONE,field(activity,"retryButton",Button.class).getVisibility());
                    DiagnosisClient.Task task=verifiedTask();
                    set(activity,"currentTask",task);
                    field(activity,"taskInfo",TextView.class).setText(
                            "需要确认 Binder 与已加载模块的实际状态\n\n"+BUILD+
                            "\n已定位两类 ABI 阻断 · 不会修改手机");
                    field(activity,"scopeInfo",TextView.class).setText(
                            "只读取 Binder 状态、模块名称及 GNU Note 指纹");
                    set(activity,"evidence",new JSONObject().put("schema",DiagnosisCollector.SCHEMA));
                    Method render=DiagnosisActivity.class.getDeclaredMethod("renderControls");
                    render.setAccessible(true);render.invoke(activity);
                    CheckBox check=field(activity,"reviewed",CheckBox.class);
                    assertFalse("Must preview first",check.isEnabled());
                    assertFalse(field(activity,"submitButton",Button.class).isEnabled());
                    // Save actual native layout screenshot, no generated mock image.
                    Bitmap shot=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
                    assertNotNull(shot);
                    File dest=new File(activity.getExternalFilesDir(null),"diagnosis-v2.png");
                    try(FileOutputStream out=new FileOutputStream(dest)){assertTrue(shot.compress(Bitmap.CompressFormat.PNG,95,out));}
                    shot.recycle();
                    assertTrue(dest.length()>30000);
                }catch(Exception e){throw new AssertionError(e);}
            });
        }
    }
}
