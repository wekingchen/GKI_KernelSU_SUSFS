package com.wekingchen.pandoraota;

import android.app.*;
import android.content.*;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/**
 * A short, optional secondary route reached only after verified ABI_BLOCKED.
 * It does not change the existing 3-tab home, OTA capture, or fastboot feedback.
 */
public final class DiagnosisActivity extends Activity {
    private static final int BG=Color.rgb(247,249,253),INK=Color.rgb(24,34,53);
    private static final int MUTED=Color.rgb(112,124,145),BLUE=Color.rgb(35,105,230);
    private static final int WARNING=Color.rgb(173,86,45),WHITE=Color.WHITE;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private SecretStore secrets;
    private DiagnosisClient.Task currentTask;
    private JSONObject evidence;
    private DiagnosisUploader.Receipt receipt;
    private TextView taskInfo,readInfo,uploadInfo,scopeInfo;
    private Button loadButton,readButton,previewButton,submitButton,retryButton,releaseButton;
    private CheckBox reviewed;
    private boolean busy;
    private String errorText="";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        secrets=new SecretStore(this);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        LinearLayout shell=column();shell.setBackgroundColor(BG);setContentView(shell);
        if(Build.VERSION.SDK_INT>=35)getWindow().getDecorView().setOnApplyWindowInsetsListener((view,insets)->{
            android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars());
            shell.setPadding(0,bars.top,0,bars.bottom);
            return insets;
        });
        LinearLayout top=new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);top.setPadding(dp(12),dp(8),dp(18),dp(8));
        shell.addView(top,new LinearLayout.LayoutParams(-1,dp(60)));
        Button back=button("返回",false);back.setContentDescription("返回工作台");
        top.addView(back,new LinearLayout.LayoutParams(dp(72),dp(42)));
        back.setOnClickListener(v->finish());
        top.addView(text("兼容性补采",20,INK,true),new LinearLayout.LayoutParams(0,-2,1));

        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);
        shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout body=column();body.setPadding(dp(18),dp(8),dp(18),dp(30));scroll.addView(body);
        body.addView(text("仅在 OTA ABI 检查被阻断时使用 · 不刷机、不改系统",12,MUTED,false));

        LinearLayout intro=card(body,"01  为什么需要补采","自动识别当前 OTA 的阻断原因，不再手动找命令");
        taskInfo=text("正在核验当前 GitHub 来源与待补充的证据…",13,INK,false);
        intro.addView(taskInfo,space(12));
        loadButton=button("重新读取补采任务",false);
        intro.addView(loadButton,space(12));loadButton.setOnClickListener(v->loadTask());

        LinearLayout read=card(body,"02  只读检查手机","仅采集当前任务需要的状态，不读取原始分区镜像");
        scopeInfo=text("需先完成可信任务核验。不会上传内核地址、完整 cmdline 或系统日志。",12,MUTED,false);
        read.addView(scopeInfo,space(12));
        readButton=button("开始只读采集",false);
        read.addView(readButton,space(12));readButton.setOnClickListener(v->collect());
        readInfo=text("尚未采集",12,MUTED,false);
        readInfo.setTextIsSelectable(true);read.addView(readInfo,space(9));
        previewButton=button("预览将提交的内容",false);
        read.addView(previewButton,space(9));previewButton.setOnClickListener(v->showPreview());

        LinearLayout submit=card(body,"03  核对后提交","先预览，再决定是否发送到 GitHub");
        submit.addView(text("只发送白名单状态和模块 GNU Note 的 SHA-256，不发送原始内存、内核地址或完整日志。GitHub 草稿只用于核验，提交不会解锁 ABI、刷机或 LKG。",11,MUTED,false),space(12));
        reviewed=new CheckBox(this);reviewed.setText("已检查预览内容，同意将本次只读诊断信息上传到 GitHub 草稿");
        reviewed.setTextSize(12);reviewed.setTextColor(INK);
        reviewed.setButtonTintList(ColorStateList.valueOf(BLUE));
        submit.addView(reviewed,space(12));
        reviewed.setOnCheckedChangeListener((button,yes)->renderControls());
        submitButton=button("核对并上传诊断报告",true);submit.addView(submitButton,space(10));
        submitButton.setOnClickListener(v->confirmUpload());

        LinearLayout result=card(body,"提交与审核状态","GitHub 只做证据接收审核，不会自动判定内核兼容");
        uploadInfo=text("尚未提交",12,MUTED,false);
        uploadInfo.setTextIsSelectable(true);result.addView(uploadInfo,space(12));
        retryButton=button("重新通知审核工作流",false);
        result.addView(retryButton,space(9));retryButton.setOnClickListener(v->retryDispatch());
        releaseButton=button("查看 GitHub 诊断草稿",false);
        result.addView(releaseButton,space(9));releaseButton.setOnClickListener(v->openDraft());

        renderControls();loadTask();
    }
    private String token()throws Exception{return secrets.loadToken();}
    private void loadTask(){
        run("正在核验诊断任务…",()->{
            StageClient.State stage=new StageClient(secrets.repo(),token()).latest();
            if(!"ABI_BLOCKED".equals(stage.stage))
                throw new java.io.IOException("当前阶段为「"+stage.title()+"」，不需要再采集 ABI 诊断。只有新 OTA 被阻断时才会出现任务。");
            DiagnosisClient.Task task=new DiagnosisClient(secrets.repo(),token()).load(stage);
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                boolean changed=currentTask==null||currentTask.run!=task.run||
                        !currentTask.stockSha.equals(task.stockSha)||!currentTask.head.equals(task.head);
                currentTask=task;
                if(changed){evidence=null;receipt=null;reviewed.setChecked(false);}
                taskInfo.setText(task.plainSummary()+"\n\n"+task.build+
                        "\n此次 GitHub 已确认有 "+task.issues.size()+" 类问题，需要 "+task.checks.size()+" 类只读检查。\n"+
                        "不会重新采集原始 boot 或 OEM 模块，也不会执行 GitHub 下发的命令。");
                scopeInfo.setText(task.checks.contains("binder_runtime")&&task.checks.contains("loaded_module_identity")?
                        "将读取 Binder 活动模式、模块加载名称和 zram/zsmalloc 的 GNU Note 指纹。" :
                        task.checks.contains("binder_runtime")?
                        "仅检查 Binder 活动实现、Rust Binder 模块和相关启动参数是否存在。" :
                        "仅检查已加载模块及其 GNU Note 指纹，保持 vendor/system 来源严格区分。");
                readInfo.setText("尚未采集");uploadInfo.setText("尚未提交");
                renderControls();
            });
            return "已核验诊断来源";
        });
    }
    private void collect(){
        if(currentTask==null)return;
        DiagnosisClient.Task task=currentTask;
        run("正在只读采集设备状态…",()->{
            JSONObject data=DiagnosisCollector.capture(task);
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed()||currentTask!=task)return;
                evidence=data;receipt=null;reviewed.setChecked(false);
                boolean partial="PARTIAL_READ_ONLY".equals(data.optString("status"));
                readInfo.setText(partial?
                        "已取得部分信息；Root/模块指纹可能受限。仍可预览并作为不完整证据提交，但不能判定通过。" :
                        "已完成只读采集。请先预览，再确认是否发送。");
                readInfo.setTextColor(partial?WARNING:INK);
                uploadInfo.setText("尚未提交");renderControls();
            });
            return "只读采集已完成";
        });
    }
    private void showPreview(){
        if(evidence==null)return;
        try{
            JSONObject obs=evidence.getJSONObject("observations");
            StringBuilder summary=new StringBuilder("版本："+evidence.optString("stock_build")+
                    "\n来源 Run #"+evidence.optLong("source_run_id")+
                    "\n采集状态："+("PARTIAL_READ_ONLY".equals(evidence.optString("status"))?"部分信息未取得":"已取得白名单信息"));
            JSONObject identity=obs.optJSONObject("identity");
            if(identity!=null)summary.append("\n\n本机：").append(identity.optString("device"))
                    .append(" / ").append(identity.optString("slot"))
                    .append("\n内核：").append(identity.optString("uname"));
            JSONObject binder=obs.optJSONObject("binder_runtime");
            if(binder!=null)summary.append("\n\nBinder：")
                    .append(binder.optString("impl","UNKNOWN")).append(" / ")
                    .append(binder.optString("active_impl","UNKNOWN"))
                    .append("\nRust Binder 是否加载：").append(binder.isNull("rust_binder_loaded")?"未取得":binder.optBoolean("rust_binder_loaded")?"是":"否");
            JSONObject modules=obs.optJSONObject("loaded_module_identity");
            if(modules!=null)for(String name:new String[]{"node_cache","zram","zsmalloc"}){
                JSONObject item=modules.optJSONObject(name);
                if(item!=null)summary.append("\n").append(name).append("：")
                        .append(item.isNull("loaded")?"未取得":item.optBoolean("loaded")?"已加载":"未加载")
                        .append("；Note ").append(item.isNull("gnu_note_sha256")?"未取得":item.optString("gnu_note_sha256"));
            }
            summary.append("\n\n说明：此页没有完整 cmdline、模块地址或系统日志；仅提交这些结构化状态。");
            new AlertDialog.Builder(this).setTitle("只读报告预览")
                    .setMessage(summary.toString()).setPositiveButton("确认",null).show();
        }catch(Exception e){readInfo.setText("无法预览：请重新只读采集");}
    }
    private void confirmUpload(){
        if(currentTask==null||evidence==null||!reviewed.isChecked()||receipt!=null||busy)return;
        new AlertDialog.Builder(this).setTitle("提交当前诊断信息？")
                .setMessage("只上传本次预览过的白名单状态。GitHub 会先保存为 Draft，再运行只读核验；不会修改手机、解锁 ABI 或晋升 LKG。")
                .setNegativeButton("返回检查",null)
                .setPositiveButton("确认上传",(d,w)->upload()).show();
    }
    private void upload(){
        if(currentTask==null||evidence==null||receipt!=null)return;
        DiagnosisClient.Task selected=currentTask;
        JSONObject data=evidence;
        run("正在验证当前 OTA 并上传草稿…",()->{
            String pat=token();
            StageClient.State stage=new StageClient(secrets.repo(),pat).latest();
            DiagnosisClient.Task fresh=new DiagnosisClient(secrets.repo(),pat).load(stage);
            if(selected.run!=fresh.run||!selected.stockSha.equals(fresh.stockSha)
                    ||!selected.head.equals(fresh.head)||!selected.checks.equals(fresh.checks))
                throw new java.io.IOException("补采任务已变化，请返回工作台重新获取；没有上传旧版本数据");
            DiagnosisUploader.Receipt r=new DiagnosisUploader(secrets.repo(),pat).upload(data);
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed()||currentTask!=selected)return;
                receipt=r;
                uploadInfo.setText(r.dispatched?
                        "GitHub 已确认附件并通知审核。\n状态：等待只读审核；这不是 ABI 通过。" :
                        "GitHub 已确认草稿附件，但通知审核失败或结果未知。\n请使用下方「重新通知」，不要再次上传。");
                reviewed.setChecked(false);renderControls();
            });
            return "已保存到 GitHub 诊断草稿";
        });
    }
    private void retryDispatch(){
        DiagnosisUploader.Receipt r=receipt;
        if(r==null||r.dispatched)return;
        run("正在重新通知审核…",()->{
            new DiagnosisUploader(secrets.repo(),token()).notifyIntake(r);
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed()||receipt!=r)return;
                receipt=new DiagnosisUploader.Receipt(r.releaseId,r.assetId,r.sourceRun,
                        r.sha,r.releaseUrl,r.tag,true);
                uploadInfo.setText("审核工作流已收到通知。\n请在 GitHub 查看审核结果；仍不代表 ABI 已通过。");
                renderControls();
            });
            return "已通知只读审核工作流";
        });
    }
    private void openDraft(){
        if(receipt==null)return;
        String url="https://github.com/"+DiagnosisUploader.REPO+"/releases/tag/"+receipt.tag;
        startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)));
    }
    private interface Operation{String perform()throws Exception;}
    private void run(String label,Operation operation){
        if(busy)return;
        busy=true;errorText="";renderControls();
        worker.execute(()->{
            String result=null;Exception failed=null;
            try{result=operation.perform();}catch(Exception e){failed=e;}
            final String value=result;final Exception error=failed;
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                busy=false;
                if(error!=null){
                    errorText=error.getMessage()==null?"操作未完成":error.getMessage();
                    if(errorText.length()>230)errorText=errorText.substring(0,230);
                    if(currentTask==null)taskInfo.setText(errorText);
                    else if(receipt==null)uploadInfo.setText("操作未完成："+errorText);
                }
                renderControls();
            });
        });
    }
    private void renderControls(){
        if(loadButton==null)return;
        loadButton.setEnabled(!busy);
        readButton.setEnabled(!busy&&currentTask!=null&&receipt==null);
        previewButton.setEnabled(!busy&&evidence!=null);
        submitButton.setEnabled(!busy&&currentTask!=null&&evidence!=null&&reviewed.isChecked()&&receipt==null);
        retryButton.setVisibility(receipt!=null&&!receipt.dispatched?View.VISIBLE:View.GONE);
        retryButton.setEnabled(!busy);
        releaseButton.setVisibility(receipt!=null?View.VISIBLE:View.GONE);
        releaseButton.setEnabled(!busy);
    }
    private LinearLayout column(){LinearLayout c=new LinearLayout(this);c.setOrientation(LinearLayout.VERTICAL);return c;}
    private LinearLayout card(LinearLayout parent,String title,String sub){
        LinearLayout card=column();card.setPadding(dp(18),dp(17),dp(18),dp(18));
        card.setBackground(round(WHITE,22));card.setElevation(dp(1));
        parent.addView(card,space(16));card.addView(text(title,17,INK,true));
        card.addView(text(sub,11,MUTED,false),space(5));return card;
    }
    private TextView text(String value,int size,int color,boolean strong){
        TextView t=new TextView(this);t.setText(value);t.setTextColor(color);
        t.setTextSize(size);t.setLineSpacing(dp(3),1);
        if(strong)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t;
    }
    private Button button(String title,boolean primary){
        Button b=new Button(this);b.setText(title);b.setTextSize(13);b.setAllCaps(false);
        b.setMinHeight(dp(46));b.setMinimumHeight(dp(46));b.setTextColor(primary?WHITE:BLUE);
        b.setBackground(round(primary?BLUE:Color.rgb(233,241,255),14));return b;
    }
    private GradientDrawable round(int color,int radius){
        GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));return g;
    }
    private LinearLayout.LayoutParams space(int top){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(top);return p;
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    @Override protected void onDestroy(){worker.shutdownNow();super.onDestroy();}
}
