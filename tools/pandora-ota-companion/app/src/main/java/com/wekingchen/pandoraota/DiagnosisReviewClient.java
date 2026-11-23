package com.wekingchen.pandoraota;

import org.json.*;
import java.io.IOException;

/**
 * Read-only verification of a diagnostic review. A successful workflow run
 * alone is not a verified REVIEW_REQUIRED receipt: inspect the exact artifact.
 */
final class DiagnosisReviewClient {
    static final String WORKFLOW="pandora-os4-ota-diagnostic-intake.yml";
    static final String TITLE="Pandora OTA diagnosis / source-";
    static final String API=StageClient.API;
    private final FeedbackClient github;
    DiagnosisReviewClient(String repo,String token){github=new FeedbackClient(repo,token);}
    DiagnosisReviewClient(String repo,String token,FeedbackClient.Transport transport){
        github=new FeedbackClient(repo,token,transport);
    }
    static final class Status {
        final String state,description;
        final long runId;
        Status(String s,String text,long id){state=s;description=text;runId=id;}
    }
    static String title(DiagnosisUploader.Receipt receipt){
        return TITLE+receipt.sourceRun+" / release-"+receipt.releaseId+" / asset-"+receipt.assetId;
    }
    Status latest(DiagnosisUploader.Receipt receipt,DiagnosisClient.Task task)throws Exception {
        if(receipt==null||task==null||!receipt.dispatched||receipt.sourceRun!=task.run
                ||receipt.releaseId<=0||receipt.assetId<=0
                ||!receipt.sha.matches("[a-f0-9]{64}"))
            throw new IOException("诊断审核请求来源未确认");
        String expected=title(receipt);
        JSONObject run=null;
        // GitHub returns newest first. Find an exact receipt in a bounded
        // window instead of assuming it is always among the latest 100 runs.
        for(int page=1;page<=5;page++){
            JSONArray runs=github.json("GET",API+"/actions/workflows/"+WORKFLOW+
                    "/runs?event=workflow_dispatch&branch=dev&per_page=100&page="+page,null,200)
                    .getJSONArray("workflow_runs");
            for(int i=0;i<runs.length();i++){
                JSONObject candidate=runs.getJSONObject(i);
                if(!expected.equals(candidate.optString("display_title")))continue;
                if(!"dev".equals(candidate.optString("head_branch"))||
                        !"workflow_dispatch".equals(candidate.optString("event"))||
                        !(".github/workflows/"+WORKFLOW).equals(candidate.optString("path"))||
                        !candidate.optString("head_sha").matches("[a-f0-9]{40}"))
                    throw new IOException("诊断审核 Run 的来源不可信");
                if(run==null||candidate.getLong("id")>run.getLong("id"))run=candidate;
            }
            if(run!=null||runs.length()<100)break;
        }
        if(run==null)return new Status("QUEUED","审核已通知 GitHub，尚未建立运行记录；请稍后刷新。",0);
        long id=run.getLong("id");
        String phase=run.optString("status");
        if("queued".equals(phase)||"waiting".equals(phase)||"requested".equals(phase))
            return new Status("QUEUED","GitHub 已收到诊断审核任务，正在排队。",id);
        if("in_progress".equals(phase)||"pending".equals(phase))
            return new Status("RUNNING","GitHub 正在核验来源、固件版本和证据完整性。",id);
        if(!"completed".equals(phase))throw new IOException("未知的 GitHub 运行状态");
        if(!"success".equals(run.optString("conclusion")))
            return new Status("FAILED","审核未通过；请查看 GitHub 运行中的具体错误。不会解锁 ABI。",id);
        JSONArray artifacts=github.json("GET",API+"/actions/runs/"+id+"/artifacts?per_page=100",null,200)
                .getJSONArray("artifacts");
        String name="pandora-OTA-V2-DIAGNOSTIC-REVIEW-"+receipt.sourceRun+"-"+id;
        long artifact=0;int count=0;
        for(int i=0;i<artifacts.length();i++){
            JSONObject a=artifacts.getJSONObject(i);
            if(name.equals(a.optString("name"))&&!a.optBoolean("expired")){
                artifact=a.getLong("id");count++;
            }
        }
        if(count!=1||artifact<=0)throw new IOException("审核成功但核验附件缺失或过期，不能视为已审核");
        JSONObject proof=github.bundledJson(artifact,"diagnostic-review.json",16384);
        if(!"pandora-ota-diagnostic-review-v1".equals(proof.optString("schema"))
                ||!"REVIEW_REQUIRED".equals(proof.optString("review"))
                ||proof.optLong("source_run_id")!=task.run
                ||!task.build.equals(proof.optString("stock_build"))
                ||!task.stockSha.equals(proof.optString("stock_input_sha256"))
                ||!receipt.sha.equals(proof.optString("payload_sha256"))
                ||proof.optBoolean("safe_to_flash",true)
                ||proof.optBoolean("oem_gate_unlocked",true)
                ||proof.optBoolean("lkg_promotion",true))
            throw new IOException("审核证明与本次补采或安全状态不一致");
        String next="";
        try{
            JSONObject plan=github.bundledJson(artifact,"diagnostic-recovery-plan.json",32768);
            if("pandora-ota-v2-recovery-plan-v1".equals(plan.optString("schema"))&&
                    plan.optLong("source_run_id")==task.run&&
                    task.build.equals(plan.optString("stock_build"))&&
                    task.stockSha.equals(plan.optString("stock_input_sha256"))&&
                    receipt.sha.equals(plan.optString("evidence_sha256"))&&
                    !plan.optBoolean("automatic_rebuild_authorized",true)&&
                    !plan.optBoolean("fastboot_boot_authorized",true)&&
                    !plan.optBoolean("lkg_promotion_authorized",true)){
                JSONArray actions=plan.optJSONArray("actions");
                if(actions!=null&&actions.length()>0){
                    JSONObject first=actions.optJSONObject(0);
                    if(first!=null){
                        String title=first.optString("title");
                        if(title.length()>0&&title.length()<50)
                            next="\n建议先做："+title+"；完整步骤见 GitHub 审核记录。";
                    }
                }
            }
        }catch(Exception ignored){
            // Old review artifacts predate the optional human-readable plan.
            // Never treat a missing/unverified recommendation as authority.
        }
        return new Status("REVIEW_REQUIRED",
                "只读证据已核验，ABI 仍然阻断；不会自动重编、刷机或晋升 LKG。"+next,id);
    }
}
