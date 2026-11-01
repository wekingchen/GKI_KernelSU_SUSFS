package com.wekingchen.pandoraota;

import android.content.Context;
import android.os.StatFs;
import java.io.IOException;

/** Thresholds use available bytes on the actual capture filesystem, not total/free storage. */
final class CapturePreflight {
    static final long GIB = 1024L * 1024L * 1024L;
    enum Space { BLOCK, WARN, READY }
    static Space space(long available) {
        if (available < GIB) return Space.BLOCK;
        return available < 2 * GIB ? Space.WARN : Space.READY;
    }
    static long available(Context context) throws IOException {
        try {
            return new StatFs(RootCollector.captureDirectory(context).getAbsolutePath()).getAvailableBytes();
        } catch (IllegalArgumentException e) {
            throw new IOException("无法读取采集目录可用空间", e);
        }
    }
    static long requireSpace(Context context) throws IOException {
        long bytes = available(context);
        if (space(bytes) == Space.BLOCK)
            throw new IOException("采集目录可用空间不足 1 GiB，请释放空间后再采集");
        return bytes;
    }
    static String buildIdentity(String os, String fingerprint) {
        if (os == null || os.isEmpty() || "未知版本".equals(os)) return "";
        return os + "\n" + (fingerprint == null ? "" : fingerprint);
    }
    static boolean buildChanged(String previous, String current) {
        return current != null && !current.isEmpty() && !current.equals(previous);
    }
}
