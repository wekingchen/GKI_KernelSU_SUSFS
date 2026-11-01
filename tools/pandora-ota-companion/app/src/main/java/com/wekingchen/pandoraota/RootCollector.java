package com.wekingchen.pandoraota;

import android.content.Context;
import android.os.Build;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.zip.*;

/** Read-only rooted capture; never flash or change the device partitions. */
final class RootCollector {
    private RootCollector() {}

    static boolean isPandora() {
        return "pandora".equalsIgnoreCase(Build.DEVICE)
                || "pandora".equalsIgnoreCase(Build.PRODUCT);
    }

    static String checkRoot() throws Exception {
        Process p = new ProcessBuilder("su", "-c", "id").redirectErrorStream(true).start();
        String output = readLimited(p.getInputStream(), 4096);
        int rc = p.waitFor();
        if (rc != 0 || !output.contains("uid=0")) {
            throw new IllegalStateException("Root 未授权或 su 命令不可用");
        }
        return output.trim();
    }

    static File capture(Context ctx, boolean includeBoot) throws Exception {
        if (!isPandora()) throw new IllegalStateException("仅支持小米17 Pro（pandora）");
        checkRoot();
        File parent = new File(ctx.getExternalFilesDir(null), "captures");
        if (!parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("无法建立采集目录");
        }
        String stamp = timestamp();
        File dir = new File(parent, "staging-" + stamp);
        if (!dir.mkdirs()) throw new IllegalStateException("创建临时目录失败");
        File zip = new File(parent, "pandora-os4-capture-" + stamp + ".zip");

        String sh = "set -eu\n"
                + "umask 077\n"
                + "OUT=" + shellQuote(dir.getAbsolutePath()) + "\n"
                + "mkdir -p \"$OUT\"\n"
                + "printf 'schema=pandora-ota-capture-v1\\nsource=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\\ndevice=pandora\\n' > \"$OUT/manifest.txt\"\n"
                + "for key in ro.product.device ro.build.version.release ro.build.version.incremental ro.build.fingerprint ro.boot.slot_suffix; do "
                + "printf '%s=' \"$key\" >> \"$OUT/manifest.txt\"; getprop \"$key\" >> \"$OUT/manifest.txt\"; done\n"
                + "uname -r > \"$OUT/kernel-release.txt\"\n"
                + "cat /proc/version > \"$OUT/kernel-version.txt\"\n"
                + "(cat /proc/modules || true) > \"$OUT/loaded-modules.txt\"\n"
                + "(cat /sys/kernel/security/lsm || true) > \"$OUT/lsm.txt\"\n"
                + "(cat /proc/cgroups || true) > \"$OUT/cgroups.txt\"\n"
                + "modules=''\n"
                + "for d in vendor_dlkm/lib/modules system_dlkm/lib/modules vendor/lib/modules system/lib/modules; do "
                + "if [ -d \"/$d\" ]; then modules=\"$modules $d\"; fi; done\n"
                + "if [ -z \"$modules\" ]; then echo 'OEM module paths missing' >&2; exit 21; fi\n"
                + "(cd / && tar -cf \"$OUT/oem-modules.tar\" $modules)\n"
                + (includeBoot
                    ? "slot=\"$(getprop ro.boot.slot_suffix)\"\n"
                    + "case \"$slot\" in _a|_b) ;; *) echo 'invalid slot' >&2; exit 12;; esac\n"
                    + "for part in boot init_boot vendor_boot dtbo; do "
                    + "dev=\"/dev/block/by-name/$part$slot\"; "
                    + "if [ -e \"$dev\" ]; then dd if=\"$dev\" of=\"$OUT/$part$slot.img\" bs=1048576 2>/dev/null; fi; done\n"
                    : "")
                + "chmod 644 \"$OUT\"/*\n";
        Process p = new ProcessBuilder("su", "-c", sh).redirectErrorStream(true).start();
        String shellLog = readLimited(p.getInputStream(), 8192);
        int rc = p.waitFor();
        if (rc != 0) {
            throw new IllegalStateException("只读采集失败 (code " + rc + "): " + shellLog);
        }
        File[] produced = dir.listFiles();
        if (produced == null || produced.length == 0) {
            throw new IllegalStateException("采集结果为空");
        }
        try (ZipOutputStream out = new ZipOutputStream(new FileOutputStream(zip))) {
            byte[] buffer = new byte[1024 * 256];
            for (File f : produced) {
                if (!f.isFile()) continue;
                out.putNextEntry(new ZipEntry(f.getName()));
                try (BufferedInputStream in = new BufferedInputStream(new FileInputStream(f))) {
                    int n;
                    while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
                }
                out.closeEntry();
            }
        }
        for (File f : produced) if (f.isFile()) f.delete();
        dir.delete();
        if (!zip.isFile() || zip.length() == 0) {
            throw new IllegalStateException("ZIP 打包结果为空");
        }
        return zip;
    }

    private static String shellQuote(String s) {
        return "'" + s.replace("'", "'\\''") + "'";
    }

    private static String timestamp() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        return fmt.format(new Date());
    }

    private static String readLimited(InputStream input, int limit) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] b = new byte[1024];
        int n;
        while ((n = input.read(b)) != -1) {
            if (out.size() < limit) out.write(b, 0, Math.min(n, limit - out.size()));
        }
        return out.toString(StandardCharsets.UTF_8.name());
    }
}
