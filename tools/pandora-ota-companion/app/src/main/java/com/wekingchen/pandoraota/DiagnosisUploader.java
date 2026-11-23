package com.wekingchen.pandoraota;

import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.UUID;

/** Explicit, small JSON-only GitHub Draft upload; never reuses the OTA stock-intake event. */
final class DiagnosisUploader {
    static final String REPO="wekingchen/GKI_KernelSU_SUSFS";
    static final String WORKFLOW="pandora-os4-ota-diagnostic-intake.yml";
    static final int MAX_BYTES=32768;
    interface Transport { HttpURLConnection open(URL url)throws Exception; }
    private static final Transport LIVE=url->(HttpURLConnection)url.openConnection();
    static final class Receipt {
        final long releaseId,assetId,sourceRun;
        final String sha,releaseUrl,tag;
        final boolean dispatched;
        Receipt(long releaseId,long assetId,long run,String sha,String releaseUrl,String tag,boolean dispatched){
            this.releaseId=releaseId;this.assetId=assetId;sourceRun=run;
            this.sha=sha;this.releaseUrl=releaseUrl;this.tag=tag;this.dispatched=dispatched;
        }
    }
    private final String token;
    private final Transport transport;
    DiagnosisUploader(String repo,String token){this(repo,token,LIVE);}
    DiagnosisUploader(String repo,String token,Transport transport){
        if(!REPO.equals(repo)||token==null||token.isEmpty())
            throw new IllegalArgumentException("请先配置可信 GitHub 仓库与授权令牌");
        this.token=token;this.transport=transport;
    }
    Receipt upload(JSONObject evidence)throws Exception{
        if(!DiagnosisCollector.SCHEMA.equals(evidence.optString("schema"))
                ||evidence.optBoolean("device_write_allowed",true)
                ||evidence.optBoolean("safe_to_flash",true)
                ||evidence.optBoolean("lkg_promotion",true))
            throw new IOException("诊断证据不是安全的只读格式");
        long run=evidence.optLong("source_run_id");
        String build=evidence.optString("stock_build");
        if(run<=0||!build.matches("OS[0-9]+\\.[0-9.]+[A-Z0-9]+"))
            throw new IOException("补采证据缺少可信来源信息");
        byte[] bytes=(evidence.toString(2)+"\n").getBytes(StandardCharsets.UTF_8);
        if(bytes.length<=0||bytes.length>MAX_BYTES)throw new IOException("补采内容超过 32 KiB 上限");
        String digest=sha256(bytes);
        String tag="pandora-ota-diagnostic-"+run+"-"+UUID.randomUUID().toString().replace("-","");
        JSONObject releaseReq=new JSONObject().put("tag_name",tag)
                .put("target_commitish","dev").put("draft",true).put("prerelease",true)
                .put("name","Pandora OTA read-only diagnosis / pending validation")
                .put("body","Unverified read-only diagnosis. Keep draft; NOT an OEM ABI gate pass or boot authorization.");
        String api="https://api.github.com/repos/"+REPO;
        JSONObject release=requestJson(api+"/releases","POST",releaseReq.toString().getBytes(StandardCharsets.UTF_8),201);
        String template=release.getString("upload_url");
        String base=template.split("\\{",2)[0];
        URL check=new URL(base);
        if(!"https".equals(check.getProtocol())||!"uploads.github.com".equals(check.getHost())
                ||check.getUserInfo()!=null||check.getPort()!=-1&&check.getPort()!=443
                ||!check.getPath().startsWith("/repos/"+REPO+"/releases/"+release.getLong("id")+"/assets"))
            throw new IOException("GitHub 上传地址未经过验证");
        JSONObject asset=requestJson(base+"?name=diagnostic-evidence.json","POST",bytes,201);
        if(asset.optLong("size")!=bytes.length)throw new IOException("GitHub 已收文件大小与本地不一致，请保留原件");
        Receipt provisional=new Receipt(release.getLong("id"),asset.getLong("id"),run,digest,
                release.optString("html_url"),tag,false);
        boolean notified;
        try{notifyIntake(provisional);}catch(Exception e){notified=false;return new Receipt(
                provisional.releaseId,provisional.assetId,run,digest,provisional.releaseUrl,tag,false);}
        notified=true;
        return new Receipt(provisional.releaseId,provisional.assetId,run,digest,provisional.releaseUrl,tag,notified);
    }
    void notifyIntake(Receipt receipt)throws Exception{
        JSONObject inputs=new JSONObject().put("source_run_id",Long.toString(receipt.sourceRun))
                .put("release_id",Long.toString(receipt.releaseId))
                .put("asset_id",Long.toString(receipt.assetId))
                .put("evidence_sha256",receipt.sha);
        JSONObject request=new JSONObject().put("ref","dev").put("inputs",inputs);
        requestJson("https://api.github.com/repos/"+REPO+"/actions/workflows/"+WORKFLOW+"/dispatches",
                "POST",request.toString().getBytes(StandardCharsets.UTF_8),204);
    }
    private JSONObject requestJson(String address,String verb,byte[] bytes,int expected)throws Exception{
        URL url=new URL(address);
        String host=url.getHost();
        if(!"https".equals(url.getProtocol())||url.getUserInfo()!=null
                ||(url.getPort()!=-1&&url.getPort()!=443)
                ||!("api.github.com".equals(host)||"uploads.github.com".equals(host)))
            throw new IOException("不允许向 GitHub 以外的服务器上传诊断信息");
        HttpURLConnection connection=transport.open(url);
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(15000);connection.setReadTimeout(30000);
        try {
            connection.setRequestMethod(verb);
            connection.setRequestProperty("Authorization","Bearer "+token);
            connection.setRequestProperty("Accept","application/vnd.github+json");
            connection.setRequestProperty("X-GitHub-Api-Version","2022-11-28");
            connection.setRequestProperty("User-Agent","pandora-ota-companion/"+BuildConfig.VERSION_NAME);
            connection.setRequestProperty("Content-Type",host.equals("uploads.github.com")?
                    "application/json":"application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            connection.setDoOutput(true);
            try(OutputStream out=connection.getOutputStream()){out.write(bytes);}
            int status=connection.getResponseCode();
            if(status!=expected)throw new IOException("GitHub 接收诊断请求失败 HTTP "+status);
            if(expected==204)return new JSONObject();
            try(InputStream in=connection.getInputStream()){
                ByteArrayOutputStream data=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;
                while((n=in.read(buf))!=-1){
                    if(data.size()+n>128*1024)throw new IOException("GitHub 响应过长");
                    data.write(buf,0,n);
                }
                return new JSONObject(data.toString(StandardCharsets.UTF_8.name()));
            }
        }finally{connection.disconnect();}
    }
    private static String sha256(byte[] bytes)throws Exception{
        StringBuilder result=new StringBuilder();
        for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))
            result.append(String.format(Locale.ROOT,"%02x",b&255));
        return result.toString();
    }
}
