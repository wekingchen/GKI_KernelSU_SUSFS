package com.wekingchen.pandoraota;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.Assert.*;

/** In-process fake GitHub HTTPS connections. Never talks to the user's GitHub repository. */
@RunWith(AndroidJUnit4.class)
public class GitHubUploadEmulatorTest {
    private File newPayload() throws IOException {
        File file = new File(InstrumentationRegistry.getInstrumentation()
                .getTargetContext().getCacheDir(), "synthetic-capture-test.zip");
        try (OutputStream output = new FileOutputStream(file)) {
            byte[] data = new byte[100 * 1024];
            for (int n = 0; n < data.length; n++) data[n] = (byte) (n * 19 + 3);
            output.write(data);
        }
        return file;
    }

    static final class FakeGitHub implements GitHubUploader.ConnectionFactory {
        final List<FakeConnection> connections = new ArrayList<>();
        long expectedBytes;
        boolean rejectUpload;
        boolean rejectDispatch;
        @Override public HttpURLConnection open(URL url) {
            FakeConnection connection = new FakeConnection(url, this);
            connections.add(connection);
            return connection;
        }
        int countPaths(String suffix) {
            int matches = 0;
            for (FakeConnection c : connections)
                if (c.url.getPath().endsWith(suffix)) matches++;
            return matches;
        }
    }

    static final class FakeConnection extends HttpURLConnection {
        final URL url;
        final FakeGitHub fake;
        final ByteArrayOutputStream posted = new ByteArrayOutputStream();
        FakeConnection(URL target, FakeGitHub fake) {
            super(target);
            this.url = target;
            this.fake = fake;
        }
        @Override public void connect() {}
        @Override public void disconnect() {}
        @Override public boolean usingProxy() { return false; }
        @Override public OutputStream getOutputStream() { return posted; }
        @Override public int getResponseCode() {
            if (url.getHost().equals("uploads.github.com")) return fake.rejectUpload ? 503 : 201;
            if (url.getPath().endsWith("/dispatches")) return fake.rejectDispatch ? 403 : 204;
            return 201;
        }
        @Override public InputStream getErrorStream() {
            return new ByteArrayInputStream("{\"message\":\"synthetic error\"}"
                    .getBytes(StandardCharsets.UTF_8));
        }
        @Override public InputStream getInputStream() {
            String body;
            if (url.getHost().equals("uploads.github.com")) {
                body = "{\"id\":456,\"size\":" + fake.expectedBytes + "}";
            } else if (url.getPath().endsWith("/releases")) {
                body = "{\"id\":123,\"draft\":true,"
                        + "\"html_url\":\"https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/test\","
                        + "\"upload_url\":\"https://uploads.github.com/repos/wekingchen/"
                        + "GKI_KernelSU_SUSFS/releases/123/assets{?name,label}\"}";
            } else {
                body = "";
            }
            return new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8));
        }
    }

    @Test
    public void successfulTransportReportsProgressAndSeparateServerConfirmation() throws Exception {
        File file = newPayload();
        try {
            FakeGitHub fake = new FakeGitHub();
            fake.expectedBytes = file.length();
            AtomicLong latestBytes = new AtomicLong(-1);
            List<String> stages = new ArrayList<>();
            GitHubUploader.Result result = GitHubUploader.uploadWithTransport(
                    "wekingchen/GKI_KernelSU_SUSFS", "synthetic_test_token", file,
                    new GitHubUploader.Listener() {
                        @Override public void onStage(String stage) { stages.add(stage); }
                        @Override public void onProgress(long sent, long total) {
                            assertEquals(file.length(), total);
                            assertTrue(sent >= 0 && sent <= total);
                            latestBytes.set(sent);
                        }
                    }, fake);
            assertTrue(result.dispatched);
            assertEquals(123, result.releaseId);
            assertEquals(456, result.assetId);
            assertEquals(GitHubUploader.sha256(file), result.sha256);
            assertEquals(file.length(), latestBytes.get());
            assertEquals(1, fake.countPaths("/dispatches"));
            assertTrue(stages.contains("已发送 100%，等待 GitHub 确认"));
            assertEquals(3, fake.connections.size());
            for (FakeConnection c : fake.connections) {
                assertEquals("Bearer synthetic_test_token",
                        c.getRequestProperty("Authorization"));
                assertEquals("https", c.url.getProtocol());
            }
            FakeConnection binary = fake.connections.get(1);
            assertArrayEquals(java.nio.file.Files.readAllBytes(file.toPath()),
                              binary.posted.toByteArray());
        } finally {
            assertTrue(file.delete());
        }
    }

    @Test
    public void serverRejectsUploadAndLocalZipRemains() throws Exception {
        File file = newPayload();
        try {
            FakeGitHub fake = new FakeGitHub();
            fake.expectedBytes = file.length();
            fake.rejectUpload = true;
            try {
                GitHubUploader.uploadWithTransport(
                        "wekingchen/GKI_KernelSU_SUSFS", "synthetic_test_token", file,
                        new GitHubUploader.Listener() {
                            @Override public void onStage(String s) {}
                            @Override public void onProgress(long a, long b) {}
                        }, fake);
                fail("HTTP 503 must not count as a confirmed upload");
            } catch (IOException expected) {
                assertTrue(expected.getMessage().contains("503"));
            }
            assertTrue(file.exists());
            assertEquals(0, fake.countPaths("/dispatches"));
        } finally {
            assertTrue(file.delete());
        }
    }

    @Test
    public void dispatchRejectionDoesNotClaimBackendWasStarted() throws Exception {
        File file = newPayload();
        try {
            FakeGitHub fake = new FakeGitHub();
            fake.expectedBytes = file.length();
            fake.rejectDispatch = true;
            GitHubUploader.Result result = GitHubUploader.uploadWithTransport(
                    "wekingchen/GKI_KernelSU_SUSFS", "synthetic_test_token", file,
                    new GitHubUploader.Listener() {
                        @Override public void onStage(String s) {}
                        @Override public void onProgress(long a, long b) {}
                    }, fake);
            assertFalse(result.dispatched);
            assertTrue(file.exists());
            assertEquals(1, fake.countPaths("/dispatches"));
            assertEquals(456, result.assetId);
        } finally {
            assertTrue(file.delete());
        }
    }
}
