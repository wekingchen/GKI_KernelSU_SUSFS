package com.wekingchen.pandoraota;

import android.app.*;
import android.content.*;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.InputFilter;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

/** Existing GitHub feedback form, with five local read-only checks. No pre-boot registration. */
public final class FeedbackActivity extends Activity {
    private static final int BG=Color.rgb(247,249,253),INK=Color.rgb(24,34,53),MUTED=Color.rgb(112,124,145),BLUE=Color.rgb(35,105,230),WARN=Color.rgb(173,86,45);
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private SecretStore secrets; private FeedbackStore store;
    private EditText runField,shaField,noteField;
    private TextView sourceInfo,evidenceInfo,statusInfo;
    private Button chooseButton,loadButton,readButton,submitButton,refreshButton,newButton,modulesButton,retryButton;
    private RadioButton passRadio,failRadio;
    private CheckBox recovered,imageConfirm,desktopConfirm,modulesConfirm;
    private FeedbackClient.Candidate candidate;
    private DeviceEvidence evidence;
    private JSONObject submission;
    private boolean busy,foreground,polling;
    private long generation;
    private final Runnable pollTask=() -> pollSubmission(false);

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);secrets=new SecretStore(this);store=new FeedbackStore(this);submission=store.submission();
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN|WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        LinearLayout shell=column();shell.setBackgroundColor(BG);setContentView(shell);
        if(Build.VERSION.SDK_INT>=35)getWindow().getDecorView().setOnApplyWindowInsetsListener((v,insets)->{
            android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars());shell.setPadding(0,bars.top,0,bars.bottom);return insets;
        });
        LinearLayout top=new LinearLayout(this);top.setGravity(Gravity.CENTER_VERTICAL);top.setPadding(dp(12),dp(8),dp(18),dp(8));shell.addView(top,new LinearLayout.LayoutParams(-1,dp(60)));
        Button back=button("返回",false);back.setContentDescription("返回工作台");top.addView(back,new LinearLayout.LayoutParams(dp(72),dp(42)));back.setOnClickListener(v->finish());
        TextView title=text("真机测试反馈",20,INK,true);top.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout body=column();body.setPadding(dp(18),dp(8),dp(18),dp(28));scroll.addView(body);
        TextView intro=text("电脑临时启动 → 手机测试 → 本机提交",12,MUTED,false);body.addView(intro);
        LinearLayout source=card(body,"01  测试对象","选择电脑刚才实际测试的待测 boot");
        chooseButton=button("选择候选",false);source.addView(chooseButton,space(12));chooseButton.setOnClickListener(v->chooseCandidate());
        runField=field("来源 Run ID",true);source.addView(runField,space(10));
        loadButton=button("读取候选信息",false);source.addView(loadButton,space(8));loadButton.setOnClickListener(v->loadCandidate());
        sourceInfo=text("尚未选择候选；旧候选没有手机元数据时，可手动填入 IMG 的 SHA-256。",12,MUTED,false);source.addView(sourceInfo,space(10));
        shaField=field("实际测试 IMG 的 SHA-256（64 位）",false);shaField.setTextSize(12);shaField.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);shaField.setMinLines(2);shaField.setTypeface(Typeface.MONOSPACE);source.addView(shaField,space(10));
        shaField.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){if(imageConfirm!=null)imageConfirm.setChecked(false);}
            public void afterTextChanged(android.text.Editable text){}
        });
        imageConfirm=check("我确认电脑实际测试的是上述候选镜像，SHA-256 一致");source.addView(imageConfirm,space(10));
        LinearLayout device=card(body,"02  本机验证信息","读取原来需要通过 ADB 检查的五项信息");
        readButton=button("读取本机验证信息",false);device.addView(readButton,space(12));readButton.setOnClickListener(v->readEvidence());
        evidenceInfo=text("尚未读取",12,MUTED,false);evidenceInfo.setTextIsSelectable(true);device.addView(evidenceInfo,space(12));
        modulesButton=button("展开模块明细",false);device.addView(modulesButton,space(10));modulesButton.setOnClickListener(v->showModules());
        LinearLayout result=card(body,"03  测试结果","自动读数不代替你实际测试基础功能");
        RadioGroup choices=new RadioGroup(this);choices.setOrientation(RadioGroup.HORIZONTAL);
        passRadio=new RadioButton(this);passRadio.setId(View.generateViewId());passRadio.setText("测试通过");
        failRadio=new RadioButton(this);failRadio.setId(View.generateViewId());failRadio.setText("测试失败");
        choices.addView(passRadio,new RadioGroup.LayoutParams(0,-2,1));choices.addView(failRadio,new RadioGroup.LayoutParams(0,-2,1));result.addView(choices,space(12));
        recovered=check("待测启动失败，未能进入系统；现已恢复");result.addView(recovered,space(8));
        desktopConfirm=check("我已进入待测系统桌面，启动状态为 1");result.addView(desktopConfirm,space(8));
        modulesConfirm=check("我已核对关键模块，并测试 Wi-Fi、移动数据/通话、蓝牙、相机等基础功能正常");result.addView(modulesConfirm,space(8));
        recovered.setOnCheckedChangeListener((b,value)->{
            if(value){failRadio.setChecked(true);desktopConfirm.setChecked(false);modulesConfirm.setChecked(false);}
            renderEvidence();renderControls();saveDraft();
        });
        choices.setOnCheckedChangeListener((group,id)->saveDraft());
        result.addView(text("恢复后环境只用于查看，不会填作失败待测内核的运行证据。",11,WARN,false),space(8));
        noteField=field("补充说明（选填，最多 1000 字）",false);noteField.setMinLines(3);noteField.setGravity(Gravity.TOP);noteField.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);noteField.setFilters(new InputFilter[]{new InputFilter.LengthFilter(1000)});result.addView(noteField,space(12));
        TextView permission=text("GitHub PAT 需授予目标仓库 Contents 读写、Actions 读写；可在设置中更新令牌。",11,MUTED,false);body.addView(permission,space(16));
        submitButton=button("核对并提交测试结果",true);body.addView(submitButton,space(12));submitButton.setOnClickListener(v->confirmSubmit());
        LinearLayout receipt=card(body,"提交状态","这里直接跟踪原工作流，无需打开网页填表");
        statusInfo=text("尚未提交",12,MUTED,false);statusInfo.setTextIsSelectable(true);receipt.addView(statusInfo,space(12));
        refreshButton=button("刷新提交状态",false);receipt.addView(refreshButton,space(10));refreshButton.setOnClickListener(v->pollSubmission(true));
        retryButton=button("重新发送同一反馈",false);receipt.addView(retryButton,space(8));
        retryButton.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("重新发送同一反馈？")
                .setMessage("仅在长时间未建立运行记录时使用。保持原反馈编号和全部内容，服务端会阻止重复处理。")
                .setNegativeButton("继续等待",null).setPositiveButton("重新发送",(d,w)->{
                    try{dispatch(submission.getJSONObject("inputs"),submission.getString("request_id"),true);}catch(Exception e){statusInfo.setText(message(e));}
                }).show());
        newButton=button("填写下一次反馈",false);receipt.addView(newButton,space(8));newButton.setOnClickListener(v->{
            if(pending())return;submission=new JSONObject();store.submission(null);imageConfirm.setChecked(false);desktopConfirm.setChecked(false);modulesConfirm.setChecked(false);choices.clearCheck();renderControls();statusInfo.setText("尚未提交");
        });
        Button history=button("历史反馈",false);receipt.addView(history,space(8));history.setOnClickListener(v->showHistory());
        restore();renderEvidence();renderControls();
        if(!pending())readEvidence();
    }
    private FeedbackClient client(){return new FeedbackClient(secrets.repo(),loadToken());}
    private String loadToken(){try{return secrets.loadToken();}catch(Exception e){throw new IllegalStateException("无法读取加密令牌，请在设置中重新保存",e);}}
    private void chooseCandidate(){
        if(busy||pending())return;
        task("正在查询可用候选…",()->client().candidates(), value->{
            @SuppressWarnings("unchecked") List<FeedbackClient.Candidate> list=(List<FeedbackClient.Candidate>)value;
            if(list.isEmpty()){statusInfo.setText("最近 15 轮中暂无有效候选。可输入已知 Run ID 查询；尚无新 OTA 时无需提交。 ");return;}
            String[] labels=new String[list.size()];for(int i=0;i<labels.length;i++)labels[i]=list.get(i).label();
            new AlertDialog.Builder(this).setTitle("选择实际测试的候选").setItems(labels,(d,i)->{runField.setText(Long.toString(list.get(i).run));loadCandidate();}).setNegativeButton("取消",null).show();
        });
    }
    private void loadCandidate(){
        if(busy||pending())return;
        long run;try{run=Long.parseLong(runField.getText().toString().trim());}catch(Exception e){statusInfo.setText("请输入有效的来源 Run ID");return;}
        task("正在核对候选来源…",()->client().candidate(run,true),value->{
            candidate=(FeedbackClient.Candidate)value;imageConfirm.setChecked(false);desktopConfirm.setChecked(false);modulesConfirm.setChecked(false);
            shaField.setText(candidate.sha);renderCandidate();saveDraft();
        });
    }
    private void renderCandidate(){
        if(candidate==null)return;
        sourceInfo.setText(candidate.label()+"\n"+(candidate.sha.isEmpty()?"旧候选：请填写电脑实际测试 IMG 的 SHA-256，服务端将再次核验":"镜像校验值已从该候选的独立元数据读取")
                +(candidate.uname.isEmpty()?"":"\n预期内核："+candidate.uname));renderControls();
    }
    private void readEvidence(){
        if(busy||pending())return;
        desktopConfirm.setChecked(false);modulesConfirm.setChecked(false);
        task("正在读取设备、build、启动状态、内核和模块…",DeviceEvidence::collect,value->{evidence=(DeviceEvidence)value;renderEvidence();saveDraft();});
    }
    private void renderEvidence(){
        if(evidenceInfo==null)return;
        if(evidence==null){evidenceInfo.setText("尚未读取");return;}
        String modules=evidence.moduleError.isEmpty()?(evidence.modules.trim().isEmpty()?"已读取 · 当前列表为空":"已读取 · "+evidence.modules.trim().split("\\r?\\n").length+" 个模块"):evidence.moduleError;
        evidenceInfo.setText((recovered.isChecked()?"恢复后环境（不会作为待测证据提交）\n":"")
                +"设备："+value(evidence.device)+"\n系统："+value(evidence.build)+"\n启动完成："+value(evidence.bootCompleted)
                +"\n内核："+value(evidence.uname)+"\n模块："+modules+"\n读取时间："+time(evidence.collectedAt));
        evidenceInfo.setTextColor(evidence.bootReady()&&!recovered.isChecked()?INK:WARN);
        renderControls();
    }
    private void showModules(){
        TextView text=text(evidence==null?"尚未读取":!evidence.moduleError.isEmpty()?evidence.moduleError:evidence.modules.isEmpty()?"已读取，当前模块列表为空":evidence.modules,11,INK,false);text.setTypeface(Typeface.MONOSPACE);text.setTextIsSelectable(true);text.setPadding(dp(18),dp(12),dp(18),dp(12));
        ScrollView scroll=new ScrollView(this);scroll.addView(text);
        new AlertDialog.Builder(this).setTitle("/proc/modules · 本机读取").setView(scroll).setPositiveButton("关闭",null).show();
    }
    private JSONObject form(String id)throws Exception{
        if(candidate==null||!Long.toString(candidate.run).equals(runField.getText().toString().trim()))throw new IllegalArgumentException("请先读取并核对来源候选");
        String sha=shaField.getText().toString().trim().toLowerCase(Locale.ROOT);
        if(!candidate.sha.isEmpty()&&!candidate.sha.equals(sha))throw new IllegalArgumentException("镜像 SHA-256 与候选不一致");
        return FeedbackForm.inputs(candidate.run,sha,passRadio.isChecked()?"pass":failRadio.isChecked()?"fail":"",evidence,
                candidate.build,candidate.uname,recovered.isChecked(),imageConfirm.isChecked(),desktopConfirm.isChecked(),modulesConfirm.isChecked(),noteField.getText().toString(),id);
    }
    private void confirmSubmit(){
        if(busy||pending())return;
        try{
            final String id=UUID.randomUUID().toString().replace("-","");final JSONObject inputs=form(id);
            String summary="来源："+candidate.label()+"\n结果："+("pass".equals(inputs.getString("result"))?"测试通过":"测试失败")
                    +"\n系统："+value(inputs.getString("observed_build"))+"\n内核："+value(inputs.getString("observed_uname"))
                    +"\nIMG SHA-256："+inputs.getString("tested_boot_sha256")
                    +"\n\n提交后由原工作流核验；通过将固化开发基线，LKG 不变。";
            new AlertDialog.Builder(this).setTitle("核对本次测试反馈").setMessage(summary)
                    .setNegativeButton("返回修改",null).setPositiveButton("确认提交",(d,w)->dispatch(inputs,id)).show();
        }catch(Exception e){statusInfo.setText(message(e));}
    }
    private void dispatch(JSONObject inputs,String id){dispatch(inputs,id,false);}
    private void dispatch(JSONObject inputs,String id,boolean retry){
        if(busy||(pending()&&!retry))return;
        if(retry&&(!id.equals(submission.optString("request_id"))||submission.optLong("run_id")>0))return;
        try{
            saveDraft();
            submission=new JSONObject().put("request_id",id).put("repo",secrets.repo()).put("result",inputs.getString("result"))
                    .put("source_run_id",inputs.getLong("source_run_id")).put("created_at",System.currentTimeMillis()).put("state","正在提交")
                    .put("terminal",false).put("run_id",0).put("inputs",inputs);
            store.submission(submission); // persist BEFORE network; an uncertain response never causes an automatic re-dispatch
            busy=true;renderControls();statusInfo.setText("正在向原工作流提交…");
            worker.execute(()->{
                String error="";boolean rejected=false;
                try{client().submit(inputs);}catch(Exception e){error=message(e);rejected=!retry&&e instanceof FeedbackClient.ApiException&&((FeedbackClient.ApiException)e).status>=400&&((FeedbackClient.ApiException)e).status<500;}
                final String detail=error;final boolean refused=rejected;
                runOnUiThread(()->{
                    busy=false;
                    try{submission.put("terminal",refused).put("state",refused?"提交未受理："+detail:detail.isEmpty()?"请求已发送，等待 GitHub 建立运行记录":"响应未确认，正在核对是否已受理；不会重复提交。\n"+detail);store.submission(submission);}
                    catch(Exception e){statusInfo.setText(message(e));}
                    renderReceipt();renderControls();schedulePoll();
                });
            });
        }catch(Exception e){busy=false;statusInfo.setText(message(e));renderControls();}
    }
    private boolean pending(){return submission!=null&&!submission.optString("request_id").isEmpty()&&!submission.optBoolean("terminal");}
    private void pollSubmission(boolean manual){
        if(!foreground||!pending()||polling||busy)return;
        if(!secrets.repo().equals(submission.optString("repo"))){statusInfo.setText("反馈属于其他仓库，请恢复设置中的原仓库后继续查询");return;}
        handler.removeCallbacks(pollTask);polling=true;final long ticket=generation;
        final String request=submission.optString("request_id");final long run=submission.optLong("run_id");
        worker.execute(()->{
            JSONObject response=null;String failure="";
            try{FeedbackClient c=client();response=run>0?c.readRun(run,request):c.findRun(request);}catch(Exception e){failure=message(e);}
            final JSONObject found=response;final String error=failure;
            runOnUiThread(()->{
                polling=false;if(!foreground||ticket!=generation||!request.equals(submission.optString("request_id"))){schedulePoll();return;}
                try{
                    if(!error.isEmpty())submission.put("state","查询暂未成功，将自动重试。\n"+error);
                    else if(found==null)submission.put("state","等待 GitHub 建立运行记录；无需再次提交，可稍后刷新");
                    else{
                        submission.put("run_id",found.getLong("id"));String status=found.optString("status"), conclusion=found.optString("conclusion");
                        boolean done="completed".equals(status);submission.put("terminal",done);
                        submission.put("state",!done?("in_progress".equals(status)?"正在核验来源、测试结果与基线":"已受理，等待工作流运行")
                                :"success".equals(conclusion)?("pass".equals(submission.optString("result"))?"验证完成，开发基线已固化；LKG 未变更":"测试失败报告已保存；未晋升基线")
                                :"工作流未通过（"+conclusion+"），请保留记录并检查错误");
                    }
                    store.submission(submission);renderReceipt();renderControls();
                }catch(Exception e){statusInfo.setText(message(e));}
                schedulePoll();
            });
        });
    }
    private void schedulePoll(){handler.removeCallbacks(pollTask);if(foreground&&pending())handler.postDelayed(pollTask,10000);}
    private void renderReceipt(){
        if(submission==null||submission.optString("request_id").isEmpty())return;
        statusInfo.setText(submission.optString("state")+"\n来源 Run #"+submission.optLong("source_run_id")
                +(submission.optLong("run_id")>0?"\n反馈运行 #"+submission.optLong("run_id"):"")
                +"\n反馈编号："+submission.optString("request_id"));
    }
    private void showHistory(){
        JSONArray all=store.history();if(all.length()==0){statusInfo.setText("暂无反馈历史");return;}
        String[] titles=new String[all.length()];for(int i=0;i<titles.length;i++){JSONObject j=all.optJSONObject(i);titles[i]="#"+j.optLong("source_run_id")+" · "+("pass".equals(j.optString("result"))?"通过反馈":"失败反馈")+"\n"+time(j.optLong("created_at"));}
        new AlertDialog.Builder(this).setTitle("最近反馈").setItems(titles,(d,i)->{
            JSONObject j=all.optJSONObject(i);new AlertDialog.Builder(this).setTitle("反馈记录")
                    .setMessage(j.optString("state")+"\n反馈运行 #"+j.optLong("run_id")+"\n"+j.optJSONObject("inputs").toString())
                    .setPositiveButton("关闭",null).show();
        }).setNegativeButton("关闭",null).show();
    }
    private void renderControls(){
        if(submitButton==null)return;boolean editable=!busy&&!pending();
        for(View v:new View[]{runField,chooseButton,loadButton,readButton,imageConfirm,desktopConfirm,modulesConfirm,noteField,failRadio,recovered,submitButton})v.setEnabled(editable);
        shaField.setEnabled(editable&&(candidate==null||candidate.sha.isEmpty()));
        passRadio.setEnabled(editable&&!recovered.isChecked());
        desktopConfirm.setEnabled(editable&&!recovered.isChecked()&&evidence!=null&&evidence.bootReady());
        modulesConfirm.setEnabled(editable&&!recovered.isChecked());
        retryButton.setVisibility(pending()&&submission.optLong("run_id")==0&&System.currentTimeMillis()-submission.optLong("created_at")>=120000?View.VISIBLE:View.GONE);
        retryButton.setEnabled(!busy&&!polling);
        refreshButton.setEnabled(!busy&&pending()&&!polling);newButton.setVisibility(submission!=null&&!submission.optString("request_id").isEmpty()&&!pending()?View.VISIBLE:View.GONE);
        submitButton.setText(pending()?"已提交 · 正在跟踪结果":"核对并提交测试结果");
    }
    private void saveDraft(){
        if(noteField==null)return;
        try{JSONObject j=new JSONObject().put("repo",secrets.repo()).put("run",runField.getText().toString()).put("sha",shaField.getText().toString())
                .put("note",noteField.getText().toString()).put("recovered",recovered.isChecked());
            if(candidate!=null)j.put("candidate",candidate.json());if(evidence!=null)j.put("evidence",evidence.json());store.draft(j);
        }catch(Exception e){statusInfo.setText(message(e));}
    }
    private void restore(){
        JSONObject j=store.draft();if(secrets.repo().equals(j.optString("repo"))){
            runField.setText(j.optString("run"));shaField.setText(j.optString("sha"));noteField.setText(j.optString("note"));
            if(j.optJSONObject("candidate")!=null)candidate=FeedbackClient.Candidate.from(j.optJSONObject("candidate"));
            if(j.optJSONObject("evidence")!=null)evidence=DeviceEvidence.from(j.optJSONObject("evidence"));
            recovered.setChecked(j.optBoolean("recovered"));renderCandidate();
        }
        // Human pass/module/image attestations deliberately start unchecked after reopening.
        renderReceipt();
    }
    interface Work{Object run()throws Exception;} interface Done{void accept(Object value);}
    private void task(String label,Work work,Done done){
        if(busy)return;busy=true;renderControls();statusInfo.setText(label);
        worker.execute(()->{Object value=null;String error="";try{value=work.run();}catch(Exception e){error=message(e);}final Object result=value;final String failure=error;
            runOnUiThread(()->{busy=false;if(isFinishing()||isDestroyed())return;renderControls();if(!failure.isEmpty())statusInfo.setText(failure);else{statusInfo.setText("已完成，请核对结果");done.accept(result);}});
        });
    }
    @Override protected void onStart(){super.onStart();foreground=true;if(submission!=null){renderReceipt();pollSubmission(false);schedulePoll();}}
    @Override protected void onStop(){foreground=false;generation++;handler.removeCallbacks(pollTask);saveDraft();super.onStop();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);worker.shutdown();super.onDestroy();}
    private String value(String text){return text==null||text.isEmpty()?"未取得":text;}
    private String time(long millis){return new SimpleDateFormat("MM-dd HH:mm:ss",Locale.CHINA).format(new Date(millis));}
    private static String message(Exception e){String s=e.getMessage();return s==null?"操作未完成":s.length()>240?s.substring(0,240):s;}
    private LinearLayout column(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
    private LinearLayout card(LinearLayout parent,String title,String sub){LinearLayout c=column();c.setPadding(dp(18),dp(18),dp(18),dp(18));c.setBackground(round(Color.WHITE,22));c.setElevation(dp(1));parent.addView(c,space(18));c.addView(text(title,17,INK,true));c.addView(text(sub,11,MUTED,false),space(5));return c;}
    private TextView text(String s,int size,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(3),1);if(bold)t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return t;}
    private CheckBox check(String s){CheckBox c=new CheckBox(this);c.setText(s);c.setTextSize(12);c.setTextColor(INK);c.setButtonTintList(ColorStateList.valueOf(BLUE));return c;}
    private EditText field(String hint,boolean number){EditText e=new EditText(this);e.setHint(hint);e.setTextSize(14);e.setTextColor(INK);e.setPadding(dp(12),dp(11),dp(12),dp(11));e.setBackground(round(Color.rgb(243,246,252),12));e.setInputType(number?InputType.TYPE_CLASS_NUMBER:InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);return e;}
    private Button button(String s,boolean primary){Button b=new Button(this);b.setText(s);b.setTextSize(13);b.setAllCaps(false);b.setMinHeight(dp(44));b.setMinimumHeight(dp(44));b.setTextColor(primary?Color.WHITE:BLUE);b.setBackground(round(primary?BLUE:Color.rgb(233,241,255),14));return b;}
    private GradientDrawable round(int color,int radius){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));return g;}
    private LinearLayout.LayoutParams space(int top){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(top);return p;}
    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
}
