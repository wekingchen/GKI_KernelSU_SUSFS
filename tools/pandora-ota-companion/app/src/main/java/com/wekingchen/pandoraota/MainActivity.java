package com.wekingchen.pandoraota;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.text.InputType;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.*;
import java.io.File;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Single-screen, four-step OTA companion. No background transfer is claimed. */
public final class MainActivity extends Activity {
    private static final int BACKGROUND = Color.rgb(244, 247, 251);
    private static final int INK = Color.rgb(29, 44, 62);
    private static final int MUTED = Color.rgb(110, 123, 143);
    private static final int TEAL = Color.rgb(25, 122, 118);
    private static final int LIGHT_TEAL = Color.rgb(229, 245, 241);
    private static final int FIELD = Color.rgb(245, 247, 250);
    private static final int WHITE = Color.WHITE;

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SecretStore store;
    private EditText repoField, tokenField;
    private CheckBox bootOption;
    private Button saveButton, clearButton, rootButton, collectButton, uploadButton;
    private Button deleteButton, openReleaseButton, chooseArchiveButton;
    private TextView tokenState, fileState, uploadStage, uploadNumbers, uploadSpeed;
    private TextView percent, receiptState, message;
    private ProgressBar uploadBar;
    private boolean busy;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SecretStore(this);
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);

        ScrollView scroll = new ScrollView(this);
        scroll.setClipToPadding(false);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);
        LinearLayout content = vertical();
        content.setPadding(dp(18), dp(20), dp(18), dp(32));
        scroll.addView(content);
        setContentView(scroll);
        if (Build.VERSION.SDK_INT >= 35) {
            // Android 15+ edge-to-edge: keep every control above system bars.
            getWindow().getDecorView().setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                content.setPadding(dp(18), dp(20) + bars.top, dp(18), dp(32) + bars.bottom);
                return insets;
            });
        }

        LinearLayout hero = vertical();
        GradientDrawable heroBg = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Color.rgb(24, 43, 65), Color.rgb(31, 86, 102)});
        heroBg.setCornerRadius(dp(22));
        hero.setBackground(heroBg);
        hero.setPadding(dp(20), dp(21), dp(20), dp(20));
        hero.setElevation(dp(3));
        content.addView(hero, blockParams(dp(4)));
        hero.addView(text("PANDORA  /  HYPEROS 4", 11, Color.rgb(151, 227, 217), true));
        hero.addView(text("OTA 采集助手", 25, WHITE, true), blockParams(dp(8)));
        hero.addView(text("从手机采集固件适配数据，安全打包并上传 GitHub。",
                13, Color.rgb(217, 235, 240), false), blockParams(dp(8)));
        hero.addView(text("设备：" + Build.DEVICE + "    Android " + Build.VERSION.RELEASE
                + "    ·    只读模式", 12, Color.rgb(188, 232, 224), false), blockParams(dp(14)));

        LinearLayout connect = card(content, "01", "连接 GitHub", "首次配置一次，以后直接采集和上传");
        connect.addView(text("接收仓库", 12, MUTED, true), blockParams(dp(15)));
        repoField = field("owner/repo", store.repo(), false);
        connect.addView(repoField, blockParams(dp(6)));
        connect.addView(text("GitHub 访问令牌（PAT）", 12, MUTED, true), blockParams(dp(14)));
        tokenField = field("输入或更新令牌；留空不修改已保存令牌", "", true);
        connect.addView(tokenField, blockParams(dp(6)));
        tokenState = text("", 12, TEAL, false);
        connect.addView(tokenState, blockParams(dp(9)));
        connect.addView(text("令牌有效期在 GitHub 创建时设置，本应用不设置到期时间；"
                        + "可长期加密保存，也可随时删除。请仅授权指定接收仓库。",
                12, MUTED, false), blockParams(dp(7)));
        LinearLayout configActions = new LinearLayout(this);
        configActions.setOrientation(LinearLayout.HORIZONTAL);
        connect.addView(configActions, blockParams(dp(13)));
        saveButton = button("保存连接设置", true);
        configActions.addView(saveButton, new LinearLayout.LayoutParams(0, dp(46), 1));
        Space space = new Space(this);
        configActions.addView(space, new LinearLayout.LayoutParams(dp(9), 1));
        clearButton = button("清除令牌", false);
        configActions.addView(clearButton, new LinearLayout.LayoutParams(dp(112), dp(46)));
        saveButton.setOnClickListener(v -> saveConnection());
        clearButton.setOnClickListener(v -> {
            new AlertDialog.Builder(this)
                    .setTitle("删除本机令牌？")
                    .setMessage("只删除本应用内的令牌。若要让令牌立即失效，需要到 GitHub 撤销。")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("删除", (d, which) -> {
                        store.clearToken();
                        tokenField.setText("");
                        refresh();
                        notifyMessage("已清除本机保存的令牌");
                    }).show();
        });

        LinearLayout capture = card(content, "02", "采集设备数据", "申请 Root 后读取 OEM 模块和内核状态");
        capture.addView(text("仅允许 pandora 设备，默认不读取启动分区。",
                12, MUTED, false), blockParams(dp(13)));
        bootOption = new CheckBox(this);
        bootOption.setText("同时备份当前启动分区（可能不是原厂）");
        bootOption.setTextColor(INK);
        bootOption.setTextSize(13);
        bootOption.setButtonTintList(ColorStateList.valueOf(TEAL));
        bootOption.setChecked(false);
        capture.addView(bootOption, blockParams(dp(6)));
        rootButton = button("检查 Root 授权", false);
        capture.addView(rootButton, blockParams(dp(11)));
        collectButton = button("开始采集并打包 ZIP", true);
        capture.addView(collectButton, blockParams(dp(9)));
        rootButton.setOnClickListener(v -> runTask("正在请求 Root 授权…", () ->
                "Root 可用：" + RootCollector.checkRoot()));
        collectButton.setOnClickListener(v -> {
            final boolean includeBoot = bootOption.isChecked();
            runTask("正在只读采集并打包…", () -> {
                File output = RootCollector.capture(getApplicationContext(), includeBoot);
                store.saveArchive(output.getAbsolutePath());
                return "采集完成：" + output.getName() + "（" + size(output.length()) + "）";
            });
        });

        LinearLayout transfer = card(content, "03", "上传到 GitHub", "显示传输进度、速率和服务器确认状态");
        fileState = text("", 13, INK, false);
        fileState.setTextIsSelectable(true);
        transfer.addView(fileState, blockParams(dp(13)));
        chooseArchiveButton = button("切换本地采集包", false);
        transfer.addView(chooseArchiveButton, blockParams(dp(9)));
        chooseArchiveButton.setOnClickListener(v -> chooseArchive());
        uploadButton = button("上传采集包", true);
        transfer.addView(uploadButton, blockParams(dp(14)));
        uploadButton.setOnClickListener(v -> startUpload());
        LinearLayout progressHeader = new LinearLayout(this);
        progressHeader.setGravity(android.view.Gravity.CENTER_VERTICAL);
        progressHeader.setOrientation(LinearLayout.HORIZONTAL);
        transfer.addView(progressHeader, blockParams(dp(16)));
        uploadStage = text("等待上传", 12, MUTED, true);
        progressHeader.addView(uploadStage, new LinearLayout.LayoutParams(0, -2, 1));
        percent = text("0%", 16, TEAL, true);
        progressHeader.addView(percent);
        uploadBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        uploadBar.setMax(100);
        uploadBar.setProgress(0);
        uploadBar.setProgressTintList(ColorStateList.valueOf(TEAL));
        uploadBar.setProgressBackgroundTintList(ColorStateList.valueOf(LIGHT_TEAL));
        transfer.addView(uploadBar, new LinearLayout.LayoutParams(-1, dp(8)));
        uploadNumbers = text("0 B / 0 B", 12, MUTED, false);
        transfer.addView(uploadNumbers, blockParams(dp(12)));
        uploadSpeed = text("速率 --   ·   耗时 --", 12, MUTED, false);
        transfer.addView(uploadSpeed, blockParams(dp(3)));
        receiptState = text("尚未获得 GitHub 上传确认", 12, MUTED, false);
        receiptState.setTextIsSelectable(true);
        transfer.addView(receiptState, blockParams(dp(13)));
        openReleaseButton = button("查看 GitHub 草稿 Release", false);
        transfer.addView(openReleaseButton, blockParams(dp(10)));
        openReleaseButton.setOnClickListener(v -> openRelease());

        LinearLayout cleanup = card(content, "04", "本地文件管理", "文件不会自动删除；仅在确认上传成功后可清理");
        cleanup.addView(text("删除只影响本机 ZIP，不会删除 GitHub 上的附件。",
                12, MUTED, false), blockParams(dp(12)));
        deleteButton = button("删除本地已上传的采集包", false);
        cleanup.addView(deleteButton, blockParams(dp(12)));
        deleteButton.setOnClickListener(v -> confirmDelete());

        message = text("就绪。请按 01 → 02 → 03 顺序操作。", 12, MUTED, false);
        message.setTextIsSelectable(true);
        content.addView(message, blockParams(dp(17)));
        content.addView(text("安全边界：不会刷机、修改内核或自动晋升 LKG；"
                + "上传后仍需现有 OTA 工作流完成检查。完整 OTA 大包分片暂未接入。",
                11, MUTED, false), blockParams(dp(8)));
        refresh();
    }

    private void saveConnection() {
        try {
            String repo = repoField.getText().toString().trim();
            if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"))
                throw new IllegalArgumentException("仓库格式应为 owner/repo");
            String token = tokenField.getText().toString().trim();
            store.saveRepo(repo);
            if (!token.isEmpty()) store.saveToken(token);
            tokenField.setText("");
            refresh();
            notifyMessage("连接设置已保存。令牌由 Android Keystore 加密。");
        } catch (Exception e) {
            notifyMessage("保存失败：" + safeMessage(e));
        }
    }

    private void startUpload() {
        File file = selectedFile();
        if (file == null) {
            notifyMessage("请先采集 ZIP 文件");
            return;
        }
        if (store.isUploaded(new SecretStore.FileInfo(file.getAbsolutePath(), file.length()))) {
            notifyMessage("该采集包已上传成功，无需重复上传");
            return;
        }
        final String repo = store.repo();
        beginBusy("正在准备上传…");
        uploadBar.setProgress(0);
        percent.setText("0%");
        uploadNumbers.setText("0 B / " + size(file.length()));
        uploadSpeed.setText("速率 --   ·   耗时 --");
        receiptState.setText("等待 GitHub 服务器确认");
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        worker.execute(() -> {
            try {
                String token = store.loadToken();
                final long started = SystemClock.elapsedRealtime();
                GitHubUploader.Result result = GitHubUploader.upload(repo, token, file,
                        new GitHubUploader.Listener() {
                    private long lastMs = started;
                    private long lastBytes = 0;
                    @Override
                    public void onStage(String stage) {
                        runOnUiThread(() -> uploadStage.setText(stage));
                    }
                    @Override
                    public void onProgress(long sent, long total) {
                        long now = SystemClock.elapsedRealtime();
                        long interval = now - lastMs;
                        if (sent < total && interval < 350) return;
                        double rate = interval > 0
                                ? (sent - lastBytes) * 1000.0 / interval : 0;
                        lastMs = now;
                        lastBytes = sent;
                        long elapsed = now - started;
                        runOnUiThread(() -> renderProgress(sent, total, rate, elapsed));
                    }
                });
                store.confirmedUpload(file.getAbsolutePath(), file.length(), result);
                runOnUiThread(() -> {
                    finishBusy();
                    uploadStage.setText("GitHub 已确认上传");
                    receiptState.setText("Release #" + result.releaseId
                            + " · 附件 #" + result.assetId
                            + "\nSHA-256：" + result.sha256
                            + "\n工作流通知：" + (result.dispatched
                            ? "请求已发送（不代表工作流已执行）" : "发送失败，需另行处理"));
                    notifyMessage("上传成功，文件仍保存在手机中。可选择手动删除。");
                });
            } catch (Exception e) {
                String error = safeMessage(e);
                runOnUiThread(() -> {
                    finishBusy();
                    uploadStage.setText("上传未确认成功");
                    receiptState.setText("未取得有效服务器回执；请保留本地文件并检查 GitHub 草稿");
                    notifyMessage("上传失败：" + error);
                });
            } finally {
                runOnUiThread(() -> getWindow().clearFlags(
                        WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
            }
        });
    }

    private void renderProgress(long sent, long total, double bytesPerSecond, long elapsed) {
        int value = total <= 0 ? 0 : (int) (sent * 100 / total);
        uploadBar.setProgress(value);
        percent.setText(value + "%");
        uploadNumbers.setText(size(sent) + " / " + size(total));
        uploadSpeed.setText("速率 " + size((long) bytesPerSecond) + "/s"
                + "   ·   耗时 " + (elapsed / 1000) + " 秒");
    }

    private void chooseArchive() {
        File[] archives = store.archives();
        if (archives.length == 0) {
            notifyMessage("本机没有可选的采集包");
            return;
        }
        String[] names = new String[archives.length];
        for (int i = 0; i < archives.length; i++) {
            File f = archives[i];
            boolean uploaded = store.isUploaded(
                    new SecretStore.FileInfo(f.getAbsolutePath(), f.length()));
            names[i] = f.getName() + "\n" + size(f.length()) + " · "
                    + (uploaded ? "已上传" : "待上传");
        }
        new AlertDialog.Builder(this)
                .setTitle("选择本地采集包")
                .setSingleChoiceItems(names, -1, (dialog, which) -> {
                    store.saveArchive(archives[which].getAbsolutePath());
                    dialog.dismiss();
                    refresh();
                    notifyMessage("已切换：" + archives[which].getName());
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void confirmDelete() {
        File file = selectedFile();
        if (file == null || !store.isUploaded(
                new SecretStore.FileInfo(file.getAbsolutePath(), file.length()))) {
            notifyMessage("尚未确认上传成功，禁止删除本地采集包");
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("确认删除本地文件？")
                .setMessage(file.getName() + "\n\n仅删除手机上的采集 ZIP，GitHub 附件不受影响。"
                        + "本地删除后无法在应用内恢复。")
                .setNegativeButton("保留文件", null)
                .setPositiveButton("删除本地 ZIP", (dialog, which) ->
                    runTask("正在删除本地采集包…", () -> {
                        File target = new File(store.lastArchive()).getCanonicalFile();
                        File directory = new File(getExternalFilesDir(null), "captures")
                                .getCanonicalFile();
                        if (!directory.equals(target.getParentFile())
                                || !target.getName().matches(
                                "pandora-os4-capture-\\d{8}-\\d{6}\\.zip")) {
                            throw new SecurityException("路径不在应用的 OTA 采集目录内");
                        }
                        if (!store.isUploaded(new SecretStore.FileInfo(
                                target.getAbsolutePath(), target.length()))) {
                            throw new SecurityException("无 GitHub 成功上传回执");
                        }
                        if (!target.delete()) throw new IllegalStateException("无法删除文件");
                        store.forgetArchive();
                        return "已手动删除本地 ZIP；GitHub 附件已保留";
                    })).show();
    }

    private void openRelease() {
        String url = store.lastReleaseUrl();
        if (!url.startsWith("https://github.com/")) {
            notifyMessage("尚无有效的 GitHub Release 链接");
            return;
        }
        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
    }

    private void refresh() {
        tokenState.setText(store.hasToken()
                ? "● 已加密保存凭据（有效期由 GitHub 管理）"
                : "○ 尚未保存 GitHub 凭据");
        File file = selectedFile();
        boolean exists = file != null;
        boolean uploaded = exists && store.isUploaded(
                new SecretStore.FileInfo(file.getAbsolutePath(), file.length()));
        fileState.setText(exists
                ? file.getName() + "\n" + size(file.length())
                        + "   ·   " + (uploaded ? "已获上传确认" : "待上传")
                : "暂无采集包。请先在上方完成只读采集。");
        saveButton.setEnabled(!busy);
        clearButton.setEnabled(!busy && store.hasToken());
        repoField.setEnabled(!busy);
        tokenField.setEnabled(!busy);
        bootOption.setEnabled(!busy);
        rootButton.setEnabled(!busy && RootCollector.isPandora());
        collectButton.setEnabled(!busy && RootCollector.isPandora());
        uploadButton.setEnabled(!busy && exists && !uploaded && store.hasToken());
        chooseArchiveButton.setEnabled(!busy && store.archives().length > 0);
        deleteButton.setEnabled(!busy && uploaded);
        openReleaseButton.setVisibility(uploaded
                && store.lastReleaseUrl().startsWith("https://github.com/")
                ? View.VISIBLE : View.GONE);
        if (!busy && uploaded) {
            uploadStage.setText("GitHub 已确认上传");
            uploadBar.setProgress(100);
            percent.setText("100%");
            uploadNumbers.setText(size(file.length()) + " / " + size(file.length()));
            uploadSpeed.setText("历史上传完成记录");
            receiptState.setText("GitHub 已确认 · Release #" + store.lastReleaseId()
                    + "\n工作流通知：" + (store.dispatched() ? "已发送请求" : "未成功"));
        }
        if (!busy && !uploaded) {
            uploadStage.setText("等待上传");
            uploadBar.setProgress(0);
            percent.setText("0%");
            uploadNumbers.setText(exists ? "0 B / " + size(file.length()) : "0 B / 0 B");
            uploadSpeed.setText("速率 --   ·   耗时 --");
            receiptState.setText("尚未获得 GitHub 上传确认");
        }
    }

    private File selectedFile() {
        String path = store.lastArchive();
        if (path.isEmpty() || !new File(path).isFile()) {
            File[] files = store.archives();
            if (files.length == 0) return null;
            store.saveArchive(files[0].getAbsolutePath());
            path = files[0].getAbsolutePath();
        }
        File file = new File(path);
        return file.isFile() && file.length() > 0 ? file : null;
    }

    private interface Task { String run() throws Exception; }
    private void runTask(String stage, Task task) {
        beginBusy(stage);
        worker.execute(() -> {
            String result;
            try {
                result = task.run();
            } catch (Exception e) {
                result = "操作失败：" + safeMessage(e);
            }
            final String finalResult = result;
            runOnUiThread(() -> {
                finishBusy();
                refresh();
                notifyMessage(finalResult);
            });
        });
    }

    private void beginBusy(String label) {
        busy = true;
        notifyMessage(label);
        refresh();
    }

    private void finishBusy() {
        busy = false;
        refresh();
    }

    private void notifyMessage(String value) {
        message.setText(value);
    }

    private static String safeMessage(Exception e) {
        String detail = e.getMessage();
        if (detail == null || detail.isEmpty()) return e.getClass().getSimpleName();
        return detail.length() > 260 ? detail.substring(0, 260) : detail;
    }

    private String size(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format(Locale.CHINA, "%.1f KiB", bytes / 1024.0);
        if (bytes < 1024L * 1024 * 1024)
            return String.format(Locale.CHINA, "%.2f MiB", bytes / (1024.0 * 1024));
        return String.format(Locale.CHINA, "%.2f GiB",
                bytes / (1024.0 * 1024 * 1024));
    }

    private LinearLayout card(LinearLayout parent, String step, String title, String sub) {
        LinearLayout card = vertical();
        card.setBackground(round(WHITE, dp(20)));
        card.setPadding(dp(18), dp(17), dp(18), dp(20));
        card.setElevation(dp(2));
        parent.addView(card, blockParams(dp(16)));
        LinearLayout header = new LinearLayout(this);
        header.setGravity(android.view.Gravity.CENTER_VERTICAL);
        card.addView(header);
        TextView badge = text(step, 12, TEAL, true);
        badge.setGravity(android.view.Gravity.CENTER);
        badge.setBackground(round(LIGHT_TEAL, dp(11)));
        header.addView(badge, new LinearLayout.LayoutParams(dp(35), dp(34)));
        LinearLayout heading = vertical();
        LinearLayout.LayoutParams hp = new LinearLayout.LayoutParams(0, -2, 1);
        hp.leftMargin = dp(11);
        header.addView(heading, hp);
        heading.addView(text(title, 17, INK, true));
        heading.addView(text(sub, 12, MUTED, false), blockParams(dp(3)));
        return card;
    }

    private LinearLayout vertical() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout.LayoutParams blockParams(int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.topMargin = top;
        return p;
    }

    private TextView text(String value, float sp, int color, boolean bold) {
        TextView item = new TextView(this);
        item.setText(value);
        item.setTextSize(sp);
        item.setTextColor(color);
        if (bold) item.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        item.setLineSpacing(dp(2), 1f);
        return item;
    }

    private EditText field(String hint, String value, boolean password) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextSize(14);
        input.setTextColor(INK);
        input.setHintTextColor(MUTED);
        input.setHint(hint);
        input.setText(value);
        input.setPadding(dp(13), dp(12), dp(13), dp(12));
        input.setBackground(round(FIELD, dp(11)));
        input.setInputType(InputType.TYPE_CLASS_TEXT
                | (password ? InputType.TYPE_TEXT_VARIATION_PASSWORD :
                InputType.TYPE_TEXT_VARIATION_NORMAL));
        return input;
    }

    private Button button(String caption, boolean primary) {
        Button b = new Button(this);
        b.setText(caption);
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setTextColor(primary ? WHITE : TEAL);
        b.setBackground(round(primary ? TEAL : LIGHT_TEAL, dp(12)));
        b.setMinHeight(dp(46));
        b.setMinimumHeight(dp(46));
        b.setPadding(dp(12), 0, dp(12), 0);
        return b;
    }

    private GradientDrawable round(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radius);
        return drawable;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + .5f);
    }

    @Override
    protected void onDestroy() {
        worker.shutdown();
        super.onDestroy();
    }
}
