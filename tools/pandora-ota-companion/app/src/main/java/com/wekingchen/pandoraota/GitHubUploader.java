package com.wekingchen.pandoraota;

import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Read-only capture delivery. A transport progress event is NOT server confirmation. */
final class GitHubUploader {
    static final long MAX_ASSET = 2L * 1024L * 1024L * 1024L;
    private GitHubUploader() {}

    interface Listener {
        void onStage(String stage);
        void onProgress(long sent, long total);
    }

    static final class Result {
        final long releaseId;
        final long assetId;
        final String sha256;
        final String releaseUrl;
        final boolean dispatched;

        Result(long releaseId, long assetId, String sha256, String releaseUrl, boolean dispatched) {
            this.releaseId = releaseId;
            this.assetId = assetId;
            this.sha256 = sha256;
            this.releaseUrl = releaseUrl;
            this.dispatched = dispatched;
        }
    }

    static Result upload(String repo, String token, File file, Listener listener) throws Exception {
        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("仓库格式必须为 owner/repo");
        }
        if (token == null || token.trim().isEmpty()) {
            throw new IllegalArgumentException("请先配置 GitHub fine-grained PAT");
        }
        if (!file.isFile() || file.length() <= 0 || file.length() >= MAX_ASSET) {
            throw new IllegalArgumentException("采集包不存在、为空或达到单附件 2 GiB 限制");
        }
        listener.onStage("校验文件 SHA-256");
        String sha256 = sha256(file);
        String api = "https://api.github.com/repos/" + repo;
        listener.onStage("创建 GitHub Draft Release");
        JSONObject request = new JSONObject();
        request.put("tag_name", "pandora-ota-capture-" + System.currentTimeMillis());
        request.put("name", "Pandora OS4 OTA capture — private intake");
        request.put("draft", true);
        request.put("prerelease", true);
        request.put("body", "Unverified read-only mobile snapshot. Do not publish or flash.");
        JSONObject release = postJson(api + "/releases", token, request, 201);
        String template = release.getString("upload_url");
        String uploadBase = template.split("\\{", 2)[0];
        if (!uploadBase.startsWith("https://uploads.github.com/")) {
            throw new SecurityException("GitHub 返回了非预期的附件上传地址");
        }
        String uploadUrl = uploadBase + "?name=" +
                URLEncoder.encode(file.getName(), StandardCharsets.UTF_8.name());
        listener.onStage("正在发送采集包");
        listener.onProgress(0, file.length());
        JSONObject asset = postBinary(uploadUrl, token, file, listener);
        long acceptedSize = asset.optLong("size", -1);
        if (acceptedSize != file.length()) {
            throw new IOException("GitHub 接收文件大小不匹配；本地包已保留，请核查 Release");
        }
        listener.onStage("GitHub 已确认附件，正在通知工作流");
        JSONObject payload = new JSONObject();
        payload.put("schema", "pandora-ota-capture-v1");
        payload.put("release_id", release.getLong("id"));
        payload.put("asset_id", asset.getLong("id"));
        payload.put("filename", file.getName());
        payload.put("sha256", sha256);
        payload.put("bytes", file.length());
        JSONObject event = new JSONObject();
        event.put("event_type", "pandora_ota_upload_v1");
        event.put("client_payload", payload);
        boolean dispatched;
        try {
            postJson(api + "/dispatches", token, event, 204);
            dispatched = true;
        } catch (Exception ignored) {
            // Sending an event is separate from the already-confirmed upload.
            dispatched = false;
        }
        String releaseUrl = release.optString("html_url", "");
        return new Result(release.getLong("id"), asset.getLong("id"), sha256,
                releaseUrl, dispatched);
    }

    private static JSONObject postBinary(String url, String token, File file,
                                         Listener listener) throws Exception {
        HttpURLConnection conn = connect(url, token);
        try {
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/zip");
            conn.setDoOutput(true);
            conn.setReadTimeout(30 * 60 * 1000);
            conn.setFixedLengthStreamingMode(file.length());
            try (InputStream input = new BufferedInputStream(new FileInputStream(file));
                 OutputStream out = conn.getOutputStream()) {
                byte[] buffer = new byte[256 * 1024];
                long sent = 0;
                int n;
                while ((n = input.read(buffer)) != -1) {
                    out.write(buffer, 0, n);
                    sent += n;
                    listener.onProgress(sent, file.length());
                }
                out.flush();
            }
            listener.onStage("已发送 100%，等待 GitHub 确认");
            int status = conn.getResponseCode();
            String body = readResponse(conn, status);
            if (status != 201) throw new IOException("上传 HTTP " + status + ": " + body);
            return new JSONObject(body);
        } finally {
            conn.disconnect();
        }
    }

    private static JSONObject postJson(String url, String token, JSONObject request,
                                       int expectedStatus) throws Exception {
        HttpURLConnection conn = connect(url, token);
        try {
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            byte[] data = request.toString().getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(data.length);
            try (OutputStream out = conn.getOutputStream()) {
                out.write(data);
            }
            int status = conn.getResponseCode();
            String body = readResponse(conn, status);
            if (status != expectedStatus) {
                throw new IOException("GitHub API HTTP " + status + ": " + body);
            }
            return body.isEmpty() ? new JSONObject() : new JSONObject(body);
        } finally {
            conn.disconnect();
        }
    }

    private static HttpURLConnection connect(String url, String token) throws Exception {
        URL target = new URL(url);
        String host = target.getHost().toLowerCase(Locale.ROOT);
        if (!"https".equals(target.getProtocol())
                || (!"api.github.com".equals(host) && !"uploads.github.com".equals(host))) {
            throw new SecurityException("仅允许 GitHub HTTPS API 上传");
        }
        HttpURLConnection conn = (HttpURLConnection) target.openConnection();
        conn.setInstanceFollowRedirects(false);
        conn.setConnectTimeout(20000);
        conn.setReadTimeout(120000);
        conn.setRequestProperty("Authorization", "Bearer " + token);
        conn.setRequestProperty("Accept", "application/vnd.github+json");
        conn.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
        conn.setRequestProperty("User-Agent", "pandora-ota-companion/0.2");
        return conn;
    }

    private static String readResponse(HttpURLConnection conn, int status) throws IOException {
        InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
        if (stream == null) return "";
        try (InputStream in = stream; ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (bytes.size() < 16384)
                    bytes.write(buffer, 0, Math.min(n, 16384 - bytes.size()));
            }
            return bytes.toString(StandardCharsets.UTF_8.name());
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] data = new byte[256 * 1024];
            int n;
            while ((n = input.read(data)) != -1) digest.update(data, 0, n);
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) {
            hex.append(String.format(Locale.US, "%02x", b & 0xff));
        }
        return hex.toString();
    }
}
