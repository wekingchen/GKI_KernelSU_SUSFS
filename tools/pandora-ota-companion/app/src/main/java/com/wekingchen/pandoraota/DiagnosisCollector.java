package com.wekingchen.pandoraota;

import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.*;

/** Fixed local read-only observations. Never executes instructions from downloaded tasks. */
final class DiagnosisCollector {
    interface Reader { String read(String key) throws Exception; }
    static final String SCHEMA="pandora-ota-diagnostic-evidence-v1";
    private static final Set<String> MODULES=new LinkedHashSet<>(
            Arrays.asList("rust_binder","kernelsu","node_cache","zram","zsmalloc"));
    private static final Pattern HEX=Pattern.compile("^[a-f0-9]{64}$");
    private static final int MAX_OUTPUT=128*1024; // only in memory; serialized evidence remains <=32 KiB
    private DiagnosisCollector(){}

    static JSONObject capture(DiagnosisClient.Task task)throws Exception {
        return capture(task,DiagnosisCollector::localRead);
    }
    static JSONObject capture(DiagnosisClient.Task task,Reader reader)throws Exception {
        String device=clean(reader,"device",80),build=clean(reader,"build",100);
        String boot=clean(reader,"boot",8),uname=clean(reader,"uname",160);
        String slot=clean(reader,"slot",16);
        if(!"pandora".equals(device)||!task.build.equals(build)||!"1".equals(boot))
            throw new IOException("本机不属于该诊断任务的已启动 OTA 版本，禁止混用旧手机证据");
        if(!slot.matches("_[ab]"))throw new IOException("当前活动 slot 未取得，暂不能绑定采集证据");
        if(!uname.matches("[A-Za-z0-9_.+-]{8,160}"))
            throw new IOException("内核版本身份无法读取");
        JSONObject observations=new JSONObject();
        JSONObject identity=new JSONObject().put("device",device).put("build",build)
                .put("boot_completed",boot).put("slot",slot).put("uname",uname);
        observations.put("identity",identity);
        String moduleNames=clean(reader,"modules",MAX_OUTPUT);
        boolean moduleKnown=!moduleNames.isEmpty();
        Set<String> loaded=parseModuleNames(moduleNames);
        boolean partial=!moduleKnown;
        if(task.checks.contains("binder_runtime")) {
            JSONObject binder=new JSONObject();
            String impl=binderValue(clean(reader,"binder_impl",64));
            String active=binderValue(clean(reader,"binder_active_impl",64));
            binder.put("impl",impl).put("active_impl",active)
                    .put("rust_binder_loaded",moduleKnown?Boolean.valueOf(loaded.contains("rust_binder")):JSONObject.NULL)
                    .put("kernelsu_lkm_loaded",moduleKnown?Boolean.valueOf(loaded.contains("kernelsu")):JSONObject.NULL);
            String cmdline=clean(reader,"cmdline",8192);
            // Never persist or transmit the full kernel command line.
            String blacklist=findToken(cmdline,"module_blacklist");
            String eexist=findToken(cmdline,"pandora_rust_binder_eexist");
            binder.put("module_blacklist_kernelsu",blacklist.isEmpty()?JSONObject.NULL:Boolean.valueOf(Arrays.asList(blacklist.split(",")).contains("kernelsu")));
            binder.put("eexist_parameter",eexist.isEmpty()?JSONObject.NULL:Boolean.valueOf("1".equals(eexist)));
            observations.put("binder_runtime",binder);
            partial |= "UNKNOWN".equals(impl)||"UNKNOWN".equals(active)||!moduleKnown;
        }
        if(task.checks.contains("loaded_module_identity")) {
            JSONObject source=new JSONObject();
            for(String name:new String[]{"node_cache","zram","zsmalloc"}){
                JSONObject module=new JSONObject();
                module.put("loaded",moduleKnown?Boolean.valueOf(loaded.contains(name)):JSONObject.NULL);
                String note=clean(reader,"note_"+name,200).toLowerCase(Locale.ROOT);
                // Only the GNU Note digest is uploaded, never binary bytes, addresses or paths.
                note=note.split("\\s+")[0];
                if(!HEX.matcher(note).matches())note="";
                module.put("gnu_note_sha256",note.isEmpty()?JSONObject.NULL:note);
                if(moduleKnown&&loaded.contains(name)&&note.isEmpty())partial=true;
                source.put(name,module);
            }
            observations.put("loaded_module_identity",source);
        }
        JSONObject captured=new JSONObject().put("schema",SCHEMA)
                .put("repository",StageClient.REPO).put("source_run_id",task.run)
                .put("source_head_sha",task.head).put("stock_build",task.build)
                .put("stock_input_sha256",task.stockSha)
                .put("candidate_commit",task.commit)
                .put("checks",new JSONArray(task.checks))
                .put("status",partial?"PARTIAL_READ_ONLY":"CAPTURED_READ_ONLY")
                .put("captured_at_ms",System.currentTimeMillis())
                .put("observations",observations)
                .put("attestation","DEVICE_READ_ONLY_OBSERVATION_NOT_KERNEL_COMPATIBILITY_PROOF")
                .put("device_write_allowed",false).put("safe_to_flash",false)
                .put("lkg_promotion",false);
        if(captured.toString().getBytes(StandardCharsets.UTF_8).length>32768)
            throw new IOException("诊断内容超过安全上限");
        return captured;
    }
    private static String findToken(String line,String key){
        for(String item:line.split("\\s+"))if(item.startsWith(key+"="))
            return item.substring((key+"=").length()).replaceAll("[^A-Za-z0-9_,.-]","");
        return "";
    }
    private static Set<String> parseModuleNames(String content){
        Set<String> result=new LinkedHashSet<>();
        for(String line:content.split("\\n")){
            String[] tokens=line.trim().split("\\s+");
            if(tokens.length>0&&MODULES.contains(tokens[0]))result.add(tokens[0]);
        }
        return result;
    }
    private static String binderValue(String raw){
        if("c".equals(raw)||"rust".equals(raw))return raw;
        return "UNKNOWN";
    }
    private static String clean(Reader r,String key,int max){
        try{
            String s=r.read(key);
            if(s==null||s.length()>max)return "";
            return s.trim();
        }catch(Exception e){return "";}
    }
    private static String localRead(String key)throws Exception{
        switch(key){
            case "device":return process(5,"getprop","ro.product.device");
            case "build":return process(5,"getprop","ro.mi.os.version.incremental");
            case "boot":return process(5,"getprop","sys.boot_completed");
            case "slot":return process(5,"getprop","ro.boot.slot_suffix");
            case "uname":return process(5,"uname","-r");
            case "modules":
                try { return readFile("/proc/modules",MAX_OUTPUT); }
                catch(Exception ordinary) {
                    // Android sometimes blocks ordinary /proc/modules access.
                    // This literal fixed AWK expression returns *only names*,
                    // with no kernel pointers, paths, sizes or arbitrary script.
                    return process(20,"su","-c",
                            "awk '$1==\"rust_binder\" || $1==\"kernelsu\" || "+
                            "$1==\"node_cache\" || $1==\"zram\" || "+
                            "$1==\"zsmalloc\" {print $1}' /proc/modules");
                }
            case "cmdline":return readFile("/proc/cmdline",8192);
            case "binder_impl":return firstFile("/sys/module/binder_linux/parameters/impl",
                    "/sys/module/binder/parameters/impl");
            case "binder_active_impl":return firstFile("/sys/module/binder_linux/parameters/active_impl",
                    "/sys/module/binder/parameters/active_impl");
            case "note_node_cache":return noteHash("node_cache");
            case "note_zram":return noteHash("zram");
            case "note_zsmalloc":return noteHash("zsmalloc");
            default:throw new SecurityException("未授权的只读采集项目");
        }
    }
    private static String firstFile(String a,String b)throws Exception{
        try{return readFile(a,256);}catch(Exception e){return readFile(b,256);}
    }
    private static String noteHash(String name)throws Exception{
        if(!Arrays.asList("node_cache","zram","zsmalloc").contains(name))
            throw new SecurityException("模块不在允许清单内");
        // Exact, constant command and path. No server-provided command fragments.
        return process(15,"su","-c",
                "sha256sum /sys/module/"+name+"/notes/.note.gnu.build-id");
    }
    private static String readFile(String path,int max)throws Exception{
        try(InputStream in=new FileInputStream(path)){
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            byte[] buf=new byte[2048];int size;
            while((size=in.read(buf))>=0){
                if(out.size()+size>max)throw new IOException("读取内容超过限制");
                out.write(buf,0,size);
            }
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }
    private static String process(int timeout,String... args)throws Exception{
        Process p=new ProcessBuilder(args).redirectErrorStream(true).start();
        try{
            if(!p.waitFor(timeout,TimeUnit.SECONDS))throw new IOException("采集读取超时");
            if(p.exitValue()!=0)throw new IOException("只读信息暂不可用");
            return readLimited(p.getInputStream());
        }finally{p.destroyForcibly();}
    }
    private static String readLimited(InputStream stream)throws Exception{
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[1024];int n;
        while((n=stream.read(buf))>=0){
            if(out.size()+n>8192)throw new IOException("响应过长");
            out.write(buf,0,n);
        }
        return out.toString(StandardCharsets.UTF_8.name());
    }
}
