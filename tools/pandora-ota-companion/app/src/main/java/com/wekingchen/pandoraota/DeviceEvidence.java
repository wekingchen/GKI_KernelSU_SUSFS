package com.wekingchen.pandoraota;

import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** The five former adb-shell checks run locally. No reboot, fastboot or partition writes. */
final class DeviceEvidence {
    final String device, build, bootCompleted, uname, modules, moduleError;
    final long collectedAt;
    DeviceEvidence(String device, String build, String bootCompleted, String uname,
                   String modules, String moduleError, long time) {
        this.device=device; this.build=build; this.bootCompleted=bootCompleted;
        this.uname=uname; this.modules=modules; this.moduleError=moduleError; collectedAt=time;
    }
    interface Reader { String read(String name) throws Exception; }
    static DeviceEvidence collect() { return collect(name -> {
        switch (name) {
            case "device": return command(5, "getprop", "ro.product.device");
            case "build": return command(5, "getprop", "ro.mi.os.version.incremental");
            case "boot": return command(5, "getprop", "sys.boot_completed");
            case "uname": return command(5, "uname", "-r");
            case "modules":
                try (InputStream in=new FileInputStream("/proc/modules")) { return readLimited(in); }
            case "root_modules": return command(20, "su", "-c", "cat /proc/modules");
            default: throw new IOException("未知的只读检查");
        }
    }); }
    static DeviceEvidence collect(Reader reader) {
        String device=safe(reader,"device"), build=safe(reader,"build"), boot=safe(reader,"boot"), uname=safe(reader,"uname");
        String modules="", error="";
        try { modules=reader.read("modules"); }
        catch (Exception ordinary) {
            try { modules=reader.read("root_modules"); }
            catch (Exception root) { error="未取得模块列表；请检查 Root 授权后重新读取"; }
        }
        return new DeviceEvidence(device,build,boot,uname,modules,error,System.currentTimeMillis());
    }
    private static String safe(Reader reader,String name) {
        try { return reader.read(name).trim(); } catch(Exception e) { return ""; }
    }
    boolean bootReady() { return "pandora".equals(device) && "1".equals(bootCompleted); }
    JSONObject json() throws Exception {
        return new JSONObject().put("device",device).put("build",build).put("boot_completed",bootCompleted)
                .put("uname",uname).put("modules",modules).put("module_error",moduleError).put("collected_at",collectedAt);
    }
    static DeviceEvidence from(JSONObject j) {
        return new DeviceEvidence(j.optString("device"),j.optString("build"),j.optString("boot_completed"),
                j.optString("uname"),j.optString("modules"),j.optString("module_error"),j.optLong("collected_at"));
    }
    private static String command(int seconds,String... args) throws Exception {
        Process p=new ProcessBuilder(args).redirectErrorStream(true).start();
        ExecutorService reader=Executors.newSingleThreadExecutor(r -> { Thread t=new Thread(r,"feedback-read"); t.setDaemon(true); return t; });
        Future<String> output=reader.submit(() -> readLimited(p.getInputStream()));
        try {
            if(!p.waitFor(seconds,TimeUnit.SECONDS)) throw new IOException("只读检查超时");
            String text=output.get(2,TimeUnit.SECONDS);
            if(p.exitValue()!=0) throw new IOException("只读检查未完成");
            return text;
        } finally { p.destroyForcibly(); output.cancel(true); reader.shutdownNow(); }
    }
    private static String readLimited(InputStream in) throws IOException {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream(); byte[] b=new byte[4096]; int n;
        while((n=in.read(b))!=-1) {
            if(bytes.size()+n>256*1024) throw new IOException("模块列表超过读取上限");
            bytes.write(b,0,n);
        }
        return bytes.toString(StandardCharsets.UTF_8.name());
    }
}
