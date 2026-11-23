package com.wekingchen.pandoraota;

import org.json.*;
import java.io.IOException;
import java.util.*;

/** The app consumes only signed-by-provenance, non-executable, issue-scoped OTA tasks. */
final class DiagnosisClient {
    static final String TASK="ota-v2-diagnostic-task.json";
    static final String ABI_ARTIFACT="pandora-OTA-OEM-ABI-TESTBOOT-";
    static final String SOURCE="xiaomi-sm8850-os4-ota-auto-candidate.yml";
    static final String RUST="STOCK_RUST_BINDER_ABI_UNRESOLVED";
    static final String PROVIDER="AMBIGUOUS_MODULE_PROVIDERS";
    private final FeedbackClient client;
    DiagnosisClient(String repo,String token){client=new FeedbackClient(repo,token);}
    DiagnosisClient(String repo,String token,FeedbackClient.Transport transport){
        client=new FeedbackClient(repo,token,transport);
    }
    static final class Task {
        final JSONObject json;
        final long run;
        final String build,stockSha,commit,head;
        final List<String> checks;
        final List<String> issues;
        Task(JSONObject j)throws Exception {
            json=j;run=j.getLong("source_run_id");build=j.getString("stock_build");
            stockSha=j.getString("stock_input_sha256");head=j.getString("source_head_sha");
            commit=j.getString("candidate_commit");
            checks=new ArrayList<>();issues=new ArrayList<>();
            JSONArray a=j.getJSONArray("checks");
            for(int i=0;i<a.length();i++)checks.add(a.getJSONObject(i).getString("id"));
            a=j.getJSONArray("issues");
            for(int i=0;i<a.length();i++)issues.add(a.getJSONObject(i).getString("code"));
        }
        String plainSummary(){
            if(checks.size()==1&&checks.contains("binder_runtime"))return "需要确认 Binder 实际工作模式";
            if(checks.size()==1&&checks.contains("loaded_module_identity"))return "需要确认已加载模块的来源";
            return "需要确认 Binder 与已加载模块的实际状态";
        }
    }
    static final Map<String,String> ISSUE_TYPES=new LinkedHashMap<>();
    static {
        ISSUE_TYPES.put(RUST,"binder_runtime");
        ISSUE_TYPES.put(PROVIDER,"loaded_module_identity");
        ISSUE_TYPES.put("OTHER_UNRESOLVED_IMPORTS","loaded_module_identity");
        ISSUE_TYPES.put("MODULE_CRC_MISMATCH","loaded_module_identity");
        ISSUE_TYPES.put("OEM_MODULE_PARSE_OR_IDENTITY_FAILURE","loaded_module_identity");
    }
    static Task validate(JSONObject j,StageClient.State state,JSONObject source)throws Exception {
        if(!"ABI_BLOCKED".equals(state.stage))throw new IOException("当前不是 ABI 阻断阶段，不需要补采");
        if(!"pandora-ota-diagnostic-task-v1".equals(j.optString("schema"))
                ||!StageClient.REPO.equals(j.optString("repository"))
                ||!"pandora".equals(j.optString("device"))
                ||!"ABI_BLOCKED_DIAGNOSABLE".equals(j.optString("status"))
                ||j.optLong("source_run_id")!=state.json.optLong("source_run_id")
                ||!j.optString("source_head_sha").equals(state.json.optString("source_head_sha"))
                ||!state.build.equals(j.optString("stock_build"))
                ||!state.json.optString("stock_input_sha256").equals(j.optString("stock_input_sha256"))
                ||!j.optString("candidate_commit").matches("[a-f0-9]{40}")
                ||j.optBoolean("device_write_allowed",true)||j.optBoolean("safe_to_flash",true)
                ||j.optBoolean("promote_lkg",true)
                ||!j.optBoolean("requires_manual_review")||!j.optBoolean("upload_requires_confirmation")
                ||j.optJSONArray("commands")==null||j.getJSONArray("commands").length()!=0)
            throw new IOException("补采任务与当前 OTA 来源或只读限制不一致");
        if(source.optLong("id")!=j.getLong("source_run_id")
                ||!StageClient.trusted(source,SOURCE)
                ||!source.optString("head_sha").equals(j.optString("source_head_sha")))
            throw new IOException("补采来源工作流未经可信验证");
        JSONArray issues=j.getJSONArray("issues"),checks=j.getJSONArray("checks");
        if(issues.length()<1||issues.length()>5||checks.length()<1||checks.length()>2)
            throw new IOException("补采任务数量异常");
        Set<String> seen=new LinkedHashSet<>(),expected=new LinkedHashSet<>();
        for(int i=0;i<issues.length();i++){
            JSONObject item=issues.getJSONObject(i);
            String code=item.optString("code");
            if(!ISSUE_TYPES.containsKey(code)||!seen.add(code)||item.optInt("count")<=0)
                throw new IOException("补采任务包含未知问题或重复项目");
            expected.add(ISSUE_TYPES.get(code));
        }
        Set<String> types=new LinkedHashSet<>();
        for(int i=0;i<checks.length();i++){
            JSONObject item=checks.getJSONObject(i);
            String type=item.optString("id");
            if(!("binder_runtime".equals(type)||"loaded_module_identity".equals(type))
                    ||!types.add(type)||item.optString("label").isEmpty())
                throw new IOException("服务器补采类型不受支持");
        }
        if(!types.equals(expected))throw new IOException("补采类型与问题不一致");
        return new Task(j);
    }
    Task load(StageClient.State state)throws Exception {
        if(!"ABI_BLOCKED".equals(state.stage))
            throw new IOException("当前没有需要补采的 ABI 阻断");
        long run=state.json.getLong("source_run_id");
        JSONObject source=client.json("GET",StageClient.API+"/actions/runs/"+run,null,200);
        if(!StageClient.trusted(source,SOURCE)||!source.optString("head_sha")
                .equals(state.json.optString("source_head_sha")))
            throw new IOException("诊断来源 Run 不可信");
        JSONArray artifacts=client.json("GET",StageClient.API+"/actions/runs/"+run+
                "/artifacts?per_page=100",null,200).getJSONArray("artifacts");
        String name=ABI_ARTIFACT+state.build+"-"+run;
        int count=0;long artifactId=0;
        for(int i=0;i<artifacts.length();i++){
            JSONObject a=artifacts.getJSONObject(i);
            if(name.equals(a.optString("name"))&&!a.optBoolean("expired")){
                artifactId=a.getLong("id");count++;
            }
        }
        if(count!=1)throw new IOException("补采附件不存在或已过期，请到 GitHub 查看来源记录");
        JSONObject task=client.bundledJson(artifactId,TASK,16384);
        return validate(task,state,source);
    }
}
