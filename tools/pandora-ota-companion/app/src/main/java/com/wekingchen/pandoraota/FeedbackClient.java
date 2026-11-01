package com.wekingchen.pandoraota;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;

/** Only dispatches the original trusted dev workflow. No device-control operations. */
final class FeedbackClient {
    static final String WORKFLOW="xiaomi-sm8850-os4-ota-test-feedback.yml";
    static final String SOURCE="xiaomi-sm8850-os4-ota-auto-candidate.yml";
    static final String TITLE="Pandora OTA feedback / ";
    interface Transport { HttpURLConnection open(URL url) throws Exception; }
    private final Transport transport;
    private final String repo,token,api;
    FeedbackClient(String repo,String token) { this(repo,token,url -> (HttpURLConnection)url.openConnection()); }
    FeedbackClient(String repo,String token,Transport transport) {
        if(!"wekingchen/GKI_KernelSU_SUSFS".equals(repo)) throw new IllegalArgumentException("真机反馈仅支持 wekingchen/GKI_KernelSU_SUSFS，请检查设置中的仓库");
        if(token==null||token.trim().isEmpty()) throw new IllegalArgumentException("请先在设置中配置 PAT：Contents 读写、Actions 读写");
        this.repo=repo;this.token=token;this.transport=transport;api="https://api.github.com/repos/"+repo;
    }
    static final class Candidate {
        final long run; final String build,sha,uname,filename;
        Candidate(long run,String build,String sha,String uname,String filename) {
            this.run=run;this.build=build;this.sha=sha;this.uname=uname;this.filename=filename;
        }
        String label() { return build+" · #"+run; }
        JSONObject json() throws Exception {
            return new JSONObject().put("run",run).put("build",build).put("sha",sha).put("uname",uname).put("filename",filename);
        }
        static Candidate from(JSONObject j) { return new Candidate(j.optLong("run"),j.optString("build"),j.optString("sha"),j.optString("uname"),j.optString("filename")); }
    }
    List<Candidate> candidates() throws Exception {
        JSONArray runs=json("GET",api+"/actions/workflows/"+SOURCE+"/runs?branch=dev&status=success&per_page=15",null,200).getJSONArray("workflow_runs");
        List<Candidate> result=new ArrayList<>();
        for(int i=0;i<runs.length();i++) {
            JSONObject run=runs.getJSONObject(i);
            if(!validSource(run)) continue;
            Candidate c=candidate(run.getLong("id"),false);
            if(c!=null) result.add(c);
        }
        return result;
    }
    private static boolean validSource(JSONObject run) {
        String event=run.optString("event");
        return "dev".equals(run.optString("head_branch")) && "completed".equals(run.optString("status"))
                && "success".equals(run.optString("conclusion"))
                && (".github/workflows/"+SOURCE).equals(run.optString("path"))
                && ("release".equals(event)||"schedule".equals(event)||"workflow_dispatch".equals(event));
    }
    Candidate candidate(long run,boolean loadMetadata) throws Exception {
        if(run<=0) throw new IllegalArgumentException("Run ID 应为正整数");
        JSONObject source=json("GET",api+"/actions/runs/"+run,null,200);
        if(source.optLong("id")!=run||!validSource(source)) throw new IOException("来源不是 dev 上已成功完成的 OTA 候选工作流");
        JSONArray assets=json("GET",api+"/actions/runs/"+run+"/artifacts?per_page=100",null,200).getJSONArray("artifacts");
        String build=""; int bases=0,tests=0; long mobile=0;
        for(int i=0;i<assets.length();i++) {
            JSONObject a=assets.getJSONObject(i);if(a.optBoolean("expired")) continue;
            String n=a.optString("name"), suffix="-"+run, prefix="pandora-OTA-OEM-ABI-TESTBOOT-";
            if(n.startsWith(prefix)&&n.endsWith(suffix)) { tests++;build=n.substring(prefix.length(),n.length()-suffix.length()); }
            if(n.startsWith("pandora-OTA-UNVERIFIED-GKI-")&&n.endsWith(suffix)) bases++;
        }
        if(tests!=1||bases!=1||!build.matches("OS[0-9]+\\.[0-9.]+[A-Z0-9]+")) {
            if(loadMetadata) throw new IOException("候选附件缺失、重复或已过期");
            return null;
        }
        int matchingBase=0,mobiles=0;
        for(int i=0;i<assets.length();i++) {
            JSONObject a=assets.getJSONObject(i);if(a.optBoolean("expired"))continue;
            if(("pandora-OTA-UNVERIFIED-GKI-"+build+"-"+run).equals(a.optString("name"))) matchingBase++;
            if(("pandora-OTA-MOBILE-FEEDBACK-"+build+"-"+run).equals(a.optString("name"))) { mobiles++;mobile=a.optLong("id"); }
        }
        if(matchingBase!=1||mobiles>1) throw new IOException("候选 GKI 与待测 boot 来源不一致");
        if(!loadMetadata) return new Candidate(run,build,"","","");
        if(mobile==0) return new Candidate(run,build,"","",""); // legacy: exact SHA must be supplied manually
        JSONObject manifest=manifest(mobile);
        return parseManifest(manifest,run,build,source.optString("head_sha"),repo);
    }
    static Candidate parseManifest(JSONObject j,long run,String build,String head,String repo) throws Exception {
        String sha=j.optString("tested_boot_sha256"),uname=j.optString("expected_uname"),filename=j.optString("filename");
        if(!"pandora-mobile-feedback-v1".equals(j.optString("schema"))||!repo.equals(j.optString("repository"))
                ||j.optLong("source_run_id")!=run||!head.equals(j.optString("source_head_sha"))
                ||!build.equals(j.optString("build"))||!"pandora".equals(j.optString("device"))
                ||!j.optBoolean("eligible_for_fastboot_boot")||!sha.matches("[a-f0-9]{64}")
                ||!uname.matches("6\\.12\\.[0-9]+-android16-6-[A-Za-z0-9_.-]+")
                ||!filename.equals("pandora-"+build+"-UNVERIFIED-FASTBOOT-BOOT-ONLY.img"))
            throw new IOException("手机反馈元数据与候选来源不一致");
        return new Candidate(run,build,sha,uname,filename);
    }
    void submit(JSONObject inputs) throws Exception {
        if(!inputs.optString("client_request_id").matches("[a-f0-9]{32}")) throw new IllegalArgumentException("反馈编号无效");
        json("POST",api+"/actions/workflows/"+WORKFLOW+"/dispatches",new JSONObject().put("ref","dev").put("inputs",inputs),204);
    }
    JSONObject findRun(String requestId) throws Exception {
        if(!requestId.matches("[a-f0-9]{32}")) throw new IllegalArgumentException("反馈编号无效");
        for(int page=1;page<=3;page++) {
            JSONArray runs=json("GET",api+"/actions/workflows/"+WORKFLOW+"/runs?event=workflow_dispatch&per_page=100&page="+page,null,200).getJSONArray("workflow_runs");
            for(int i=0;i<runs.length();i++) {
                JSONObject run=runs.getJSONObject(i);
                if((TITLE+requestId).equals(run.optString("display_title"))&&"dev".equals(run.optString("head_branch"))
                        &&"workflow_dispatch".equals(run.optString("event"))&&(".github/workflows/"+WORKFLOW).equals(run.optString("path"))) return run;
            }
            if(runs.length()<100) break;
        }
        return null;
    }
    JSONObject readRun(long runId,String requestId) throws Exception {
        JSONObject run=json("GET",api+"/actions/runs/"+runId,null,200);
        if(run.optLong("id")!=runId||!(TITLE+requestId).equals(run.optString("display_title"))
                ||!"dev".equals(run.optString("head_branch"))||!"workflow_dispatch".equals(run.optString("event"))
                ||!(".github/workflows/"+WORKFLOW).equals(run.optString("path"))) throw new IOException("反馈运行身份不匹配");
        return run;
    }
    static final class ApiException extends IOException {
        final int status;
        ApiException(int status,String message) { super(message);this.status=status; }
    }
    private JSONObject json(String method,String url,JSONObject data,int expected) throws Exception {
        HttpURLConnection c=connection(new URL(url),true);
        try {
            c.setRequestMethod(method);
            if(data!=null) {
                byte[] bytes=data.toString().getBytes(StandardCharsets.UTF_8);c.setDoOutput(true);
                c.setRequestProperty("Content-Type","application/json");c.setFixedLengthStreamingMode(bytes.length);
                try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            }
            int status=c.getResponseCode();
            if(status!=expected) throw new ApiException(status,"GitHub HTTP "+status+(status==403||status==404?"：请确认目标仓库的 PAT 已启用 Actions 读写权限":"，请检查网络及令牌"));
            if(expected==204)return new JSONObject();
            try(InputStream in=c.getInputStream()){return new JSONObject(new String(read(in,1024*1024),StandardCharsets.UTF_8));}
        } finally {c.disconnect();}
    }
    private HttpURLConnection connection(URL url,boolean authenticated) throws Exception {
        String host=url.getHost();
        if(!"https".equals(url.getProtocol())||url.getUserInfo()!=null||(url.getPort()!=-1&&url.getPort()!=443)
                ||(authenticated&&!"api.github.com".equals(host))) throw new IOException("非预期的 GitHub 地址");
        HttpURLConnection c=transport.open(url);c.setInstanceFollowRedirects(false);c.setConnectTimeout(15000);c.setReadTimeout(20000);c.setUseCaches(false);
        c.setRequestProperty("Accept","application/vnd.github+json");c.setRequestProperty("X-GitHub-Api-Version","2022-11-28");
        c.setRequestProperty("User-Agent","pandora-ota-companion/0.12.0");
        if(authenticated)c.setRequestProperty("Authorization","Bearer "+token);
        return c;
    }
    private JSONObject manifest(long id) throws Exception {
        URL url=new URL(api+"/actions/artifacts/"+id+"/zip");byte[] archive=null;
        for(int hop=0;hop<4;hop++) {
            HttpURLConnection c=connection(url,hop==0);
            try {
                int status=c.getResponseCode();
                if(status==200) {try(InputStream in=c.getInputStream()){archive=read(in,256*1024);}break;}
                if(status!=302&&status!=301&&status!=307)throw new IOException("读取候选元数据 HTTP "+status);
                URL target=new URL(url,c.getHeaderField("Location"));String host=target.getHost().toLowerCase(Locale.ROOT);
                if(!host.endsWith(".blob.core.windows.net")&&!host.endsWith(".githubusercontent.com")
                        &&!host.endsWith(".s3.amazonaws.com")&&!"api.github.com".equals(host)) throw new IOException("候选下载重定向异常");
                url=target;
            } finally {c.disconnect();}
        }
        if(archive==null)throw new IOException("候选元数据下载重定向过多");
        JSONObject result=null;int entries=0;
        try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry e;while((e=zip.getNextEntry())!=null) {
                if(++entries>4||e.isDirectory()||!"mobile-test-feedback.json".equals(e.getName())||result!=null)
                    throw new IOException("候选元数据附件格式异常");
                result=new JSONObject(new String(read(zip,16384),StandardCharsets.UTF_8));
            }
        }
        if(result==null)throw new IOException("缺少手机反馈元数据");return result;
    }
    private static byte[] read(InputStream in,int max) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;
        while((n=in.read(b))!=-1){if(out.size()+n>max)throw new IOException("GitHub 响应超过读取上限");out.write(b,0,n);}return out.toByteArray();
    }
}
