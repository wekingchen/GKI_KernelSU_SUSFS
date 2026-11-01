package com.wekingchen.pandoraota;

import android.content.Context;
import android.widget.Button;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import static org.junit.Assert.*;

/** Offline GitHub asset hash contract and local deletion UI eligibility. */
@RunWith(AndroidJUnit4.class)
public class RemoteCleanupEmulatorTest {
    private static final String SHA =
        "9a32b83a2571fe4bdd6fb1a030076f4d07e9c81efb2cc9b067bb2efa0f68cdb6";
    private JSONObject remote(String digest, long size) throws Exception {
        JSONObject release = new JSONObject();
        release.put("id", 430401431L);
        release.put("draft", true);
        release.put("name", "Pandora OS4 OTA capture — private intake");
        release.put("tag_name", "pandora-ota-capture-430401431");
        JSONObject asset = new JSONObject();
        asset.put("id", 697520792L);
        asset.put("name", "pandora-os4-capture-20261101-060850-483.zip");
        asset.put("size", size);
        asset.put("state", "uploaded");
        asset.put("digest", digest);
        release.put("assets", new JSONArray().put(asset));
        return release;
    }
    private void verify(JSONObject source) throws Exception {
        GitHubUploader.verifyRemoteArchiveMetadata(source, 430401431L, 697520792L,
            "pandora-os4-capture-20261101-060850-483.zip", 89576844L, SHA);
    }
    @Test public void draft404TagPageIsReplacedWithAuthenticatedEditorPage()
            throws Exception {
        JSONObject source = remote("sha256:" + SHA, 89576844L);
        source.put("tag_name", "pandora-ota-capture-430434563");
        source.put("html_url",
            "https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/untagged-de02f5f17b8fcf0fafb5");
        String target = GitHubUploader.verifiedDraftEditorUrlFromMetadata(
            "wekingchen/GKI_KernelSU_SUSFS", source,
            430401431L, 697520792L, "pandora-os4-capture-20261101-060850-483.zip",
            89576844L, SHA);
        assertEquals(
            "https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/edit/untagged-de02f5f17b8fcf0fafb5",
            target);
    }

    @Test public void draftEditorRejectsUntrustedUrlsAndMetadata() throws Exception {
        JSONObject source = remote("sha256:" + SHA, 89576844L);
        source.put("html_url",
            "https://evil.example.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/untagged-xyz");
        try {
            GitHubUploader.verifiedDraftEditorUrlFromMetadata(
                "wekingchen/GKI_KernelSU_SUSFS", source,
                430401431L, 697520792L,
                "pandora-os4-capture-20261101-060850-483.zip", 89576844L, SHA);
            fail("external draft link must never open");
        } catch (SecurityException expected) { }
        source.put("html_url",
            "https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/untagged-xyz");
        source.put("draft", false);
        try {
            GitHubUploader.verifiedDraftEditorUrlFromMetadata(
                "wekingchen/GKI_KernelSU_SUSFS", source,
                430401431L, 697520792L,
                "pandora-os4-capture-20261101-060850-483.zip", 89576844L, SHA);
            fail("published release must not be trusted as private capture draft");
        } catch (SecurityException expected) { }
        source.put("draft", true);
        source.getJSONArray("assets").getJSONObject(0).put("digest", "sha256:" + "0".repeat(64));
        try {
            GitHubUploader.verifiedDraftEditorUrlFromMetadata(
                "wekingchen/GKI_KernelSU_SUSFS", source,
                430401431L, 697520792L,
                "pandora-os4-capture-20261101-060850-483.zip", 89576844L, SHA);
            fail("mismatching asset SHA must not navigate");
        } catch (SecurityException expected) { }
    }

    @Test public void rejectedIntakeStillAllowsAuthenticatedGitHubAsset() throws Exception {
        JSONObject value = remote("sha256:" + SHA, 89576844L);
        value.put("body", "MOBILE_OTA_INTAKE=REJECTED");
        verify(value);
        value.put("tag_name", "untagged-test-draft");
        verify(value);
    }
    @Test public void mismatchedRemoteDigestFailsClosed() throws Exception {
        try {
            verify(remote("sha256:" + "0".repeat(64), 89576844L));
            fail("remote mismatch must not be accepted");
        } catch (SecurityException expected) { }
    }
    @Test public void mismatchedSizeOrAttachmentIdentityFailsClosed() throws Exception {
        try {
            verify(remote("sha256:" + SHA, 89576843L));
            fail("mismatched remote file size");
        } catch (SecurityException expected) { }
        JSONObject source = remote("sha256:" + SHA, 89576844L);
        source.getJSONArray("assets").getJSONObject(0).put("id", 697520793L);
        try {
            verify(source);
            fail("mismatched asset ID");
        } catch (SecurityException expected) { }
    }
    @Test public void nonDraftCannotBeDeletedThroughReceipt() throws Exception {
        JSONObject remote = remote("sha256:" + SHA, 89576844L);
        remote.put("draft", false);
        try {
            verify(remote);
            fail("non draft must fail");
        } catch (SecurityException expected) { }
    }
    @Test public void cleanupRequiresDispatchAndTerminalIntakeButAllowsRejected() throws Exception {
        Context ctx = InstrumentationRegistry.getInstrumentation().getTargetContext();
        SecretStore store = new SecretStore(ctx);
        String oldRepo = store.repo();
        File dir = new File(ctx.getExternalFilesDir(null), "captures");
        assertTrue(dir.exists() || dir.mkdirs());
        File file = new File(dir, "pandora-os4-capture-20261101-131500-123.zip");
        try (FileOutputStream stream = new FileOutputStream(file)) {
            stream.write("synthetic content - not stock input".getBytes());
        }
        try {
            store.saveRepo("wekingchen/GKI_KernelSU_SUSFS");
            store.saveArchive(file.getAbsolutePath());
            GitHubUploader.Result result = new GitHubUploader.Result(
                430401431L, 697520792L, GitHubUploader.sha256(file),
                "https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/test", false);
            store.confirmedUpload(file.getAbsolutePath(), file.length(), result);
            store.saveToken("synthetic_emulator_secret_not_a_real_pat");

            try (ActivityScenario<MainActivity> scenario =
                         ActivityScenario.launch(MainActivity.class)) {
                scenario.onActivity(activity -> {
                    try {
                        java.lang.reflect.Field property = MainActivity.class
                            .getDeclaredField("deleteButton");
                        property.setAccessible(true);
                        assertFalse(((Button) property.get(activity)).isEnabled());
                    } catch (Exception e) { throw new AssertionError(e); }
                });
            }

            store.markDispatchSucceeded();
            try (ActivityScenario<MainActivity> scenario =
                         ActivityScenario.launch(MainActivity.class)) {
                scenario.onActivity(activity -> {
                    try {
                        java.lang.reflect.Field property = MainActivity.class
                            .getDeclaredField("deleteButton");
                        property.setAccessible(true);
                        assertFalse("PENDING must keep local ZIP for status query",
                                ((Button) property.get(activity)).isEnabled());
                    } catch (Exception e) { throw new AssertionError(e); }
                });
            }

            store.recordIntake("REJECTED");
            try (ActivityScenario<MainActivity> scenario =
                         ActivityScenario.launch(MainActivity.class)) {
                scenario.onActivity(activity -> {
                    try {
                        java.lang.reflect.Field property = MainActivity.class
                            .getDeclaredField("deleteButton");
                        property.setAccessible(true);
                        Button control = (Button) property.get(activity);
                        assertTrue(control.isEnabled());
                        assertTrue(control.getText().toString().contains("清理"));
                    } catch (Exception e) { throw new AssertionError(e); }
                });
            }
        } finally {
            file.delete();
            store.forgetArchive();
            store.clearToken();
            store.saveRepo(oldRepo);
        }
    }
}
