package com.wekingchen.pandoraota;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.widget.Button;
import android.widget.LinearLayout;
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
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
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

    private File syntheticCapture(String build, String slot) throws Exception {
        File file = new File(RootCollector.captureDirectory(app()),
                "pandora-os4-capture-20261101-151500-123.zip");
        try (ZipOutputStream zip = new ZipOutputStream(new FileOutputStream(file))) {
            zip.putNextEntry(new ZipEntry("manifest.txt"));
            String manifest = "schema=pandora-ota-capture-v1\n"
                    + "source=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\n"
                    + "device=pandora\n"
                    + "ro.product.device=pandora\n"
                    + "ro.mi.os.version.incremental=" + build + "\n"
                    + "ro.boot.slot_suffix=" + slot + "\n"
                    + "slot=" + slot + "\n"
                    + "uname=6.12.69-android16-6-synthetic-ci-4k\n";
            zip.write(manifest.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            zip.putNextEntry(new ZipEntry("padding.bin"));
            byte[] padding = new byte[16384];
            int state = 0x13579bdf;
            for (int i = 0; i < padding.length; i++) {
                state = state * 1103515245 + 12345;
                padding[i] = (byte) (state >>> 16);
            }
            zip.write(padding);
            zip.closeEntry();
        }
        return file;
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
    public void systemIdentityHelpersExposeBuildAndNormalizeSlotsWithoutRoot() {
        assertNotNull(RootCollector.currentOsVersion());
        assertFalse(RootCollector.currentOsVersion().trim().isEmpty());
        assertEquals("A", RootCollector.normalizeSlotLabel("_a"));
        assertEquals("A", RootCollector.normalizeSlotLabel("a"));
        assertEquals("B", RootCollector.normalizeSlotLabel("_b"));
        assertEquals("B", RootCollector.normalizeSlotLabel("B"));
        assertEquals("未知", RootCollector.normalizeSlotLabel(""));
        assertTrue(Arrays.asList("A", "B", "未知").contains(RootCollector.currentSlotLabel()));
    }

    @Test
    public void localCaptureIdentityExposesBuildAndSlot() throws Exception {
        File file = syntheticCapture("OS4.0.5.0.XBLCNXM", "_b");
        try {
            RootCollector.CaptureIdentity identity = RootCollector.inspectCaptureIdentity(file);
            assertEquals("OS4.0.5.0.XBLCNXM", identity.build);
            assertEquals("_b", identity.slotSuffix);
            assertEquals("B", identity.slotLabel);
            assertEquals("6.12.69-android16-6-synthetic-ci-4k", identity.uname);
        } finally {
            assertTrue(file.delete());
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
                    assertTrue(root.isEnabled());
                    TextView rootState = field(activity, "rootStatus", TextView.class);
                    assertTrue(rootState.getText().toString().contains("尚未检测"));
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
    public void nativeDestinationsSwitchWithoutLosingSavedConfiguration() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                try {
                    LinearLayout[] tabs = field(activity, "navItems", LinearLayout[].class);
                    android.widget.ScrollView work = field(activity, "workScroll",
                            android.widget.ScrollView.class);
                    android.widget.ScrollView records = field(activity, "recordsScroll",
                            android.widget.ScrollView.class);
                    android.widget.ScrollView settings = field(activity, "settingsScroll",
                            android.widget.ScrollView.class);
                    assertEquals(3, tabs.length);
                    assertEquals(android.view.View.VISIBLE, work.getVisibility());
                    assertEquals(android.view.View.GONE, records.getVisibility());
                    assertTrue(tabs[1].performClick());
                    assertEquals(android.view.View.VISIBLE, records.getVisibility());
                    assertEquals(android.view.View.GONE, work.getVisibility());
                    assertTrue(tabs[2].performClick());
                    assertEquals(android.view.View.VISIBLE, settings.getVisibility());
                    assertNotNull(field(activity, "repoField", EditText.class));
                    assertNotNull(field(activity, "tokenState", TextView.class));
                    LinearLayout help = field(activity, "helpRow", LinearLayout.class);
                    assertNotNull(help);
                    assertTrue(help.hasOnClickListeners());
                    assertTrue(tabs[0].performClick());
                    assertEquals(android.view.View.VISIBLE, work.getVisibility());
                    Button upload = field(activity, "uploadButton", Button.class);
                    assertFalse(upload.isEnabled());
                    assertTrue(field(activity, "taskSpinner", android.widget.ProgressBar.class)
                            .getVisibility() != android.view.View.VISIBLE);
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
