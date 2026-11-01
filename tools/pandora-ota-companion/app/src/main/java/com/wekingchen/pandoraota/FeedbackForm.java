package com.wekingchen.pandoraota;

import org.json.JSONObject;

/** Exact inputs of the existing feedback workflow; automation never supplies human attestations. */
final class FeedbackForm {
    static JSONObject inputs(long source, String sha, String result, DeviceEvidence evidence,
                             String expectedBuild, String expectedUname, boolean recovered,
                             boolean confirmedImage, boolean confirmedDesktop, boolean confirmedModules,
                             String note, String requestId) throws Exception {
        if(source<=0 || sha==null || !sha.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("请先核对来源 Run 和待测 IMG 的 SHA-256");
        if(!requestId.matches("[a-f0-9]{32}")) throw new IllegalArgumentException("反馈编号无效");
        if(!"pass".equals(result) && !"fail".equals(result)) throw new IllegalArgumentException("请选择测试通过或测试失败");
        if(!confirmedImage) throw new IllegalArgumentException("请确认电脑实际测试的是所列镜像及校验值");
        if(note.length()>1000) throw new IllegalArgumentException("补充说明请控制在 1000 字以内");
        boolean pass="pass".equals(result);
        if(pass && (recovered || evidence==null || !evidence.bootReady() || !confirmedDesktop || !confirmedModules))
            throw new IllegalArgumentException("测试通过必须取得 pandora 启动完成证据，并由你确认桌面和关键模块、基础功能正常");
        String build=recovered||evidence==null?"":evidence.build;
        String uname=recovered||evidence==null?"":evidence.uname;
        if(!recovered) {
            if(!build.matches("OS[0-9]+\\.[0-9.]+[A-Z0-9]+") || !uname.matches("6\\.12\\.[0-9]+-android16-6-[A-Za-z0-9_.-]+"))
                throw new IllegalArgumentException("请重新读取本机信息；如未能进入待测系统，请选择已恢复选项");
            if(!expectedBuild.equals(build) || (!expectedUname.isEmpty() && !expectedUname.equals(uname)))
                throw new IllegalArgumentException("当前 build / uname 与候选不一致；恢复后环境不能当作待测证据");
        }
        return new JSONObject().put("source_run_id",Long.toString(source)).put("tested_boot_sha256",sha)
                .put("result",result).put("observed_build",build).put("observed_uname",uname)
                .put("confirmed_boot_completed",Boolean.toString(!recovered && evidence!=null && evidence.bootReady() && confirmedDesktop))
                .put("confirmed_modules",Boolean.toString(!recovered && confirmedModules))
                .put("note",note).put("client_request_id",requestId);
    }
}
