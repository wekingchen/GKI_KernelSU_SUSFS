package com.wekingchen.pandoraota;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Fine-grained PAT encrypted by the Android Keystore AES-GCM key. */
final class SecretStore {
    private static final String ALIAS = "pandora_ota_github_token_v1";
    private final SharedPreferences prefs;

    SecretStore(Context ctx) {
        prefs = ctx.getSharedPreferences("private_config", Context.MODE_PRIVATE);
    }

    String repo() {
        return prefs.getString("repo", "wekingchen/GKI_KernelSU_SUSFS");
    }

    void saveRepo(String repo) {
        prefs.edit().putString("repo", repo).apply();
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
        prefs.edit().putString("last_archive", path).apply();
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        SecretKey existing = (SecretKey) store.getKey(ALIAS, null);
        if (existing != null) return existing;
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build();
        gen.init(spec);
        return gen.generateKey();
    }
}
