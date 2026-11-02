package com.wekingchen.pandoraota;

import org.json.*;
import android.util.Base64;
import java.io.IOException;
import java.security.MessageDigest;
import java.util.*;

/** Read-only status consumer. Bind every snapshot to trusted runs and the live input. */
final class StageClient {
    static final String REPO="wekingchen/GKI_KernelSU_SUSFS", WORKFLOW="pandora-os4-stage-status.yml";
    static final String API="https://api.github.com/repos/"+REPO;
    static final List<String> STAGES=Arrays.asList("NO_NEW_OTA","GKI_BUILT","ABI_BLOCKED","TESTBOOT_READY",
            "WAITING_HUMAN","BASELINE_VERIFIED","CUSTOM_UNVERIFIED","LKG_ARCHIVED");
    final FeedbackClient client;
    StageClient(String repo,String token){client=new FeedbackClient(repo,token);}
    StageClient(String repo,String token,FeedbackClient.Transport transport){client=new FeedbackClient(repo,token,transport);}
    static final class State {
        final JSONObject json; final String stage,build,detail,verifiedAt; final long run;
        State(JSONObject j)throws Exception {this(j,"");}
        State(JSONObject j,String producedAt)throws Exception {
            json=j;stage=j.getString("stage");build=j.getString("build");detail=j.optString("detail");
            run=j.getLong("producer_run_id");verifiedAt=localTime(producedAt);
        }
        static String localTime(String utc){
            try {
                return java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm",java.util.Locale.CHINA)
                        .withZone(java.time.ZoneId.systemDefault()).format(java.time.Instant.parse(utc));
            } catch (java.time.DateTimeException e) {return "未取得";}
        }
        String lkgGeneration(){
            if(!"LKG_ARCHIVED".equals(stage))return "";
            JSONArray proofs=json.optJSONArray("release_assets");
            if(proofs==null)return "";
            String generation="";
            for(int i=0;i<proofs.length();i++){
                String tag=proofs.optJSONObject(i)==null?"":proofs.optJSONObject(i).optString("tag");
                if(!tag.matches("pandora-os4-lkg-gen[1-9][0-9]*"))continue;
                String value=tag.substring("pandora-os4-lkg-gen".length());
                if(!generation.isEmpty()&&!generation.equals(value))return "";
                generation=value;
            }
            return generation.isEmpty()?"":"Gen "+generation;
        }
        String friendlyDetail(){
            if("LKG_ARCHIVED".equals(stage))
                return "该系统版本的稳定内核已通过人工确认并完成 GitHub 长期归档；这不代表已校验本机运行镜像的文件哈希。";
            return detail.replace("NOOP","无需重复处理");
        }
        String technicalDetails(){
            return "阶段："+stage+"\n系统："+build+"\n快照 Run #"+run
                    +"\n输入 Asset #"+json.optLong("stock_asset_id")
                    +"\n来源 Run #"+json.optLong("source_run_id")
                    +"\n快照 Git SHA："+json.optString("producer_head_sha")
                    +"\n固定输入 SHA256："+json.optString("stock_input_sha256");
        }
        String title(){
            switch(stage){
                case "NO_NEW_OTA":return "没有新 OTA";
                case "GKI_BUILT":return "GKI 已构建";
                case "ABI_BLOCKED":return "OEM ABI 检查阻断";
                case "TESTBOOT_READY":return "待测包已生成";
                case "WAITING_HUMAN":return "等待真机测试";
                case "BASELINE_VERIFIED":return "开发基线已验证";
                case "CUSTOM_UNVERIFIED":return "自定义内核待验证";
                case "LKG_ARCHIVED":return lkgGeneration().isEmpty()?"稳定 LKG 已长期归档":"已归档稳定内核 · "+lkgGeneration();
                default:return "状态未验证";
            }
        }
        String next(){
            switch(stage){
                case "GKI_BUILT":return "查看 OEM ABI 结果；附件过期时从永久候选显式恢复。";
                case "ABI_BLOCKED":return "先处理 ABI 阻断，不能进入真机启动测试。";
                case "TESTBOOT_READY":case "WAITING_HUMAN":return "由电脑 fastboot boot，手机测试后填写真机反馈。";
                case "BASELINE_VERIFIED":return "可以开始同版本功能适配；基线验证不代表自定义内核稳定。";
                case "CUSTOM_UNVERIFIED":return "先核对版本并测试；稳定后由你明确确认晋升 LKG。";
                case "LKG_ARCHIVED":return "仅适用于所列版本；更新系统后重新走 OTA 验证流程。";
                default:return "等待新 OTA；工作流成功本身不代表产生待测包。";
            }
        }
    }
    private JSONObject get(String path)throws Exception{return client.json("GET",API+"/"+path,null,200);}
    static void require(boolean ok,String message)throws IOException{if(!ok)throw new IOException(message);}
    static boolean trusted(JSONObject run,String workflow){
        String event=run.optString("event");
        return "dev".equals(run.optString("head_branch"))&&"completed".equals(run.optString("status"))
            &&"success".equals(run.optString("conclusion"))&&(".github/workflows/"+workflow).equals(run.optString("path"))
            &&(Arrays.asList("workflow_dispatch","workflow_run","schedule","release").contains(event)
                ||(WORKFLOW.equals(workflow)&&"push".equals(event)))
            &&run.optString("head_sha").matches("[a-f0-9]{40}");
    }
    static void validateEnvelope(JSONObject j,JSONObject run,JSONObject fixed)throws Exception{
        String stage=j.optString("stage"),sha=j.optString("stock_input_sha256");
        require("pandora-os4-stage-v1".equals(j.optString("schema"))&&REPO.equals(j.optString("repository"))
            &&"pandora".equals(j.optString("device"))&&STAGES.contains(stage)
            &&j.optString("build").matches("OS[0-9]+\\.[0-9.]+[A-Z0-9]+")
            &&j.has("safe_to_flash")&&!j.getBoolean("safe_to_flash")
            &&j.optLong("producer_run_id")>0&&j.optLong("producer_run_id")==run.optLong("id")
            &&j.optString("producer_head_sha").equals(run.optString("head_sha"))&&trusted(run,WORKFLOW)
            &&sha.matches("[a-f0-9]{64}"),"阶段状态的来源身份不匹配");
        require("pandora-os4-stock-input".equals(fixed.optString("tag_name"))&&!fixed.optBoolean("draft"),"固定输入身份异常");
        JSONArray assets=fixed.getJSONArray("assets");int count=0;
        for(int i=0;i<assets.length();i++){
            JSONObject a=assets.getJSONObject(i);
            if(a.optString("name").endsWith("xm.zip")){
                count++;
                require(a.optLong("id")==j.optLong("stock_asset_id")&&("sha256:"+sha).equals(a.optString("digest")),
                    "固定 OTA 输入已变化，请等待新的阶段状态");
            }
        }
        require(count==1,"固定输入事务待恢复，暂不展示阶段结论");
        JSONArray proofs=j.getJSONArray("release_assets");
        require(proofs.length()<=8&&("NO_NEW_OTA".equals(stage)||proofs.length()>=2)
            &&(!"LKG_ARCHIVED".equals(stage)||proofs.length()>=3),"缺少候选/归档校验证据");
    }
    State latest()throws Exception{
        JSONArray runs=get("actions/workflows/"+WORKFLOW+"/runs?branch=dev&per_page=1").getJSONArray("workflow_runs");
        require(runs.length()==1,"尚无阶段快照，请先运行全链路可信阶段状态工作流");
        JSONObject run=runs.getJSONObject(0);
        require(trusted(run,WORKFLOW),"最新阶段检查尚未成功完成；请稍后刷新并查看 GitHub 运行");
        long id=run.getLong("id"),artifactId=0;int count=0;
        JSONArray arts=get("actions/runs/"+id+"/artifacts?per_page=100").getJSONArray("artifacts");
        for(int i=0;i<arts.length();i++){
            JSONObject a=arts.getJSONObject(i);
            if(("pandora-OTA-STAGE-"+id).equals(a.optString("name"))&&!a.optBoolean("expired")){count++;artifactId=a.getLong("id");}
        }
        require(count==1,"阶段快照缺失、重复或已过期，请重新生成");
        JSONObject j=client.artifactJson(artifactId,"os4-stage.json",32768);
        validateEnvelope(j,run,get("releases/tags/pandora-os4-stock-input"));
        Set<Long> seen=new HashSet<>();JSONArray proofs=j.getJSONArray("release_assets");
        for(int i=0;i<proofs.length();i++){
            JSONObject p=proofs.getJSONObject(i);String tag=p.getString("tag"),digest=p.getString("sha256");
            require(tag.equals("pandora-os4-ota-candidate-"+j.getString("build"))||tag.matches("pandora-os4-lkg-gen[1-9][0-9]*"),"非预期的归档来源");
            require(digest.matches("[a-f0-9]{64}")&&seen.add(p.getLong("id")),"归档证据重复或 SHA 无效");
            JSONObject release=get("releases/tags/"+tag);require(!release.optBoolean("draft"),"归档尚未发布");
            JSONArray assets=release.getJSONArray("assets");int matches=0;
            for(int n=0;n<assets.length();n++){
                JSONObject a=assets.getJSONObject(n);
                if(a.optLong("id")==p.getLong("id")&&p.getString("name").equals(a.optString("name"))
                        &&("sha256:"+digest).equals(a.optString("digest")))matches++;
            }
            require(matches==1,"归档资产或 SHA 已变化");
        }
        JSONObject source=get("actions/runs/"+j.getLong("source_run_id"));
        require(source.optLong("id")==j.getLong("source_run_id")
                &&source.optString("head_sha").equals(j.getString("source_head_sha"))
                &&(trusted(source,FeedbackClient.SOURCE)||("LKG_ARCHIVED".equals(j.getString("stage"))
                &&trusted(source,"xiaomi-sm8850-os4-custom.yml"))),"阶段证据来源运行不匹配");
        String stage=j.getString("stage");
        if(stage.equals("TESTBOOT_READY")||stage.equals("WAITING_HUMAN")){
            FeedbackClient.Candidate c=client.candidate(j.getLong("source_run_id"),true);
            require(c.build.equals(j.getString("build"))&&c.sha.equals(j.getString("tested_boot_sha256"))
                    &&!c.sha.isEmpty(),"待测包与阶段状态不一致");
        }
        if(stage.equals("BASELINE_VERIFIED")||stage.equals("CUSTOM_UNVERIFIED")){
            JSONObject blob=get("contents/.github/config/ota-verified/"+j.getString("build")+"/verification.json?ref="+j.getString("producer_head_sha"));
            byte[] bytes=Base64.decode(blob.getString("content"),Base64.DEFAULT);
            StringBuilder hex=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))hex.append(String.format(Locale.ROOT,"%02x",b&255));
            require(hex.toString().equals(j.getString("baseline_record_sha256")),"基线记录与状态来源提交不一致");
        }
        return new State(j,run.optString("created_at"));
    }
}
