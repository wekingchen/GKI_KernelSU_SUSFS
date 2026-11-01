package com.wekingchen.pandoraota;

import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Read-only capture delivery. A transport progress event is NOT server confirmation. */
final class GitHubUploader {
    static final long MAX_ASSET = 950L * 1024L * 1024L; // same limit as server OTA stock input
    private GitHubUploader() {}
    /** Injectable only for offline Android integration tests; production always validates GitHub HTTPS hosts. */
    interface ConnectionFactory { HttpURLConnection open(URL url) throws Exception; }
    private static final ConnectionFactory PRODUCTION = url -> (HttpURLConnection) url.openConnection();

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
        return uploadWithTransport(repo, token, file, listener, PRODUCTION);
    }

    static Result uploadWithTransport(String repo, String token, File file,
                                     Listener listener, ConnectionFactory transport) throws Exception {
        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("仓库格式必须为 owner/repo");
        }
        if (token == null || token.trim().isEmpty()) {
            throw new IllegalArgumentException("请先配置 GitHub fine-grained PAT");
        }
        if (!file.isFile() || file.length() <= 0 || file.length() >= MAX_ASSET) {
            throw new IllegalArgumentException("采集包不存在、为空或达到 OTA 950 MiB 上限；请勿上传不受支持的大包");
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
        JSONObject release = postJson(api + "/releases", token, request, 201, transport);
        String template = release.getString("upload_url");
        String uploadBase = template.split("\\{", 2)[0];
        if (!uploadBase.startsWith("https://uploads.github.com/")) {
            throw new SecurityException("GitHub 返回了非预期的附件上传地址");
        }
        String uploadUrl = uploadBase + "?name=" +
                URLEncoder.encode(file.getName(), StandardCharsets.UTF_8.name());
        listener.onStage("正在发送采集包");
        listener.onProgress(0, file.length());
        JSONObject asset = postBinary(uploadUrl, token, file, listener, transport);
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
            postJson(api + "/dispatches", token, event, 204, transport);
            dispatched = true;
        } catch (Exception ignored) {
            // Sending an event is separate from the already-confirmed upload.
            dispatched = false;
        }
        String releaseUrl = release.optString("html_url", "");
        return new Result(release.getLong("id"), asset.getLong("id"), sha256,
                releaseUrl, dispatched);
    }

    /** Live write proof: create/read/delete only our uniquely named empty draft, then probe dispatch. */
    static void verifyConnection(String repo, String token) throws Exception {
        verifyConnection(repo, token, PRODUCTION);
    }

    static void verifyConnection(String repo, String token, ConnectionFactory transport) throws Exception {
        if (repo == null || !repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || token == null || token.trim().isEmpty())
            throw new IllegalArgumentException("请先配置 GitHub 仓库和访问令牌");
        String api = "https://api.github.com/repos/" + repo;
        JSONObject metadata = getJson(api, token, transport);
        if (!repo.equalsIgnoreCase(metadata.optString("full_name"))
                || metadata.optBoolean("archived") || metadata.optBoolean("disabled"))
            throw new IOException("GitHub 仓库不可写、已归档或身份不匹配");
        String tag = "pandora-ota-preflight-" + java.util.UUID.randomUUID();
        JSONObject request = new JSONObject();
        request.put("tag_name", tag);
        request.put("name", tag);
        request.put("draft", true);
        request.put("prerelease", true);
        request.put("body", "Temporary OTA permission check; no capture data.");
        JSONObject created = postJson(api + "/releases", token, request, 201, transport);
        long id = created.optLong("id");
        if (id <= 0) throw new IOException("GitHub 未返回权限验证草稿 ID，请检查草稿列表");
        Exception failure = null;
        try {
            JSONObject draft = getJson(api + "/releases/" + id, token, transport);
            if (draft.optLong("id") != id || !draft.optBoolean("draft")
                    || !tag.equals(draft.optString("tag_name"))
                    || !tag.equals(draft.optString("name"))
                    || draft.optJSONArray("assets") == null || draft.getJSONArray("assets").length() != 0)
                throw new IOException("GitHub 权限验证草稿身份不匹配");
        } catch (Exception e) { failure = e; }
        // ID comes only from this POST, never from a list/search or a stored capture receipt.
        try {
            HttpURLConnection connection = connect(api + "/releases/" + id, token, transport);
            try {
                connection.setRequestMethod("DELETE");
                int status = connection.getResponseCode();
                readResponse(connection, status);
                if (status != 204) throw new IOException("HTTP " + status);
            } finally { connection.disconnect(); }
        } catch (Exception e) {
            throw new IOException("权限验证草稿 #" + id + " 清理失败，请在 GitHub 删除该空草稿后重试", e);
        }
        if (failure != null) throw failure;
        JSONObject event = new JSONObject();
        // No intake workflow subscribes to this event; never dispatch a fake capture.
        event.put("event_type", "pandora_ota_preflight_v1");
        postJson(api + "/dispatches", token, event, 204, transport);
    }

    /**
     * Confirm the exact remote archive still exists before optional local deletion.
     * Server OTA acceptance is deliberately NOT required: a custom boot may be
     * legitimately rejected while the original archive remains stored on GitHub.
     * This method does not mutate Releases or any other remote resources.
     */
    static void verifyRemoteArchive(String repo, String token, long releaseId,
                                    long assetId, File localFile, String sha) throws Exception {
        if (repo == null || !repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || token == null || token.isEmpty() || releaseId <= 0 || assetId <= 0
                || sha == null || !sha.matches("[0-9a-f]{64}") || !localFile.isFile()
                || localFile.length() <= 0) {
            throw new SecurityException("缺少有效的 GitHub 上传回执，禁止删除本地文件");
        }
        JSONObject release = getJson("https://api.github.com/repos/" + repo
                + "/releases/" + releaseId, token);
        verifyRemoteArchiveMetadata(release, releaseId, assetId,
                localFile.getName(), localFile.length(), sha);
    }

    /** Pure validation for real API responses and offline emulator tests. */
    static void verifyRemoteArchiveMetadata(JSONObject release, long releaseId, long assetId,
                                            String filename, long bytes, String sha) throws Exception {
        if (release.optLong("id") != releaseId || !release.optBoolean("draft")
                || !"Pandora OS4 OTA capture — private intake"
                        .equals(release.optString("name"))) {
            throw new SecurityException("GitHub Release 身份不匹配，禁止删除");
        }
        String tag = release.optString("tag_name");
        if (!tag.startsWith("pandora-ota-capture-") && !tag.startsWith("untagged-")) {
            throw new SecurityException("GitHub Release 标签异常，禁止删除");
        }
        org.json.JSONArray assets = release.optJSONArray("assets");
        if (assets == null) throw new SecurityException("GitHub Release 不包含附件列表");
        int found = 0;
        for (int i = 0; i < assets.length(); i++) {
            JSONObject item = assets.optJSONObject(i);
            if (item == null || item.optLong("id") != assetId) continue;
            found++;
            if (!filename.equals(item.optString("name"))
                    || item.optLong("size", -1) != bytes
                    || !"uploaded".equals(item.optString("state"))
                    || !("sha256:" + sha).equalsIgnoreCase(item.optString("digest"))) {
                throw new SecurityException("远端附件名称、大小或 SHA-256 不一致，禁止删除");
            }
        }
        if (found != 1) throw new SecurityException("远端附件不存在或重复，禁止删除");
    }

    /**
     * GitHub Draft Releases have a private editor URL, not a published /tag/
     * page. A /releases/tag/untagged-* link returned in html_url may show 404
     * even though the authenticated REST API reports the draft and ZIP intact.
     *
     * Fetch the CURRENT release at click time: stored URLs are not durable
     * because GitHub may retag drafts while the intake writes its receipt.
     */
    static String verifiedDraftEditorUrl(String repo, String token, long releaseId,
                                         long assetId, File file, String sha) throws Exception {
        if (repo == null || !repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || token == null || token.isEmpty()
                || releaseId <= 0 || assetId <= 0 || sha == null
                || !sha.matches("[0-9a-f]{64}") || file == null || !file.isFile()) {
            throw new SecurityException("无法确认该采集包的 GitHub 草稿身份");
        }
        JSONObject release = getJson("https://api.github.com/repos/" + repo
                + "/releases/" + releaseId, token);
        return verifiedDraftEditorUrlFromMetadata(repo, release, releaseId, assetId,
                file.getName(), file.length(), sha);
    }

    /** Offline-testable, fail-closed translation for a verified Draft Release. */
    static String verifiedDraftEditorUrlFromMetadata(String repo, JSONObject release,
                                                      long releaseId, long assetId,
                                                      String filename, long bytes, String sha)
            throws Exception {
        verifyRemoteArchiveMetadata(release, releaseId, assetId, filename, bytes, sha);
        return draftEditorUrl(repo, release.optString("html_url"));
    }

    /** Validate and convert only the canonical GitHub release tag URL. */
    static String draftEditorUrl(String repo, String htmlUrl) {
        if (repo == null || !repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || htmlUrl == null) {
            throw new SecurityException("无效的 GitHub 草稿地址");
        }
        String prefix = "https://github.com/" + repo + "/releases/tag/";
        if (!htmlUrl.startsWith(prefix)) {
            throw new SecurityException("GitHub 返回了非预期的 Release 地址");
        }
        String tag = htmlUrl.substring(prefix.length());
        if (!tag.matches("(untagged-[A-Za-z0-9-]+|pandora-ota-capture-[A-Za-z0-9-]+)")) {
            throw new SecurityException("GitHub Draft Release 标识无效");
        }
        return "https://github.com/" + repo + "/releases/edit/" + tag;
    }

    /** Retry notification for an already-uploaded GitHub attachment, without uploading again. */
    static void retryDispatch(String repo, String token, File file,
                              long releaseId, long assetId, String expectedSha) throws Exception {
        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || token == null || token.isEmpty() || releaseId <= 0 || assetId <= 0
                || !expectedSha.matches("[0-9a-f]{64}") || !file.isFile()
                || file.length() <= 0 || file.length() >= MAX_ASSET) {
            throw new SecurityException("通知重试所需上传回执或本地 ZIP 不合法");
        }
        if (!sha256(file).equals(expectedSha)) {
            throw new SecurityException("ZIP SHA-256 与历史上传回执不一致，禁止重新通知");
        }
        JSONObject release = getJson("https://api.github.com/repos/" + repo
                + "/releases/" + releaseId, token);
        if (!release.optBoolean("draft") || !release.optString("tag_name")
                .startsWith("pandora-ota-capture-")) {
            throw new SecurityException("远端 Draft Release 来源不匹配");
        }
        boolean found = false;
        org.json.JSONArray assets = release.optJSONArray("assets");
        if (assets != null) for (int i = 0; i < assets.length(); i++) {
            JSONObject asset = assets.optJSONObject(i);
            if (asset != null && asset.optLong("id") == assetId
                    && asset.optLong("size") == file.length()
                    && file.getName().equals(asset.optString("name"))) found = true;
        }
        if (!found) throw new SecurityException("远端附件已变化，拒绝通知重试");
        JSONObject payload = new JSONObject();
        payload.put("schema", "pandora-ota-capture-v1");
        payload.put("release_id", releaseId);
        payload.put("asset_id", assetId);
        payload.put("filename", file.getName());
        payload.put("sha256", expectedSha);
        payload.put("bytes", file.length());
        JSONObject event = new JSONObject();
        event.put("event_type", "pandora_ota_upload_v1");
        event.put("client_payload", payload);
        postJson("https://api.github.com/repos/" + repo + "/dispatches", token, event, 204);
    }

    /** Server-side ingestion result, not GKI boot/ABI verification. */
    static String checkIntake(String repo, String token,
                              long releaseId, long assetId, String sha) throws Exception {
        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || releaseId <= 0 || assetId <= 0 || !sha.matches("[0-9a-f]{64}")
                || token == null || token.isEmpty()) {
            throw new SecurityException("GitHub 接收状态查询缺少合法的回执");
        }
        JSONObject source = getJson("https://api.github.com/repos/" + repo
                + "/releases/" + releaseId, token);
        return parseIntakeReceipt(source, assetId, sha);
    }

    static String parseIntakeReceipt(JSONObject source, long assetId, String sha) throws Exception {
        if (!source.optBoolean("draft") || !source.optString("tag_name")
                .startsWith("pandora-ota-capture-")) {
            throw new SecurityException("接收状态来源不是采集应用的 Draft Release");
        }
        String body = source.optString("body", "");
        if (!body.contains("MOBILE_OTA_INTAKE=")) return "PENDING";
        String id = "";
        String digest = "";
        String state = "";
        for (String line : body.split("\\r?\\n")) {
            if (line.startsWith("MOBILE_ASSET_ID=")) id = line.substring(16).trim();
            if (line.startsWith("MOBILE_SOURCE_SHA256=")) digest = line.substring(21).trim();
            if (line.startsWith("MOBILE_OTA_INTAKE=")) state = line.substring(18).trim();
        }
        if (!Long.toString(assetId).equals(id) || !sha.equals(digest)) {
            throw new SecurityException("服务器状态对应不同附件，不能视为本次接收结果");
        }
        if ("ACCEPTED".equals(state) || "ALREADY_CURRENT".equals(state)
                || "REJECTED".equals(state)) return state;
        return "PENDING";
    }

    private static JSONObject getJson(String target, String token) throws Exception {
        return getJson(target, token, PRODUCTION);
    }

    private static JSONObject getJson(String target, String token, ConnectionFactory transport) throws Exception {
        HttpURLConnection connection = connect(target, token, transport);
        try {
            connection.setRequestMethod("GET");
            int status = connection.getResponseCode();
            String body = readResponse(connection, status);
            if (status != 200) throw new IOException("读取 GitHub API HTTP " + status);
            return new JSONObject(body);
        } finally {
            connection.disconnect();
        }
    }

    private static JSONObject postBinary(String url, String token, File file,
                                         Listener listener, ConnectionFactory transport) throws Exception {
        HttpURLConnection conn = connect(url, token, transport);
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
        return postJson(url, token, request, expectedStatus, PRODUCTION);
    }

    private static JSONObject postJson(String url, String token, JSONObject request,
                                       int expectedStatus, ConnectionFactory transport) throws Exception {
        HttpURLConnection conn = connect(url, token, transport);
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
        return connect(url, token, PRODUCTION);
    }

    private static HttpURLConnection connect(String url, String token,
                                             ConnectionFactory transport) throws Exception {
        URL target = new URL(url);
        String host = target.getHost().toLowerCase(Locale.ROOT);
        if (!"https".equals(target.getProtocol())
                || (!"api.github.com".equals(host) && !"uploads.github.com".equals(host))) {
            throw new SecurityException("仅允许 GitHub HTTPS API 上传");
        }
        HttpURLConnection conn = transport.open(target);
        conn.setInstanceFollowRedirects(false);
        conn.setUseCaches(false);
        conn.setRequestProperty("Cache-Control", "no-cache");
        conn.setConnectTimeout(20000);
        conn.setReadTimeout(120000);
        conn.setRequestProperty("Authorization", "Bearer " + token);
        conn.setRequestProperty("Accept", "application/vnd.github+json");
        conn.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
        conn.setRequestProperty("User-Agent", "pandora-ota-companion/0.12.2");
        return conn;
    }

    // Never parse a truncated successful JSON response. Only error-message previews may be clipped.
    private static final int MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024;
    private static final int MAX_ERROR_RESPONSE_BYTES = 16 * 1024;

    private static String readResponse(HttpURLConnection conn, int status) throws IOException {
        InputStream stream = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
        if (stream == null) return "";
        final int limit = status >= 400 ? MAX_ERROR_RESPONSE_BYTES : MAX_JSON_RESPONSE_BYTES;
        try (InputStream in = stream; ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) != -1) {
                int remaining = limit - bytes.size();
                if (n > remaining) {
                    if (status >= 400) {
                        bytes.write(buffer, 0, remaining);
                        break; // Error text is only diagnostic; it is never parsed as JSON.
                    }
                    throw new IOException("GitHub API 响应超过 2 MiB 安全上限，拒绝解析不完整 JSON");
                }
                bytes.write(buffer, 0, n);
            }
            return bytes.toString(StandardCharsets.UTF_8.name());
        }
    }

    static String sha256(File file) throws Exception {
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
