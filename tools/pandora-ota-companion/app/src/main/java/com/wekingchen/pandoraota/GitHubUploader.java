package com.wekingchen.pandoraota;

import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Creates a private Draft Release, uploads the captured ZIP, then emits a dispatch event. */
final class GitHubUploader {
    private GitHubUploader() {}
    static final long MAX_ASSET = 2L * 1024L * 1024L * 1024L;

    static String upload(String repo, String token, File file) throws Exception {
        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("仓库格式必须为 owner/repo");
        }
        if (token == null || token.trim().isEmpty()) {
            throw new IllegalArgumentException("请先配置 GitHub fine-grained PAT");
        }
        if (!file.isFile() || file.length() <= 0 || file.length() >= MAX_ASSET) {
            throw new IllegalArgumentException("文件不存在、为空或达到 GitHub 单附件 2 GiB 上限");
        }
        String sha256 = sha256(file);
        String api = "https://api.github.com/repos/" + repo;
        JSONObject request = new JSONObject();
        request.put("tag_name", "pandora-ota-capture-" + System.currentTimeMillis());
        request.put("name", "Pandora OS4 OTA capture — private intake");
        request.put("draft", true);
        request.put("prerelease", true);
        request.put("body", "Unverified read-only mobile capture. Do not publish or flash.");
        JSONObject release = postJson(api + "/releases", token, request, 201);
        String template = release.getString("upload_url");
        String baseUploadUrl = template.split("\\{", 2)[0];
        if (!baseUploadUrl.startsWith("https://uploads.github.com/")) {
            throw new IllegalStateException("GitHub 返回了非预期的上传地址");
        }
        String uploadUrl = baseUploadUrl + "?name="
                + URLEncoder.encode(file.getName(), StandardCharsets.UTF_8.name());
        JSONObject asset = postBinary(uploadUrl, token, file);
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
        boolean dispatched = true;
        try {
            postJson(api + "/dispatches", token, event, 204);
        } catch (Exception e) {
            dispatched = false; // uploaded asset is preserved; notify the user.
        }
        return "Draft Release ID " + release.getLong("id")
                + "\nAsset ID " + asset.getLong("id")
                + "\nSHA-256 " + sha256
                + "\n上传完成；dispatch=" + (dispatched ? "已提交（不代表工作流已执行）" : "失败，需人工重试");
    }

    private static JSONObject postBinary(String target, String token, File file) throws Exception {
        HttpURLConnection connection = connect(target, token);
        try {
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/zip");
            connection.setDoOutput(true);
            connection.setReadTimeout(30 * 60 * 1000);
            connection.setFixedLengthStreamingMode(file.length());
            try (InputStream input = new BufferedInputStream(new FileInputStream(file));
                 OutputStream out = connection.getOutputStream()) {
                byte[] bytes = new byte[256 * 1024];
                int n;
                while ((n = input.read(bytes)) != -1) out.write(bytes, 0, n);
            }
            int status = connection.getResponseCode();
            String body = readResponse(connection, status);
            if (status != 201) throw new IOException("上传 HTTP " + status + ": " + body);
            return new JSONObject(body);
        } finally {
            connection.disconnect();
        }
    }

    private static JSONObject postJson(String target, String token, JSONObject request,
                                       int expected) throws Exception {
        HttpURLConnection connection = connect(target, token);
        try {
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            byte[] encoded = request.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(encoded.length);
            try (OutputStream out = connection.getOutputStream()) { out.write(encoded); }
            int status = connection.getResponseCode();
            String body = readResponse(connection, status);
            if (status != expected) throw new IOException("GitHub API HTTP " + status + ": " + body);
            return body.isEmpty() ? new JSONObject() : new JSONObject(body);
        } finally {
            connection.disconnect();
        }
    }

    private static HttpURLConnection connect(String url, String token) throws Exception {
        URL target = new URL(url);
        String host = target.getHost().toLowerCase(Locale.ROOT);
        if (!"https".equals(target.getProtocol())
                || (!"api.github.com".equals(host) && !"uploads.github.com".equals(host))) {
            throw new SecurityException("仅允许 GitHub HTTPS API 地址");
        }
        HttpURLConnection connection = (HttpURLConnection) target.openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(20000);
        connection.setReadTimeout(120000);
        connection.setRequestProperty("Authorization", "Bearer " + token);
        connection.setRequestProperty("Accept", "application/vnd.github+json");
        connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
        connection.setRequestProperty("User-Agent", "pandora-os4-ota-companion/0.1");
        return connection;
    }

    private static String readResponse(HttpURLConnection conn, int status) throws IOException {
        InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
        if (stream == null) return "";
        try (InputStream in = stream; ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (bytes.size() < 16384) bytes.write(buffer, 0, Math.min(n, 16384 - bytes.size()));
            }
            return bytes.toString(StandardCharsets.UTF_8.name());
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new BufferedInputStream(new FileInputStream(file))) {
            byte[] buffer = new byte[256 * 1024];
            int n;
            while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) {
            hex.append(String.format(Locale.US, "%02x", b & 0xff));
        }
        return hex.toString();
    }
}
