package com.wekingchen.pandoraota;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.Comparator;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Scoped GitHub PAT stored with Android Keystore; upload receipts tracked per archive. */
final class SecretStore {
    private static final String ALIAS = "pandora_ota_github_token_v1";
    private final SharedPreferences prefs;
    private final Context context;

    SecretStore(Context ctx) {
        context = ctx.getApplicationContext();
        prefs = context.getSharedPreferences("private_config", Context.MODE_PRIVATE);
    }

    String repo() {
        return prefs.getString("repo", "wekingchen/GKI_KernelSU_SUSFS");
    }

    void saveRepo(String repo) {
        prefs.edit().putString("repo", repo).apply();
    }

    boolean hasToken() {
        return prefs.contains("token_ciphertext") && prefs.contains("token_iv");
    }

    void saveToken(String token) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(token.getBytes(StandardCharsets.UTF_8));
        prefs.edit()
                .putString("token_iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                .putString("token_ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP))
                .apply();
    }

    String loadToken() throws Exception {
        String iv = prefs.getString("token_iv", null);
        String ciphertext = prefs.getString("token_ciphertext", null);
        if (iv == null || ciphertext == null) return null;
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(),
                new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
        return new String(cipher.doFinal(
                Base64.decode(ciphertext, Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }

    void clearToken() {
        prefs.edit().remove("token_iv").remove("token_ciphertext").apply();
    }

    String lastArchive() {
        return prefs.getString("last_archive", "");
    }

    void saveArchive(String path) {
        // Select new capture, but keep receipts for earlier archives.
        prefs.edit().putString("last_archive", path).apply();
    }

    File[] archives() {
        File base = new File(context.getExternalFilesDir(null), "captures");
        File[] files = base.listFiles(f ->
                f.isFile() && f.getName().matches("pandora-os4-capture-\\d{8}-\\d{6}(?:-\\d{3})?\\.zip"));
        if (files == null) return new File[0];
        Arrays.sort(files, Comparator.comparingLong(File::lastModified).reversed());
        return files;
    }

    private JSONObject receipts() {
        try {
            return new JSONObject(prefs.getString("upload_receipts", "{}"));
        } catch (Exception ignored) {
            return new JSONObject();
        }
    }

    void confirmedUpload(String path, long bytes, GitHubUploader.Result result) throws Exception {
        JSONObject all = receipts();
        JSONObject info = new JSONObject();
        info.put("bytes", bytes);
        info.put("repo", repo());
        info.put("sha256", result.sha256);
        info.put("release", result.releaseUrl);
        info.put("release_id", result.releaseId);
        info.put("dispatched", result.dispatched);
        all.put(path, info);
        if (!prefs.edit().putString("upload_receipts", all.toString()).commit())
            throw new IllegalStateException("本机上传回执保存失败，请暂勿删除 ZIP");
    }

    boolean isUploaded(FileInfo file) {
        if (file == null) return false;
        JSONObject entry = receipts().optJSONObject(file.path);
        return entry != null && file.size > 0
                && repo().equals(entry.optString("repo", ""))
                && entry.optLong("bytes", -1) == file.size
                && !entry.optString("sha256", "").isEmpty();
    }

    static final class FileInfo {
        final String path;
        final long size;
        FileInfo(String path, long size) {
            this.path = path;
            this.size = size;
        }
    }

    private JSONObject selectedReceipt() {
        return receipts().optJSONObject(lastArchive());
    }

    String lastReleaseUrl() {
        JSONObject info = selectedReceipt();
        return info == null ? "" : info.optString("release", "");
    }

    long lastReleaseId() {
        JSONObject info = selectedReceipt();
        return info == null ? 0 : info.optLong("release_id", 0);
    }

    boolean dispatched() {
        JSONObject info = selectedReceipt();
        return info != null && info.optBoolean("dispatched", false);
    }

    void forgetArchive() {
        String removed = lastArchive();
        JSONObject all = receipts();
        all.remove(removed);
        File[] remaining = archives();
        SharedPreferences.Editor edit = prefs.edit()
                .putString("upload_receipts", all.toString());
        if (remaining.length == 0) edit.remove("last_archive");
        else edit.putString("last_archive", remaining[0].getAbsolutePath());
        edit.apply();
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        SecretKey existing = (SecretKey) store.getKey(ALIAS, null);
        if (existing != null) return existing;
        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build();
        generator.init(spec);
        return generator.generateKey();
    }
}
