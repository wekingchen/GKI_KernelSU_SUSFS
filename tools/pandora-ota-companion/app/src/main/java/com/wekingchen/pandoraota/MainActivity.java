package com.wekingchen.pandoraota;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.MotionEvent;
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
    private static final int BACKGROUND = Color.rgb(247, 249, 248);
    private static final int INK = Color.rgb(28, 46, 43);
    private static final int MUTED = Color.rgb(111, 129, 123);
    private static final int TEAL = Color.rgb(34, 107, 101);
    private static final int LIGHT_TEAL = Color.rgb(231, 244, 240);
    private static final int FIELD = Color.rgb(241, 245, 243);
    private static final int BORDER = Color.rgb(226, 235, 231);
    private static final int NOTICE = Color.rgb(237, 245, 242);
    private static final int WARNING = Color.rgb(159, 85, 45);
    private static final int WHITE = Color.WHITE;

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SecretStore store;
    private EditText repoField, tokenField;
    private CheckBox bootOption;
    private Button saveButton, clearButton, rootButton, collectButton, uploadButton;
    private Button deleteButton, openReleaseButton, chooseArchiveButton, retryNoticeButton, checkIntakeButton;
    private TextView tokenState, fileState, uploadStage, uploadNumbers, uploadSpeed;
    private TextView percent, receiptState, message, rootStatus;
    private ProgressBar uploadBar, taskSpinner;
    private ScrollView workScroll, recordsScroll, settingsScroll;
    private LinearLayout archiveListing;
    private TextView deviceStatus, rootPill, intakeSummary, recordFileState;
    private final LinearLayout[] navItems = new LinearLayout[3];
    private final TextView[] navIcons = new TextView[3];
    private final TextView[] navLabels = new TextView[3];
    private int activeTab;
    private boolean busy;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SecretStore(this);
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);

        // A native Android shell: persistent status, three actual destinations,
        // bottom navigation and a single focused action at a time.
        LinearLayout shell = vertical();
        shell.setBackgroundColor(BACKGROUND);
        shell.setClipChildren(false);
        shell.setClipToPadding(false);
        setContentView(shell);
        if (Build.VERSION.SDK_INT >= 35) {
            getWindow().getDecorView().setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                shell.setPadding(0, bars.top, 0, bars.bottom);
                return insets;
            });
        }
        LinearLayout topBar = new LinearLayout(this);
        topBar.setGravity(android.view.Gravity.CENTER_VERTICAL);
        topBar.setPadding(dp(22), dp(11), dp(20), dp(11));
        shell.addView(topBar, new LinearLayout.LayoutParams(-1, dp(70)));
        TextView brand = text("P", 19, WHITE, true);
        brand.setGravity(android.view.Gravity.CENTER);
        brand.setBackground(round(TEAL, dp(14)));
        topBar.addView(brand, new LinearLayout.LayoutParams(dp(44), dp(44)));
        LinearLayout brandTitle = vertical();
        LinearLayout.LayoutParams brandParams = new LinearLayout.LayoutParams(0, -2, 1);
        brandParams.leftMargin = dp(12);
        topBar.addView(brandTitle, brandParams);
        brandTitle.addView(text("Pandora", 21, INK, true));
        brandTitle.addView(text("OS4  ·  OTA 采集助手", 11, MUTED, false), blockParams(dp(2)));
        TextView readonly = text("只读模式", 11, TEAL, true);
        readonly.setGravity(android.view.Gravity.CENTER);
        readonly.setBackground(round(LIGHT_TEAL, dp(18)));
        readonly.setPadding(dp(12), dp(7), dp(12), dp(7));
        topBar.addView(readonly);

        LinearLayout notice = new LinearLayout(this);
        notice.setGravity(android.view.Gravity.CENTER_VERTICAL);
        notice.setBackground(round(NOTICE, dp(15)));
        notice.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams noticeParams = new LinearLayout.LayoutParams(-1, -2);
        noticeParams.setMargins(dp(20), dp(4), dp(20), dp(6));
        shell.addView(notice, noticeParams);
        taskSpinner = new ProgressBar(this, null, android.R.attr.progressBarStyleSmall);
        taskSpinner.setIndeterminateTintList(ColorStateList.valueOf(TEAL));
        notice.addView(taskSpinner, new LinearLayout.LayoutParams(dp(20), dp(20)));
        message = text("已就绪 · 可以检查 Root 或查看采集记录", 12, INK, false);
        message.setMaxLines(4);
        message.setTextIsSelectable(true);
        LinearLayout.LayoutParams msgParams = new LinearLayout.LayoutParams(0, -2, 1);
        msgParams.leftMargin = dp(9);
        notice.addView(message, msgParams);
        taskSpinner.setVisibility(View.GONE);

        FrameLayout destinations = new FrameLayout(this);
        shell.addView(destinations, new LinearLayout.LayoutParams(-1, 0, 1));
        workScroll = page(destinations);
        recordsScroll = page(destinations);
        settingsScroll = page(destinations);
        LinearLayout work = pageContents(workScroll);
        LinearLayout records = pageContents(recordsScroll);
        LinearLayout settings = pageContents(settingsScroll);

        // Workbench — the entire Root → capture → upload journey stays together.
        LinearLayout overview = surfaceCard(work, dp(5), dp(20));
        LinearLayout identity = new LinearLayout(this);
        identity.setGravity(android.view.Gravity.CENTER_VERTICAL);
        overview.addView(identity);
        LinearLayout info = vertical();
        identity.addView(info, new LinearLayout.LayoutParams(0, -2, 1));
        info.addView(text("设备工作台", 23, INK, true));
        info.addView(text("你的内核适配快照", 13, MUTED, false), blockParams(dp(5)));
        TextView deviceGlyph = text("⌘", 25, TEAL, true);
        deviceGlyph.setGravity(android.view.Gravity.CENTER);
        deviceGlyph.setBackground(round(LIGHT_TEAL, dp(17)));
        identity.addView(deviceGlyph, new LinearLayout.LayoutParams(dp(55), dp(55)));
        deviceStatus = text(RootCollector.isPandora() ? "●  已识别 Xiaomi 17 Pro · pandora"
                        : "●  当前设备不是 pandora，采集受限",
                12, RootCollector.isPandora() ? TEAL : WARNING, true);
        overview.addView(deviceStatus, blockParams(dp(17)));
        overview.addView(text("Android " + Build.VERSION.RELEASE
                + "   ·   Build.DEVICE: " + Build.DEVICE, 12, MUTED, false),
                blockParams(dp(5)));

        LinearLayout capture = surfaceCard(work, dp(14), dp(20));
        capture.addView(sectionHeading("01", "从设备采集", "只读读取当前活动 slot"));
        LinearLayout safetyRow = new LinearLayout(this);
        safetyRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        capture.addView(safetyRow, blockParams(dp(17)));
        rootPill = text("ROOT 待检测", 11, MUTED, true);
        rootPill.setPadding(dp(10), dp(7), dp(10), dp(7));
        rootPill.setBackground(round(FIELD, dp(15)));
        safetyRow.addView(rootPill);
        TextView protectedTag = text("不修改启动分区", 11, MUTED, false);
        LinearLayout.LayoutParams pt = new LinearLayout.LayoutParams(0, -2, 1);
        pt.leftMargin = dp(10);
        safetyRow.addView(protectedTag, pt);
        rootButton = button("检查 Root 权限", false);
        capture.addView(rootButton, blockParams(dp(15)));
        rootStatus = text("尚未检测 Root；如不弹窗，请在 Root 管理器手动授权。", 12, MUTED, false);
        rootStatus.setTextIsSelectable(true);
        capture.addView(rootStatus, blockParams(dp(10)));
        bootOption = new CheckBox(this);
        bootOption.setChecked(true);
        bootOption.setEnabled(false);
        bootOption.setVisibility(View.GONE);
        capture.addView(text("采集内容  ·  Boot / Init Boot / Vendor Boot / DTBO / OEM 模块",
                12, MUTED, false), blockParams(dp(21)));
        collectButton = button("采集并生成 ZIP", true);
        capture.addView(collectButton, blockParams(dp(10)));
        capture.addView(text("采集期间请保持应用处于前台；完成后仅保留最终 ZIP。",
                11, MUTED, false), blockParams(dp(10)));
        rootButton.setOnClickListener(v -> {
            rootStatus.setText("正在请求 Root 授权（最长 45 秒）…");
            rootPill.setText("ROOT 检查中");
            runTask("正在向 Root 管理器请求授权…", () -> {
                try {
                    String identityResult = RootCollector.checkRoot();
                    runOnUiThread(() -> {
                        rootPill.setText("ROOT 已授权");
                        rootPill.setTextColor(TEAL);
                        rootPill.setBackground(round(LIGHT_TEAL, dp(15)));
                        rootStatus.setText("授权成功：" + identityResult);
                    });
                    return "Root 已授权，可安全进行只读采集。";
                } catch (Exception e) {
                    String explanation = safeMessage(e);
                    runOnUiThread(() -> {
                        rootPill.setText("ROOT 未授权");
                        rootPill.setTextColor(WARNING);
                        rootStatus.setText("授权失败：" + explanation
                                + "\n请在 Root 管理器的超级用户列表中授权此应用。");
                    });
                    throw e;
                }
            });
        });
        collectButton.setOnClickListener(v -> runTask("正在读取分区并生成 ZIP…", () -> {
            File output = RootCollector.capture(getApplicationContext(), true);
            store.saveArchive(output.getAbsolutePath());
            return "采集完成：" + output.getName() + "（" + size(output.length()) + "）"
                    + "\n临时分区镜像及模块归档已清理。";
        }));

        LinearLayout transfer = surfaceCard(work, dp(14), dp(20));
        transfer.addView(sectionHeading("02", "上传到 GitHub", "上传成功与后端审计是两个不同步骤"));
        fileState = text("", 12, INK, true);
        fileState.setTextIsSelectable(true);
        transfer.addView(fileState, blockParams(dp(17)));
        uploadButton = button("上传当前采集包", true);
        transfer.addView(uploadButton, blockParams(dp(13)));
        uploadButton.setOnClickListener(v -> startUpload());
        LinearLayout progressHeader = new LinearLayout(this);
        progressHeader.setGravity(android.view.Gravity.CENTER_VERTICAL);
        transfer.addView(progressHeader, blockParams(dp(19)));
        uploadStage = text("等待上传", 12, MUTED, true);
        progressHeader.addView(uploadStage, new LinearLayout.LayoutParams(0, -2, 1));
        percent = text("0%", 17, TEAL, true);
        progressHeader.addView(percent);
        uploadBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        uploadBar.setMax(100);
        uploadBar.setProgressTintList(ColorStateList.valueOf(TEAL));
        uploadBar.setProgressBackgroundTintList(ColorStateList.valueOf(LIGHT_TEAL));
        transfer.addView(uploadBar, new LinearLayout.LayoutParams(-1, dp(6)));
        uploadNumbers = text("0 B / 0 B", 12, MUTED, false);
        transfer.addView(uploadNumbers, blockParams(dp(11)));
        uploadSpeed = text("速率 --   ·   耗时 --", 11, MUTED, false);
        transfer.addView(uploadSpeed, blockParams(dp(3)));
        intakeSummary = text("尚无后端接收结果", 12, MUTED, false);
        transfer.addView(intakeSummary, blockParams(dp(16)));
        checkIntakeButton = button("查询后端处理结果", false);
        transfer.addView(checkIntakeButton, blockParams(dp(10)));
        checkIntakeButton.setOnClickListener(v -> checkBackendIntake());
        transfer.addView(text("同版本 Boot 不一致会被安全拒收，不会替换固定固件或 LKG。",
                11, MUTED, false), blockParams(dp(14)));

        // Records — detail, history, diagnostic receipt and destructive actions.
        records.addView(pageHeading("采集记录", "本地文件与 GitHub 接收状态分开记录"));
        LinearLayout latest = surfaceCard(records, dp(12), dp(19));
        latest.addView(text("当前采集包", 15, INK, true));
        recordFileState = text("", 13, MUTED, false);
        recordFileState.setTextIsSelectable(true);
        latest.addView(recordFileState, blockParams(dp(12)));
        chooseArchiveButton = button("切换本地采集包", false);
        latest.addView(chooseArchiveButton, blockParams(dp(12)));
        chooseArchiveButton.setOnClickListener(v -> chooseArchive());

        LinearLayout details = surfaceCard(records, dp(14), dp(19));
        details.addView(text("服务器回执", 15, INK, true));
        receiptState = text("", 12, MUTED, false);
        receiptState.setTextIsSelectable(true);
        details.addView(receiptState, blockParams(dp(12)));
        openReleaseButton = button("在 GitHub 查看采集附件", false);
        details.addView(openReleaseButton, blockParams(dp(11)));
        openReleaseButton.setOnClickListener(v -> openRelease());
        retryNoticeButton = button("重新通知 GitHub（不重复上传）", false);
        details.addView(retryNoticeButton, blockParams(dp(9)));
        retryNoticeButton.setOnClickListener(v -> retryDispatch());
        LinearLayout listing = surfaceCard(records, dp(14), dp(19));
        listing.addView(text("本地文件", 15, INK, true));
        archiveListing = vertical();
        listing.addView(archiveListing, blockParams(dp(9)));
        LinearLayout cleanup = surfaceCard(records, dp(14), dp(19));
        cleanup.addView(text("存储空间", 15, INK, true));
        cleanup.addView(text("必须由 GitHub 确认接收，并再次校验本地 SHA-256 后，才允许删除。",
                12, MUTED, false), blockParams(dp(9)));
        deleteButton = button("删除已接收的本地 ZIP", false);
        cleanup.addView(deleteButton, blockParams(dp(12)));
        deleteButton.setOnClickListener(v -> confirmDelete());

        // Settings — credentials are intentionally off the workbench.
        settings.addView(pageHeading("连接与安全", "仅配置一次，正常使用时无需进入"));
        LinearLayout connect = surfaceCard(settings, dp(12), dp(19));
        connect.addView(text("GitHub 仓库", 13, INK, true));
        repoField = field("owner/repo", store.repo(), false);
        connect.addView(repoField, blockParams(dp(8)));
        connect.addView(text("Fine-grained PAT", 13, INK, true), blockParams(dp(17)));
        tokenField = field("留空则保留已保存的令牌", "", true);
        connect.addView(tokenField, blockParams(dp(8)));
        tokenState = text("", 12, TEAL, true);
        connect.addView(tokenState, blockParams(dp(12)));
        saveButton = button("保存连接设置", true);
        connect.addView(saveButton, blockParams(dp(15)));
        clearButton = button("清除本机令牌", false);
        connect.addView(clearButton, blockParams(dp(9)));
        saveButton.setOnClickListener(v -> saveConnection());
        clearButton.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("删除本机令牌？")
                .setMessage("仅删除应用内加密凭据。要使令牌立即失效，请前往 GitHub 撤销。")
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) -> {
                    store.clearToken();
                    tokenField.setText("");
                    refresh();
                    notifyMessage("本机 GitHub 令牌已删除");
                }).show());
        LinearLayout security = surfaceCard(settings, dp(14), dp(19));
        security.addView(text("安全边界", 15, INK, true));
        security.addView(text("设备：" + Build.DEVICE + " / " + Build.PRODUCT,
                12, MUTED, false), blockParams(dp(13)));
        security.addView(text("· 不刷机、不修改活动分区、不自动晋升 LKG\n"
                        + "· 只读采集必须为 pandora\n"
                        + "· 仅 GitHub 接收成功后允许删除本地 ZIP\n"
                        + "· 前台运行上传任务，不承诺后台断点续传",
                12, MUTED, false), blockParams(dp(12)));
        security.addView(text("版本  ·  " + getAppVersion(), 11, MUTED, false),
                blockParams(dp(13)));

        // Material-like native bottom destination bar, always visible.
        LinearLayout bottom = new LinearLayout(this);
        bottom.setGravity(android.view.Gravity.CENTER_VERTICAL);
        bottom.setOrientation(LinearLayout.HORIZONTAL);
        bottom.setPadding(dp(14), dp(7), dp(14), dp(8));
        bottom.setBackground(topStroke(WHITE, BORDER));
        shell.addView(bottom, new LinearLayout.LayoutParams(-1, dp(68)));
        String[] glyphs = {"⌂", "▤", "⚙"};
        String[] labels = {"工作台", "记录", "设置"};
        for (int i = 0; i < 3; i++) {
            final int destination = i;
            LinearLayout item = vertical();
            item.setGravity(android.view.Gravity.CENTER);
            item.setClickable(true);
            item.setFocusable(true);
            item.setBackground(touchBackground(Color.TRANSPARENT, dp(15)));
            TextView icon = text(glyphs[i], 21, MUTED, true);
            icon.setGravity(android.view.Gravity.CENTER);
            item.addView(icon);
            TextView label = text(labels[i], 11, MUTED, true);
            label.setGravity(android.view.Gravity.CENTER);
            item.addView(label, blockParams(dp(2)));
            bottom.addView(item, new LinearLayout.LayoutParams(0, -1, 1));
            navIcons[i] = icon;
            navLabels[i] = label;
            navItems[i] = item;
            item.setContentDescription(labels[i]);
            item.setOnClickListener(v -> {
                v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                selectTab(destination);
            });
        }
        selectTab(0);
        refresh();
        worker.execute(() -> {
            try {
                RootCollector.purgeStaleStaging(getApplicationContext());
            } catch (Exception e) {
                final String detail = safeMessage(e);
                runOnUiThread(() -> notifyMessage("历史临时文件清理未完成：" + detail));
            }
        });
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

    private void retryDispatch() {
        File file = selectedFile();
        if (file == null || store.dispatched() || store.lastAssetId() <= 0
                || !store.isUploaded(new SecretStore.FileInfo(file.getAbsolutePath(), file.length()))) {
            notifyMessage("没有可以安全重新发送的工作流通知");
            return;
        }
        final File selected = file;
        final String repo = store.repo();
        final long releaseId = store.lastReleaseId();
        final long assetId = store.lastAssetId();
        final String sha = store.uploadedSha256(
                new SecretStore.FileInfo(selected.getAbsolutePath(), selected.length()));
        runTask("正在核对远端附件并重新发送工作流通知…", () -> {
            String token = store.loadToken();
            GitHubUploader.retryDispatch(repo, token, selected, releaseId, assetId, sha);
            store.markDispatchSucceeded();
            return "工作流通知已再次发送；仍需等待 GitHub 接收工作流执行完成。";
        });
    }

    private String intakeLabel(String state) {
        switch (state) {
            case "ACCEPTED": return "新输入已接收（不是 ABI/KMI 或真机验证通过）";
            case "ALREADY_CURRENT": return "与固定输入一致，无须重复分析";
            case "REJECTED": return "后端拒收，请保留本地 ZIP 查看 Actions 报告";
            default: return "尚无处理结果，可稍后点查询";
        }
    }

    private void checkBackendIntake() {
        File file = selectedFile();
        if (file == null || !store.dispatched() || store.lastAssetId() <= 0) {
            notifyMessage("需先完成上传并发送工作流通知");
            return;
        }
        final String repo = store.repo();
        final long releaseId = store.lastReleaseId();
        final long assetId = store.lastAssetId();
        final String sha = store.uploadedSha256(
                new SecretStore.FileInfo(file.getAbsolutePath(), file.length()));
        runTask("正在查询 GitHub 的后端接收结果…", () -> {
            String token = store.loadToken();
            String outcome = GitHubUploader.checkIntake(repo, token, releaseId, assetId, sha);
            store.recordIntake(outcome);
            return "GitHub 接收状态：" + intakeLabel(outcome)
                    + "\n注意：接收成功不代表纯 GKI、ABI 或启动测试通过。";
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
                new SecretStore.FileInfo(file.getAbsolutePath(), file.length()))
                || !store.intakeAccepted()) {
            notifyMessage("必须先取得 GitHub 后端接收成功的回执，才能删除本地采集包");
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
                                "pandora-os4-capture-\\d{8}-\\d{6}(?:-\\d{3})?\\.zip")) {
                            throw new SecurityException("路径不在应用的 OTA 采集目录内");
                        }
                        if (!store.intakeAccepted() || !store.isUploaded(new SecretStore.FileInfo(
                                target.getAbsolutePath(), target.length()))) {
                            throw new SecurityException("无 GitHub 成功上传回执");
                        }
                        String expectedSha = store.uploadedSha256(
                                new SecretStore.FileInfo(target.getAbsolutePath(), target.length()));
                        if (expectedSha.isEmpty() ||
                                !expectedSha.equalsIgnoreCase(GitHubUploader.sha256(target))) {
                            throw new SecurityException("本地文件 SHA-256 与上传回执不符，拒绝删除");
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
        bootOption.setEnabled(false);
        rootButton.setEnabled(!busy);
        collectButton.setEnabled(!busy && RootCollector.isPandora());
        uploadButton.setEnabled(!busy && exists && !uploaded && store.hasToken());
        chooseArchiveButton.setEnabled(!busy && store.archives().length > 0);
        deleteButton.setEnabled(!busy && uploaded && store.intakeAccepted());
        checkIntakeButton.setVisibility(uploaded && store.dispatched() ? View.VISIBLE : View.GONE);
        checkIntakeButton.setEnabled(!busy && store.hasToken());
        retryNoticeButton.setVisibility(uploaded && !store.dispatched() && store.lastAssetId() > 0
                ? View.VISIBLE : View.GONE);
        retryNoticeButton.setEnabled(!busy && store.hasToken());
        openReleaseButton.setVisibility(uploaded
                && store.lastReleaseUrl().startsWith("https://github.com/")
                ? View.VISIBLE : View.GONE);
        if (!busy && uploaded) {
            uploadStage.setText(store.intakeAccepted() ? "GitHub 接收已确认" : "GitHub 附件已上传");
            uploadBar.setProgress(100);
            percent.setText("100%");
            uploadNumbers.setText(size(file.length()) + " / " + size(file.length()));
            uploadSpeed.setText("历史上传完成记录");
            receiptState.setText("GitHub 附件已确认 · Release #" + store.lastReleaseId()
                    + "\n工作流通知：" + (store.dispatched() ? "已发送请求" : "未成功")
                    + "\n接收结果：" + intakeLabel(store.intakeState()));
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
