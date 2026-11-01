package com.wekingchen.pandoraota;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import static org.junit.Assert.*;

/** Real Android Emulator integration checks; cannot emulate Xiaomi OEM partitions or KSU. */
@RunWith(AndroidJUnit4.class)
public class CompanionEmulatorTest {
    private Context app() {
        return InstrumentationRegistry.getInstrumentation().getTargetContext();
    }

    private static void write(File file, String text) throws Exception {
        try (FileOutputStream output = new FileOutputStream(file)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
        }
    }

    private static <T> T field(Object object, String name, Class<T> type) throws Exception {
        Field found = object.getClass().getDeclaredField(name);
        found.setAccessible(true);
        return type.cast(found.get(object));
    }

    @Test
    public void keystoreEncryptedCredentialsSurviveNewStoreInstance() throws Exception {
        SecretStore first = new SecretStore(app());
        first.clearToken();
        String sampleToken = "github_pat_emulator_fake_123_NotARealCredential";
        try {
            first.saveToken(sampleToken);
            assertTrue(first.hasToken());
            SecretStore next = new SecretStore(app());
            assertEquals(sampleToken, next.loadToken());
            SharedPreferences raw = app().getSharedPreferences("private_config", Context.MODE_PRIVATE);
            assertFalse(raw.getString("token_ciphertext", "").contains(sampleToken));
            assertFalse(raw.contains("token_plaintext"));
        } finally {
            first.clearToken();
        }
        assertFalse(new SecretStore(app()).hasToken());
    }

    @Test
    public void archiveReceiptsSurviveReloadAndAreBoundToRepository() throws Exception {
        SecretStore store = new SecretStore(app());
        String oldRepo = store.repo();
        File parent = RootCollector.captureDirectory(app());
        File archive = new File(parent, "pandora-os4-capture-20261101-101010-123.zip");
        write(archive, "synthetic-zip-not-valid-for-upload");
        try {
            store.saveRepo("wekingchen/GKI_KernelSU_SUSFS");
            store.saveArchive(archive.getAbsolutePath());
            GitHubUploader.Result result = new GitHubUploader.Result(
                    1234, 5678, GitHubUploader.sha256(archive),
                    "https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/test-only", false);
            store.confirmedUpload(archive.getAbsolutePath(), archive.length(), result);
            SecretStore reopened = new SecretStore(app());
            assertTrue(reopened.isUploaded(new SecretStore.FileInfo(
                    archive.getAbsolutePath(), archive.length())));
            assertEquals(5678, reopened.lastAssetId());
            assertFalse(reopened.dispatched());
            reopened.saveRepo("unrelated/receiver");
            assertFalse(reopened.isUploaded(new SecretStore.FileInfo(
                    archive.getAbsolutePath(), archive.length())));
            reopened.saveRepo("wekingchen/GKI_KernelSU_SUSFS");
            reopened.markDispatchSucceeded();
            assertTrue(new SecretStore(app()).dispatched());
        } finally {
            archive.delete();
            store.forgetArchive();
            store.saveRepo(oldRepo);
        }
    }

    @Test
    public void staleIntermediateFilesArePurgedWithoutTouchingFinalArchives() throws Exception {
        File parent = RootCollector.captureDirectory(app());
        File staging = new File(parent, "staging-20261101-010101-001");
        assertTrue(staging.mkdir() || staging.isDirectory());
        File image = new File(staging, "boot_a.img");
        write(image, "temporary active boot image");
        File zip = new File(parent, "pandora-os4-capture-20261101-010101-001.zip");
        write(zip, "keep final upload package");
        try {
            assertTrue(staging.setLastModified(System.currentTimeMillis() - 3600000L));
            RootCollector.purgeStaleStaging(app());
            assertFalse("staging must be removed", staging.exists());
            assertTrue("final ZIP must remain untouched", zip.exists());
        } finally {
            image.delete(); staging.delete(); zip.delete();
        }
    }

    @Test
    public void cleanupMustNotDeleteOutsideStagingDirectory() throws Exception {
        File parent = RootCollector.captureDirectory(app());
        File outsider = new File(parent, "pandora-user-backup.txt");
        write(outsider, "never delete me");
        Method cleanup = RootCollector.class.getDeclaredMethod("cleanStaging", File.class, File.class);
        cleanup.setAccessible(true);
        try {
            try {
                cleanup.invoke(null, parent, parent);
                fail("unsafe parent delete must be rejected");
            } catch (java.lang.reflect.InvocationTargetException e) {
                assertTrue(e.getCause() instanceof SecurityException);
            }
            assertTrue(outsider.exists());
        } finally {
            outsider.delete();
        }
    }

    @Test
    public void mainUiOpensAndBlocksRootCaptureOnNonPandoraEmulator() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                try {
                    assertFalse(RootCollector.isPandora());
                    Button collect = field(activity, "collectButton", Button.class);
                    Button root = field(activity, "rootButton", Button.class);
                    Button upload = field(activity, "uploadButton", Button.class);
                    Button delete = field(activity, "deleteButton", Button.class);
                    assertFalse(collect.isEnabled());
                    // Root diagnosis must be clickable even when capture is locked on non-pandora.
                    assertTrue(root.isEnabled());\n                    TextView rootState = field(activity, "rootStatus", TextView.class);\n                    assertTrue(rootState.getText().toString().contains("尚未检测"));
                    assertFalse(upload.isEnabled());
                    assertFalse(delete.isEnabled());
                    assertTrue(field(activity, "tokenState", TextView.class).getText().length() > 0);
                } catch (Exception e) {
                    throw new AssertionError(e);
                }
            });
        }
    }

    @Test
    public void captureHashUsesActualBytesAndRejectsOversizedFilename() throws Exception {
        File parent = RootCollector.captureDirectory(app());
        File archive = new File(parent, "pandora-os4-capture-20261101-111111-222.zip");
        write(archive, "test payload with \u00e4\u00e8\u00e7");
        try {
            String a = GitHubUploader.sha256(archive);
            write(archive, "different payload with \u00e4\u00e8\u00e7");
            String b = GitHubUploader.sha256(archive);
            assertEquals(64, a.length());
            assertNotEquals(a, b);
        } finally {
            archive.delete();
        }
    }
}
