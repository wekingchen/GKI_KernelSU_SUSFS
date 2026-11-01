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
    private static final int BACKGROUND = Color.rgb(247, 249, 253);
    private static final int INK = Color.rgb(24, 34, 53);
    private static final int MUTED = Color.rgb(112, 124, 145);
    private static final int TEAL = Color.rgb(35, 105, 230);
    private static final int LIGHT_TEAL = Color.rgb(233, 241, 255);
    private static final int FIELD = Color.rgb(243, 246, 252);
    private static final int BORDER = Color.rgb(230, 235, 244);
    private static final int NOTICE = Color.rgb(238, 244, 255);
    private static final int WARNING = Color.rgb(173, 86, 45);
    private static final int WHITE = Color.WHITE;

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SecretStore store;
    private EditText repoField, tokenField;
    private CheckBox bootOption;
    private Button saveButton, clearButton, rootButton, collectButton, uploadButton;
    private Button deleteButton, openReleaseButton, chooseArchiveButton, retryNoticeButton, checkIntakeButton;
    private TextView tokenState, repoState, fileState, uploadStage, uploadNumbers, uploadSpeed;
    private TextView percent, receiptState, message, rootStatus;
    private ProgressBar uploadBar, taskSpinner;
    private ScrollView workScroll, recordsScroll, settingsScroll;
    private LinearLayout archiveListing, statusBanner, appBar, recordCard, recordActionRow;
    private TextView deviceStatus, rootPill, intakeSummary, recordFileState;
    private TextView workUploadedMetric, workRepoMetric, workGitHubMetric;
    private TextView recordCountMetric, recordUploadedMetric, recordGitHubMetric;
    private final LinearLayout[] navItems = new LinearLayout[3];
    private final ImageView[] navIcons = new ImageView[3];
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
        GradientDrawable shellBackground = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Color.rgb(251, 253, 255), Color.rgb(244, 248, 255), Color.rgb(251, 253, 255)});
        shell.setBackground(shellBackground);
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
        appBar = new LinearLayout(this);
        appBar.setGravity(android.view.Gravity.CENTER_VERTICAL);
        appBar.setPadding(dp(18), dp(7), dp(18), dp(7));
        shell.addView(appBar, new LinearLayout.LayoutParams(-1, dp(58)));

        ImageView brand = new ImageView(this);
        brand.setImageResource(R.drawable.ic_pandora_ota);
        brand.setContentDescription("Pandora OTA");
        brand.setScaleType(ImageView.ScaleType.FIT_CENTER);
        appBar.addView(brand, new LinearLayout.LayoutParams(dp(34), dp(34)));

        LinearLayout brandCopy = vertical();
        LinearLayout.LayoutParams brandParams = new LinearLayout.LayoutParams(0, -2, 1);
        brandParams.leftMargin = dp(10);
        appBar.addView(brandCopy, brandParams);
        brandCopy.addView(text("Pandora OTA", 19, INK, true));
        brandCopy.addView(text("OS4 · Reliable · Secure", 9.5f, MUTED, false), blockParams(dp(1)));

        statusBanner = new LinearLayout(this);
        statusBanner.setGravity(android.view.Gravity.CENTER_VERTICAL);
        statusBanner.setBackground(round(NOTICE, dp(14)));
        statusBanner.setPadding(dp(13), dp(10), dp(13), dp(10));
        LinearLayout.LayoutParams noticeParams = new LinearLayout.LayoutParams(-1, -2);
        noticeParams.setMargins(dp(18), 0, dp(18), dp(6));
        shell.addView(statusBanner, noticeParams);
        taskSpinner = new ProgressBar(this, null, android.R.attr.progressBarStyleSmall);
        taskSpinner.setIndeterminateTintList(ColorStateList.valueOf(TEAL));
        statusBanner.addView(taskSpinner, new LinearLayout.LayoutParams(dp(18), dp(18)));
        message = text("", 12, INK, false);
        message.setMaxLines(3);
        message.setTextIsSelectable(true);
        LinearLayout.LayoutParams msgParams = new LinearLayout.LayoutParams(0, -2, 1);
        msgParams.leftMargin = dp(9);
        statusBanner.addView(message, msgParams);
        taskSpinner.setVisibility(View.GONE);
        statusBanner.setVisibility(View.GONE);

        FrameLayout destinations = new FrameLayout(this);
        shell.addView(destinations, new LinearLayout.LayoutParams(-1, 0, 1));
        workScroll = page(destinations);
        recordsScroll = page(destinations);
        settingsScroll = page(destinations);
        LinearLayout work = pageContents(workScroll);
        LinearLayout records = pageContents(recordsScroll);
        LinearLayout settings = pageContents(settingsScroll);

        // Workbench — premium hero + current capture, aligned to the commercial visual system.
        FrameLayout hero = new FrameLayout(this);
        GradientDrawable heroBackground = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Color.WHITE, Color.rgb(235, 243, 255), Color.rgb(224, 237, 255)});
        heroBackground.setCornerRadius(dp(30));
        hero.setBackground(heroBackground);
        hero.setElevation(dp(2));
        work.addView(hero, new LinearLayout.LayoutParams(-1, dp(196)));

        LinearLayout heroCopy = vertical();
        heroCopy.setPadding(dp(20), dp(20), dp(18), 0);
        FrameLayout.LayoutParams heroCopyParams = new FrameLayout.LayoutParams(-1, -2);
        heroCopyParams.rightMargin = dp(118);
        hero.addView(heroCopy, heroCopyParams);

        heroCopy.addView(text("Xiaomi 17 Pro", 24, INK, true));
        deviceStatus = text(RootCollector.isPandora()
                        ? "pandora · Android 16 · HyperOS 4"
                        : "pandora · 当前设备不受支持",
                12, RootCollector.isPandora() ? MUTED : WARNING, false);
        heroCopy.addView(deviceStatus, blockParams(dp(8)));

        LinearLayout rootRow = new LinearLayout(this);
        rootRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        heroCopy.addView(rootRow, blockParams(dp(14)));
        rootPill = text("Root 未检查", 11, MUTED, true);
        rootPill.setPadding(dp(11), dp(6), dp(11), dp(6));
        rootPill.setBackground(round(FIELD, dp(18)));
        rootRow.addView(rootPill);
        rootButton = button("检查", false);
        rootButton.setMinHeight(0);
        rootButton.setMinimumHeight(0);
        rootButton.setPadding(dp(12), 0, dp(12), 0);
        LinearLayout.LayoutParams rootActionParams = new LinearLayout.LayoutParams(-2, dp(34));
        rootActionParams.leftMargin = dp(8);
        rootRow.addView(rootButton, rootActionParams);

        rootStatus = text("尚未检测 Root；如不弹窗，请在 Root 管理器手动授权。",
                11, MUTED, false);
        rootStatus.setTextIsSelectable(true);
        rootStatus.setVisibility(View.GONE);
        heroCopy.addView(rootStatus, blockParams(dp(9)));

        ImageView deviceArt = new ImageView(this);
        deviceArt.setImageResource(R.drawable.device_pandora_render);
        deviceArt.setScaleType(ImageView.ScaleType.FIT_CENTER);
        FrameLayout.LayoutParams deviceArtParams = new FrameLayout.LayoutParams(dp(108), dp(154));
        deviceArtParams.gravity = android.view.Gravity.TOP | android.view.Gravity.END;
        deviceArtParams.topMargin = dp(10);
        deviceArtParams.rightMargin = dp(9);
        hero.addView(deviceArt, deviceArtParams);

        bootOption = new CheckBox(this);
        bootOption.setChecked(true);
        bootOption.setEnabled(false);
        bootOption.setVisibility(View.GONE);

        collectButton = button("开始采集   →", true);
        collectButton.setBackground(primaryGradientBackground());
        LinearLayout.LayoutParams captureParams = new LinearLayout.LayoutParams(-1, dp(58));
        captureParams.topMargin = dp(12);
        work.addView(collectButton, captureParams);

        rootButton.setOnClickListener(v -> {
            rootStatus.setVisibility(View.VISIBLE);
            rootStatus.setText("正在请求 Root 授权…");
            rootPill.setText("Root 检查中");
            runTask("正在请求 Root 授权…", () -> {
                try {
                    String identityResult = RootCollector.checkRoot();
                    runOnUiThread(() -> {
                        rootPill.setText("✓  Root 已授权");
                        rootPill.setTextColor(Color.rgb(31, 117, 93));
                        rootPill.setBackground(round(Color.rgb(229, 247, 240), dp(18)));
                        rootButton.setVisibility(View.GONE);
                        rootStatus.setVisibility(View.GONE);
                        rootStatus.setText("授权成功 · " + identityResult);
                    });
                    return "Root 已授权，可以开始采集";
                } catch (Exception e) {
                    String explanation = safeMessage(e);
                    runOnUiThread(() -> {
                        rootPill.setText("Root 未授权");
                        rootPill.setTextColor(WARNING);
                        rootStatus.setText("授权失败 · " + explanation);
                    });
                    throw e;
                }
            });
        });
        collectButton.setOnClickListener(v -> runTask("正在采集设备数据…", () -> {
            File output = RootCollector.capture(getApplicationContext(), true);
            store.saveArchive(output.getAbsolutePath());
            return "采集完成 · " + output.getName() + " · " + size(output.length());
        }));

        LinearLayout recentHeader = new LinearLayout(this);
        recentHeader.setGravity(android.view.Gravity.CENTER_VERTICAL);
        work.addView(recentHeader, blockParams(dp(24)));
        recentHeader.addView(text("最近采集", 19, INK, true),
                new LinearLayout.LayoutParams(0, -2, 1));
        TextView detailsHint = text("查看全部", 12, TEAL, true);
        detailsHint.setClickable(true);
        detailsHint.setFocusable(true);
        detailsHint.setPadding(dp(8), dp(5), dp(8), dp(5));
        detailsHint.setBackground(touchBackground(Color.TRANSPARENT, dp(12)));
        detailsHint.setOnClickListener(v -> selectTab(1));
        recentHeader.addView(detailsHint);

        LinearLayout recentCard = vertical();
        recentCard.setBackground(round(WHITE, dp(20)));
        recentCard.setPadding(dp(15), dp(14), dp(15), dp(15));
        recentCard.setElevation(dp(1));
        work.addView(recentCard, blockParams(dp(11)));

        LinearLayout fileRow = new LinearLayout(this);
        fileRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        recentCard.addView(fileRow);
        fileRow.addView(iconBox(R.drawable.ic_file_zip, dp(52), dp(18)));
        fileState = text("", 14, INK, true);
        fileState.setTextIsSelectable(true);
        LinearLayout.LayoutParams currentFileParams = new LinearLayout.LayoutParams(0, -2, 1);
        currentFileParams.leftMargin = dp(14);
        fileRow.addView(fileState, currentFileParams);

        uploadButton = button("上传到 GitHub", false);
        uploadButton.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_external_simple, 0, 0, 0);
        uploadButton.setCompoundDrawablePadding(dp(8));
        recentCard.addView(uploadButton, blockParams(dp(15)));
        uploadButton.setOnClickListener(v -> startUpload());

        LinearLayout progressHeader = new LinearLayout(this);
        progressHeader.setGravity(android.view.Gravity.CENTER_VERTICAL);
        recentCard.addView(progressHeader, blockParams(dp(14)));
        uploadStage = text("等待上传", 12, MUTED, true);
        progressHeader.addView(uploadStage, new LinearLayout.LayoutParams(0, -2, 1));
        percent = text("0%", 16, TEAL, true);
        progressHeader.addView(percent);
        uploadBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        uploadBar.setMax(100);
        uploadBar.setProgressTintList(ColorStateList.valueOf(TEAL));
        uploadBar.setProgressBackgroundTintList(ColorStateList.valueOf(LIGHT_TEAL));
        recentCard.addView(uploadBar, new LinearLayout.LayoutParams(-1, dp(5)));
        uploadNumbers = text("0 B / 0 B", 11, MUTED, false);
        recentCard.addView(uploadNumbers, blockParams(dp(8)));
        uploadSpeed = text("速率 --   ·   耗时 --", 11, MUTED, false);
        recentCard.addView(uploadSpeed, blockParams(dp(3)));
        intakeSummary = text("", 12, MUTED, false);
        recentCard.addView(intakeSummary, blockParams(dp(10)));
        checkIntakeButton = button("查询处理结果", false);
        recentCard.addView(checkIntakeButton, blockParams(dp(9)));
        checkIntakeButton.setOnClickListener(v -> checkBackendIntake());

        LinearLayout workMetrics = new LinearLayout(this);
        workMetrics.setOrientation(LinearLayout.HORIZONTAL);
        workMetrics.setBackground(round(WHITE, dp(20)));
        workMetrics.setPadding(dp(3), dp(4), dp(3), dp(4));
        workMetrics.setElevation(dp(1));
        work.addView(workMetrics, blockParams(dp(14)));
        LinearLayout uploadedMetric = metricTile("已上传", R.drawable.ic_external_simple);
        LinearLayout repoMetric = metricTile("仓库", R.drawable.ic_repo);
        LinearLayout githubMetric = metricTile("GitHub", R.drawable.ic_key_simple);
        uploadedMetric.setBackgroundColor(Color.TRANSPARENT);
        uploadedMetric.setElevation(0);
        repoMetric.setBackgroundColor(Color.TRANSPARENT);
        repoMetric.setElevation(0);
        githubMetric.setBackgroundColor(Color.TRANSPARENT);
        githubMetric.setElevation(0);
        workUploadedMetric = metricValue(uploadedMetric);
        workRepoMetric = metricValue(repoMetric);
        workGitHubMetric = metricValue(githubMetric);
        LinearLayout.LayoutParams metricLp = new LinearLayout.LayoutParams(0, dp(82), 1);
        LinearLayout.LayoutParams metricMidLp = new LinearLayout.LayoutParams(0, dp(92), 1);
        metricMidLp.leftMargin = dp(8);
        LinearLayout.LayoutParams metricLastLp = new LinearLayout.LayoutParams(0, dp(92), 1);
        metricLastLp.leftMargin = dp(8);
        workMetrics.addView(uploadedMetric, metricLp);
        workMetrics.addView(repoMetric, metricMidLp);
        workMetrics.addView(githubMetric, metricLastLp);

        // Records — status-led, concise and action-oriented.
        records.addView(pageHeading("记录", "采集文件与 GitHub 记录"));

        LinearLayout recordOverview = new LinearLayout(this);
        recordOverview.setOrientation(LinearLayout.HORIZONTAL);
        records.addView(recordOverview, blockParams(dp(18)));
        LinearLayout collectedTile = metricTile("采集文件", R.drawable.ic_file_zip);
        LinearLayout uploadedTile = metricTile("已上传", R.drawable.ic_external_simple);
        LinearLayout githubTile = metricTile("GitHub", R.drawable.ic_repo);
        recordCountMetric = metricValue(collectedTile);
        recordUploadedMetric = metricValue(uploadedTile);
        recordGitHubMetric = metricValue(githubTile);
        LinearLayout.LayoutParams overviewLp = new LinearLayout.LayoutParams(0, dp(88), 1);
        LinearLayout.LayoutParams overviewMidLp = new LinearLayout.LayoutParams(0, dp(88), 1);
        overviewMidLp.leftMargin = dp(8);
        LinearLayout.LayoutParams overviewLastLp = new LinearLayout.LayoutParams(0, dp(88), 1);
        overviewLastLp.leftMargin = dp(8);
        recordOverview.addView(collectedTile, overviewLp);
        recordOverview.addView(uploadedTile, overviewMidLp);
        recordOverview.addView(githubTile, overviewLastLp);

        recordCard = vertical();
        recordCard.setBackground(round(WHITE, dp(28)));
        recordCard.setPadding(dp(20), dp(20), dp(20), dp(21));
        recordCard.setElevation(dp(1));
        records.addView(recordCard, blockParams(dp(18)));

        LinearLayout activeFileRow = new LinearLayout(this);
        activeFileRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        recordCard.addView(activeFileRow);
        activeFileRow.addView(iconBox(R.drawable.ic_file_zip, dp(58), dp(18)));
        recordFileState = text("", 15, INK, true);
        recordFileState.setTextIsSelectable(true);
        LinearLayout.LayoutParams recordTextParams = new LinearLayout.LayoutParams(0, -2, 1);
        recordTextParams.leftMargin = dp(14);
        activeFileRow.addView(recordFileState, recordTextParams);

        chooseArchiveButton = button("切换", false);
        chooseArchiveButton.setMinHeight(0);
        chooseArchiveButton.setMinimumHeight(0);
        activeFileRow.addView(chooseArchiveButton, new LinearLayout.LayoutParams(-2, dp(42)));
        chooseArchiveButton.setOnClickListener(v -> chooseArchive());

        View recordDivider = new View(this);
        recordDivider.setBackgroundColor(BORDER);
        LinearLayout.LayoutParams dividerParams = new LinearLayout.LayoutParams(-1, dp(1));
        dividerParams.topMargin = dp(18);
        recordCard.addView(recordDivider, dividerParams);

        LinearLayout receiptRow = new LinearLayout(this);
        receiptRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        recordCard.addView(receiptRow, blockParams(dp(16)));
        ImageView receiptIcon = iconBox(R.drawable.ic_repo, dp(44), dp(15));
        receiptRow.addView(receiptIcon);
        LinearLayout receiptTexts = vertical();
        LinearLayout.LayoutParams receiptTextParams = new LinearLayout.LayoutParams(0, -2, 1);
        receiptTextParams.leftMargin = dp(12);
        receiptRow.addView(receiptTexts, receiptTextParams);
        receiptTexts.addView(text("GitHub 状态", 13, INK, true));
        receiptState = text("", 12, MUTED, false);
        receiptState.setTextIsSelectable(true);
        receiptTexts.addView(receiptState, blockParams(dp(4)));

        recordActionRow = new LinearLayout(this);
        recordActionRow.setOrientation(LinearLayout.HORIZONTAL);
        recordCard.addView(recordActionRow, blockParams(dp(18)));

        openReleaseButton = actionTile("查看草稿", R.drawable.ic_external_simple);
        retryNoticeButton = actionTile("重新通知", R.drawable.ic_refresh_simple);
        deleteButton = actionTile("核验后清理", R.drawable.ic_delete_simple);
        LinearLayout.LayoutParams tile = new LinearLayout.LayoutParams(0, dp(86), 1);
        LinearLayout.LayoutParams tileMiddle = new LinearLayout.LayoutParams(0, dp(86), 1);
        tileMiddle.leftMargin = dp(8);
        LinearLayout.LayoutParams tileLast = new LinearLayout.LayoutParams(0, dp(86), 1);
        tileLast.leftMargin = dp(8);
        recordActionRow.addView(openReleaseButton, tile);
        recordActionRow.addView(retryNoticeButton, tileMiddle);
        recordActionRow.addView(deleteButton, tileLast);
        openReleaseButton.setOnClickListener(v -> openRelease());
        retryNoticeButton.setOnClickListener(v -> retryDispatch());
        deleteButton.setOnClickListener(v -> confirmDelete());

        LinearLayout localHeader = new LinearLayout(this);
        localHeader.setGravity(android.view.Gravity.CENTER_VERTICAL);
        records.addView(localHeader, blockParams(dp(28)));
        localHeader.addView(text("本地记录", 22, INK, true),
                new LinearLayout.LayoutParams(0, -2, 1));
        TextView localCount = text("最近 12 条", 11, MUTED, false);
        localHeader.addView(localCount);
        archiveListing = vertical();
        records.addView(archiveListing, blockParams(dp(7)));

        // Settings — list-style, matching the selected commercial concept.
        settings.addView(pageHeading("设置", "关键配置简洁直观"));

        LinearLayout connectionCard = vertical();
        connectionCard.setBackground(round(WHITE, dp(24)));
        connectionCard.setPadding(dp(8), dp(7), dp(8), dp(7));
        connectionCard.setElevation(dp(1));
        settings.addView(connectionCard, blockParams(dp(18)));

        LinearLayout repoRow = settingRow(R.drawable.ic_repo, "GitHub 仓库");
        repoState = (TextView) repoRow.getChildAt(1);
        connectionCard.addView(repoRow);
        repoRow.setOnClickListener(v -> showRepoEditor());

        View settingsDivider = new View(this);
        settingsDivider.setBackgroundColor(BORDER);
        LinearLayout.LayoutParams settingsDividerParams = new LinearLayout.LayoutParams(-1, dp(1));
        settingsDividerParams.leftMargin = dp(66);
        settingsDividerParams.rightMargin = dp(12);
        connectionCard.addView(settingsDivider, settingsDividerParams);

        LinearLayout tokenRow = settingRow(R.drawable.ic_key_simple, "访问令牌");
        tokenState = (TextView) tokenRow.getChildAt(1);
        connectionCard.addView(tokenRow);
        tokenRow.setOnClickListener(v -> showTokenEditor());

        TextView strategyTitle = text("采集与上传", 18, INK, true);
        settings.addView(strategyTitle, blockParams(dp(24)));

        LinearLayout strategyCard = vertical();
        strategyCard.setBackground(round(WHITE, dp(22)));
        strategyCard.setPadding(dp(8), dp(6), dp(8), dp(6));
        strategyCard.setElevation(dp(1));
        settings.addView(strategyCard, blockParams(dp(9)));

        LinearLayout capturePolicyRow = settingRow(R.drawable.ic_file_zip, "采集设置");
        TextView capturePolicySub = (TextView) capturePolicyRow.getChildAt(1);
        renderSettingRow(capturePolicySub, "采集设置", "活动 slot · 只读完整采集");
        strategyCard.addView(capturePolicyRow);
        capturePolicyRow.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("采集设置")
                .setMessage("固定采集 boot / init_boot / vendor_boot / dtbo 与 OEM 模块。只读取当前活动 slot，不修改系统分区。")
                .setPositiveButton("知道了", null)
                .show());

        View strategyDivider = new View(this);
        strategyDivider.setBackgroundColor(BORDER);
        LinearLayout.LayoutParams strategyDividerParams = new LinearLayout.LayoutParams(-1, dp(1));
        strategyDividerParams.leftMargin = dp(66);
        strategyDividerParams.rightMargin = dp(12);
        strategyCard.addView(strategyDivider, strategyDividerParams);

        LinearLayout uploadPolicyRow = settingRow(R.drawable.ic_external_simple, "上传设置");
        TextView uploadPolicySub = (TextView) uploadPolicyRow.getChildAt(1);
        renderSettingRow(uploadPolicySub, "上传设置", "GitHub Draft · 前台上传 · 后端审计");
        strategyCard.addView(uploadPolicyRow);
        uploadPolicyRow.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("上传设置")
                .setMessage("采集包上传到 GitHub Draft Release；上传任务保持前台运行，随后由接收工作流执行身份与安全审计。")
                .setPositiveButton("知道了", null)
                .show());

        TextView aboutTitle = text("关于", 18, INK, true);
        settings.addView(aboutTitle, blockParams(dp(28)));

        LinearLayout aboutCard = vertical();
        aboutCard.setBackground(round(WHITE, dp(24)));
        aboutCard.setPadding(dp(8), dp(7), dp(8), dp(7));
        aboutCard.setElevation(dp(1));
        settings.addView(aboutCard, blockParams(dp(10)));

        LinearLayout securityRow = settingRow(R.drawable.ic_key_simple, "安全与隐私");
        TextView securitySub = (TextView) securityRow.getChildAt(1);
        renderSettingRow(securitySub, "安全与隐私", "Keystore 加密 · 只读采集");
        aboutCard.addView(securityRow);
        securityRow.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("安全与隐私")
                .setMessage("访问令牌由 Android Keystore 加密保存。采集只读，不刷机、不修改活动分区，也不会自动晋升 LKG。")
                .setPositiveButton("知道了", null)
                .show());

        View aboutDivider = new View(this);
        aboutDivider.setBackgroundColor(BORDER);
        LinearLayout.LayoutParams aboutDividerParams = new LinearLayout.LayoutParams(-1, dp(1));
        aboutDividerParams.leftMargin = dp(66);
        aboutDividerParams.rightMargin = dp(12);
        aboutCard.addView(aboutDivider, aboutDividerParams);

        LinearLayout aboutRow = settingRow(R.drawable.ic_pandora_ota, "关于 Pandora OTA");
        TextView aboutSub = (TextView) aboutRow.getChildAt(1);
        renderSettingRow(aboutSub, "关于 Pandora OTA",
                "版本 " + getAppVersion() + " · Xiaomi 17 Pro");
        aboutCard.addView(aboutRow);
        aboutRow.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("Pandora OTA")
                .setMessage("版本 " + getAppVersion()
                        + "\n\n仅适用于 Xiaomi 17 Pro · pandora。原始 init_boot.img 请从同版本 OTA 离线保存；应用内采集的是 Root 后快照。")
                .setPositiveButton("关闭", null)
                .show());

        // Keep hidden native fields for credential state/tests; editing is done through dialogs.
        repoField = field("owner/repo", store.repo(), false);
        repoField.setVisibility(View.GONE);
        settings.addView(repoField, new LinearLayout.LayoutParams(1, 1));
        tokenField = field("", "", true);
        tokenField.setVisibility(View.GONE);
        settings.addView(tokenField, new LinearLayout.LayoutParams(1, 1));
        saveButton = button("保存", true);
        saveButton.setVisibility(View.GONE);
        settings.addView(saveButton, new LinearLayout.LayoutParams(1, 1));
        clearButton = button("清除", false);
        clearButton.setVisibility(View.GONE);
        settings.addView(clearButton, new LinearLayout.LayoutParams(1, 1));

        // Material-like native bottom destination bar, always visible.
        LinearLayout bottom = new LinearLayout(this);
        bottom.setGravity(android.view.Gravity.CENTER_VERTICAL);
        bottom.setOrientation(LinearLayout.HORIZONTAL);
        bottom.setPadding(dp(18), dp(4), dp(18), dp(5));
        bottom.setBackgroundColor(Color.rgb(252, 253, 255));
        shell.addView(bottom, new LinearLayout.LayoutParams(-1, dp(60)));
        int[] glyphs = {R.drawable.ic_nav_workbench, R.drawable.ic_nav_records, R.drawable.ic_nav_settings};
        String[] labels = {"工作台", "记录", "设置"};
        for (int i = 0; i < 3; i++) {
            final int destination = i;
            LinearLayout item = vertical();
            item.setGravity(android.view.Gravity.CENTER);
            item.setClickable(true);
            item.setFocusable(true);
            item.setBackground(touchBackground(Color.TRANSPARENT, dp(15)));
            ImageView icon = new ImageView(this);
            icon.setImageResource(glyphs[i]);
            icon.setImageTintList(ColorStateList.valueOf(MUTED));
            icon.setScaleType(ImageView.ScaleType.FIT_CENTER);
            icon.setPadding(dp(5), dp(5), dp(5), dp(5));
            item.addView(icon, new LinearLayout.LayoutParams(dp(31), dp(31)));
            TextView label = text(labels[i], 10, MUTED, true);
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

    private LinearLayout settingRow(int drawable, String title) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        row.setPadding(dp(10), dp(13), dp(10), dp(13));
        row.setClickable(true);
        row.setFocusable(true);
        row.setBackground(touchBackground(Color.TRANSPARENT, dp(18)));

        ImageView icon = iconBox(drawable, dp(48), dp(15));
        row.addView(icon);

        TextView copy = text("", 12, MUTED, false);
        copy.setTag(title);
        LinearLayout.LayoutParams copyParams = new LinearLayout.LayoutParams(0, -2, 1);
        copyParams.leftMargin = dp(12);
        row.addView(copy, copyParams);

        TextView chevron = text("›", 27, MUTED, false);
        row.addView(chevron);
        return row;
    }

    private void renderSettingRow(TextView view, String title, String subtitle) {
        view.setText(title + "\n" + subtitle);
        view.setTextColor(INK);
        view.setTextSize(14);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setLineSpacing(0, 1.08f);
    }

    private void showRepoEditor() {
        EditText input = field("owner/repo", store.repo(), false);
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
                .setTitle("GitHub 仓库")
                .setView(input)
                .setNegativeButton("取消", null)
                .setPositiveButton("保存", (dialog, which) -> {
                    try {
                        String repo = input.getText().toString().trim();
                        if (!repo.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"))
                            throw new IllegalArgumentException("仓库格式应为 owner/repo");
                        store.saveRepo(repo);
                        repoField.setText(repo);
                        refresh();
                        notifyMessage("GitHub 仓库已更新");
                    } catch (Exception e) {
                        notifyMessage("保存失败：" + safeMessage(e));
                    }
                }).show();
    }

    private void showTokenEditor() {
        EditText input = field("粘贴新的 Fine-grained PAT", "", true);
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("访问令牌")
                .setView(input)
                .setNegativeButton("取消", null)
                .setNeutralButton("清除本机令牌", null)
                .setPositiveButton("保存", null)
                .create();
        dialog.setOnShowListener(ignored -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                try {
                    String token = input.getText().toString().trim();
                    if (token.isEmpty()) throw new IllegalArgumentException("请输入访问令牌");
                    store.saveToken(token);
                    input.setText("");
                    refresh();
                    notifyMessage("访问令牌已安全保存");
                    dialog.dismiss();
                } catch (Exception e) {
                    notifyMessage("保存失败：" + safeMessage(e));
                }
            });
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> {
                store.clearToken();
                refresh();
                notifyMessage("本机 GitHub 令牌已删除");
                dialog.dismiss();
            });
        });
        dialog.show();
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
                        runOnUiThread(() -> {
                            uploadStage.setText(stage);
                            notifyMessage("GitHub 上传 · " + stage);
                        });
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
                    notifyMessage("GitHub 已保存附件。请查询接收结果后，再决定是否清理本地 ZIP。");
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
            case "REJECTED": return "OTA 身份门禁未通过，远端采集附件已保留";
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
                || !store.hasToken() || store.lastAssetId() <= 0) {
            notifyMessage("未取得 GitHub 附件上传回执，请先确认上传成功");
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("确认删除本地文件？")
                .setMessage(file.getName() + "\n\n即使 OTA 审计拒收，也可以清理本地副本。操作前将在线核验 GitHub 附件 ID、大小和 SHA-256。\n\n仅删除手机上的 ZIP，远端采集附件保持不变。"
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
                        if (!store.isUploaded(new SecretStore.FileInfo(
                                target.getAbsolutePath(), target.length()))) {
                            throw new SecurityException("无 GitHub 成功上传回执");
                        }
                        String expectedSha = store.uploadedSha256(
                                new SecretStore.FileInfo(target.getAbsolutePath(), target.length()));
                        if (expectedSha.isEmpty() ||
                                !expectedSha.equalsIgnoreCase(GitHubUploader.sha256(target))) {
                            throw new SecurityException("本地文件 SHA-256 与上传回执不符，拒绝删除");
                        }
                        GitHubUploader.verifyRemoteArchive(store.repo(), store.loadToken(),
                                store.lastReleaseId(), store.lastAssetId(), target, expectedSha);
                        if (!expectedSha.equalsIgnoreCase(GitHubUploader.sha256(target))) {
                            throw new SecurityException("核验期间本地文件发生变化，禁止删除");
                        }
                        if (!target.delete()) throw new IllegalStateException("无法删除文件");
                        store.forgetArchive();
                        return "已手动删除本地 ZIP；GitHub 附件已保留";
                    })).show();
    }

    private void openRelease() {
        File file = selectedFile();
        if (file == null || !file.isFile()
                || !store.isUploaded(new SecretStore.FileInfo(
                        file.getAbsolutePath(), file.length()))
                || !store.hasToken() || store.lastReleaseId() <= 0
                || store.lastAssetId() <= 0) {
            notifyMessage("尚无可核验的 GitHub 草稿采集附件");
            return;
        }
        final String repo = store.repo();
        final String path = file.getAbsolutePath();
        final long releaseId = store.lastReleaseId();
        final long assetId = store.lastAssetId();
        final String sha = store.uploadedSha256(
                new SecretStore.FileInfo(path, file.length()));
        runTask("正在核验 GitHub 草稿附件并打开管理页面…", () -> {
            String target = GitHubUploader.verifiedDraftEditorUrl(
                    repo, store.loadToken(), releaseId, assetId, file, sha);
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(target)));
                } catch (Exception e) {
                    notifyMessage("无法打开浏览器：" + safeMessage(e));
                }
            });
            return "已请求打开 GitHub 草稿管理页。请使用有仓库写权限的账号登录；"
                    + "切勿发布此未经原厂身份验证的采集包。";
        });
    }

    private void refresh() {
        boolean credentials = store.hasToken();
        tokenState.setText(credentials ? "✓ 已配置 · 安全存储" : "未配置");
        if (repoState != null) renderSettingRow(repoState, "GitHub 仓库",
                store.repo().isEmpty() ? "未配置" : store.repo());
        if (tokenState != null) renderSettingRow(tokenState, "访问令牌",
                credentials ? "✓ 已配置 · Android Keystore" : "未配置");
        File file = selectedFile();
        boolean exists = file != null;
        boolean uploaded = exists && store.isUploaded(
                new SecretStore.FileInfo(file.getAbsolutePath(), file.length()));
        String state = uploaded ? store.intakeState() : "PENDING";
        File[] allArchives = store.archives();
        int uploadedCount = 0;
        for (File archive : allArchives) {
            if (store.isUploaded(new SecretStore.FileInfo(
                    archive.getAbsolutePath(), archive.length()))) uploadedCount++;
        }
        if (workUploadedMetric != null) workUploadedMetric.setText(uploadedCount > 0
                ? String.valueOf(uploadedCount) : "—");
        if (workRepoMetric != null) workRepoMetric.setText(store.repo().isEmpty() ? "未配置" : "已配置");
        if (workGitHubMetric != null) workGitHubMetric.setText(credentials ? "已连接" : "未连接");
        if (recordCountMetric != null) recordCountMetric.setText(String.valueOf(allArchives.length));
        if (recordUploadedMetric != null) recordUploadedMetric.setText(String.valueOf(uploadedCount));
        if (recordGitHubMetric != null) recordGitHubMetric.setText(credentials ? "已连接" : "未连接");
        fileState.setText(exists
                ? file.getName() + "\n" + size(file.length())
                    + " · " + (uploaded ? "已上传" : "待上传")
                : "暂无采集记录");
        recordFileState.setText(exists
                ? file.getName() + "\n" + size(file.length())
                    + " · " + (uploaded ? "已上传" : "仅本地")
                : "尚无采集记录");
        if (recordCard != null) recordCard.setVisibility(exists ? View.VISIBLE : View.GONE);
        saveButton.setEnabled(!busy);
        clearButton.setEnabled(!busy && credentials);
        repoField.setEnabled(!busy);
        tokenField.setEnabled(!busy);
        bootOption.setEnabled(false);
        rootButton.setEnabled(!busy);
        collectButton.setEnabled(!busy && RootCollector.isPandora());
        uploadButton.setEnabled(!busy && exists && !uploaded && credentials);
        uploadButton.setText("上传到 GitHub");
        uploadButton.setVisibility(exists && !uploaded ? View.VISIBLE : View.GONE);
        boolean showProgress = exists && (busy || uploaded);
        uploadStage.setVisibility(showProgress ? View.VISIBLE : View.GONE);
        percent.setVisibility(showProgress ? View.VISIBLE : View.GONE);
        uploadBar.setVisibility(showProgress ? View.VISIBLE : View.GONE);
        uploadNumbers.setVisibility(busy ? View.VISIBLE : View.GONE);
        uploadSpeed.setVisibility(busy ? View.VISIBLE : View.GONE);
        intakeSummary.setVisibility(uploaded ? View.VISIBLE : View.GONE);
        chooseArchiveButton.setEnabled(!busy && store.archives().length > 0);
        deleteButton.setEnabled(!busy && uploaded && store.hasToken() && store.lastAssetId() > 0);
        checkIntakeButton.setVisibility(uploaded && store.dispatched()
                ? View.VISIBLE : View.GONE);
        checkIntakeButton.setEnabled(!busy && credentials);
        retryNoticeButton.setVisibility(uploaded && !store.dispatched()
                && store.lastAssetId() > 0 ? View.VISIBLE : View.GONE);
        retryNoticeButton.setEnabled(!busy && credentials);
        openReleaseButton.setVisibility(uploaded
                && store.lastReleaseId() > 0 && store.lastAssetId() > 0
                ? View.VISIBLE : View.GONE);
        openReleaseButton.setEnabled(!busy && credentials);
        taskSpinner.setVisibility(busy ? View.VISIBLE : View.GONE);
        if (!busy && uploaded) {
            uploadStage.setText(store.intakeAccepted() ? "已接收 · 校验完成"
                    : "REJECTED".equals(state) ? "已上传 · 后端安全拒收"
                    : "已上传 · 等待后端审计");
            uploadBar.setProgress(100);
            percent.setText("100%");
            uploadNumbers.setText(size(file.length()) + " / " + size(file.length()));
            uploadSpeed.setText("GitHub 附件已保存");
            intakeSummary.setText("后端状态  ·  " + intakeLabel(state));
            intakeSummary.setTextColor("REJECTED".equals(state) ? WARNING : TEAL);
            receiptState.setText("Release #" + store.lastReleaseId()
                    + " · 附件 #" + store.lastAssetId()
                    + "\nSHA-256：" + store.uploadedSha256(
                        new SecretStore.FileInfo(file.getAbsolutePath(), file.length()))
                    + "\n工作流通知：" + (store.dispatched() ? "已发送" : "未成功")
                    + "\n接收结果：" + intakeLabel(state));
        } else if (!busy) {
            uploadStage.setText(exists ? "等待上传" : "尚无采集文件");
            uploadBar.setProgress(0);
            percent.setText("0%");
            uploadNumbers.setText(exists ? "0 B / " + size(file.length()) : "0 B / 0 B");
            uploadSpeed.setText("速率 --   ·   耗时 --");
            receiptState.setText("尚无 GitHub 附件上传回执");
            intakeSummary.setText("尚未收到后端审计结果");
            intakeSummary.setTextColor(MUTED);
        }
        refreshArchiveListing(file);
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
        if (statusBanner != null) statusBanner.setVisibility(View.VISIBLE);
        message.setText(value);
        boolean error = value.contains("失败") || value.contains("拒收")
                || value.contains("无法") || value.contains("错误");
        message.setTextColor(error ? WARNING : INK);
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

    private ScrollView page(FrameLayout host) {
        ScrollView scroll = new ScrollView(this);
        scroll.setClipToPadding(false);
        scroll.setFillViewport(true);
        scroll.setVerticalScrollBarEnabled(false);
        host.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        return scroll;
    }

    private LinearLayout pageContents(ScrollView scroll) {
        LinearLayout contents = vertical();
        contents.setPadding(dp(18), dp(8), dp(18), dp(30));
        scroll.addView(contents);
        return contents;
    }

    private LinearLayout surfaceCard(LinearLayout parent, int top, int inset) {
        LinearLayout card = vertical();
        GradientDrawable bg = round(WHITE, dp(24));
        card.setBackground(bg);
        card.setElevation(dp(1));
        card.setPadding(inset, dp(21), inset, dp(23));
        parent.addView(card, blockParams(top));
        return card;
    }

    private LinearLayout sectionHeading(String number, String heading, String detail) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(android.view.Gravity.CENTER_VERTICAL);
        View accent = new View(this);
        accent.setBackground(round(TEAL, dp(3)));
        row.addView(accent, new LinearLayout.LayoutParams(dp(5), dp(34)));
        LinearLayout labels = vertical();
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -2, 1);
        lp.leftMargin = dp(13);
        row.addView(labels, lp);
        labels.addView(text(heading, 18, INK, true));
        labels.addView(text(detail, 11, MUTED, false), blockParams(dp(4)));
        return row;
    }

    private LinearLayout pageHeading(String heading, String subheading) {
        LinearLayout block = vertical();
        block.addView(text(heading, 26, INK, true));
        block.addView(text(subheading, 12, MUTED, false), blockParams(dp(5)));
        return block;
    }

    private GradientDrawable topStroke(int color, int border) {
        GradientDrawable bg = round(color, 0);
        bg.setStroke(dp(1), border);
        return bg;
    }

    private RippleDrawable touchBackground(int base, int radius) {
        return new RippleDrawable(ColorStateList.valueOf(Color.argb(30, 35, 105, 230)),
                round(base, radius), round(WHITE, radius));
    }

    private void selectTab(int index) {
        if (index < 0 || index > 2) return;
        activeTab = index;
        if (workScroll == null || recordsScroll == null || settingsScroll == null) return;
        workScroll.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        recordsScroll.setVisibility(index == 1 ? View.VISIBLE : View.GONE);
        settingsScroll.setVisibility(index == 2 ? View.VISIBLE : View.GONE);
        if (appBar != null) appBar.setVisibility(index == 0 ? View.VISIBLE : View.GONE);
        for (int i = 0; i < navItems.length; i++) {
            boolean active = i == index;
            navIcons[i].setImageTintList(ColorStateList.valueOf(active ? TEAL : MUTED));
            navLabels[i].setTextColor(active ? TEAL : MUTED);
            navItems[i].setBackground(touchBackground(Color.TRANSPARENT, dp(18)));
            navIcons[i].setBackground(round(active ? LIGHT_TEAL : Color.TRANSPARENT, dp(18)));
            navItems[i].setSelected(active);
        }
    }

    private void refreshArchiveListing(File selected) {
        if (archiveListing == null) return;
        archiveListing.removeAllViews();
        File[] archives = store.archives();
        if (archives.length == 0) {
            LinearLayout empty = new LinearLayout(this);
            empty.setGravity(android.view.Gravity.CENTER_VERTICAL);
            empty.setPadding(dp(14), dp(14), dp(14), dp(14));
            empty.setBackground(round(WHITE, dp(18)));
            empty.setElevation(dp(1));
            empty.addView(iconBox(R.drawable.ic_file_zip, dp(42), dp(13)));
            LinearLayout emptyCopy = vertical();
            LinearLayout.LayoutParams emptyCopyParams = new LinearLayout.LayoutParams(0, -2, 1);
            emptyCopyParams.leftMargin = dp(12);
            empty.addView(emptyCopy, emptyCopyParams);
            emptyCopy.addView(text("尚无采集记录", 13, INK, true));
            emptyCopy.addView(text("完成一次采集后会显示在这里", 11, MUTED, false), blockParams(dp(3)));
            archiveListing.addView(empty);
            return;
        }
        for (int i = 0; i < Math.min(archives.length, 12); i++) {
            File entry = archives[i];
            boolean active = selected != null
                    && entry.getAbsolutePath().equals(selected.getAbsolutePath());
            LinearLayout item = new LinearLayout(this);
            item.setGravity(android.view.Gravity.CENTER_VERTICAL);
            item.setPadding(dp(14), dp(13), dp(14), dp(13));
            item.setClickable(true);
            item.setFocusable(true);
            item.setBackground(touchBackground(active ? LIGHT_TEAL : WHITE, dp(20)));
            item.setElevation(dp(1));
            item.addView(iconBox(R.drawable.ic_file_zip, dp(46), dp(14)));
            TextView itemText = text(entry.getName()
                    + "\n" + size(entry.length())
                    + " · " + (store.isUploaded(
                    new SecretStore.FileInfo(entry.getAbsolutePath(), entry.length()))
                    ? "已上传" : "仅本地"), 12, active ? TEAL : INK, active);
            LinearLayout.LayoutParams itemTextParams = new LinearLayout.LayoutParams(0, -2, 1);
            itemTextParams.leftMargin = dp(12);
            item.addView(itemText, itemTextParams);
            TextView chevron = text("›", 26, MUTED, false);
            item.addView(chevron);
            archiveListing.addView(item, blockParams(dp(9)));
            item.setOnClickListener(v -> {
                if (busy) return;
                v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                store.saveArchive(entry.getAbsolutePath());
                refresh();
                notifyMessage("已切换到：" + entry.getName());
            });
        }
        if (archives.length > 12) {
            archiveListing.addView(text("其余 " + (archives.length - 12)
                    + " 个文件可通过「切换本地采集包」选择。", 11, MUTED, false),
                    blockParams(dp(8)));
        }
    }

    private ImageView iconBox(int drawable, int size, int padding) {
        ImageView icon = new ImageView(this);
        icon.setImageResource(drawable);
        icon.setImageTintList(ColorStateList.valueOf(TEAL));
        icon.setScaleType(ImageView.ScaleType.FIT_CENTER);
        icon.setPadding(padding, padding, padding, padding);
        icon.setBackground(round(LIGHT_TEAL, dp(17)));
        icon.setLayoutParams(new LinearLayout.LayoutParams(size, size));
        return icon;
    }

    private LinearLayout metricTile(String label, int drawable) {
        LinearLayout tile = vertical();
        tile.setGravity(android.view.Gravity.CENTER);
        tile.setBackground(round(WHITE, dp(18)));
        tile.setElevation(dp(1));
        ImageView icon = new ImageView(this);
        icon.setImageResource(drawable);
        icon.setImageTintList(ColorStateList.valueOf(TEAL));
        icon.setScaleType(ImageView.ScaleType.FIT_CENTER);
        tile.addView(icon, new LinearLayout.LayoutParams(dp(23), dp(23)));
        TextView caption = text(label, 11, MUTED, false);
        caption.setGravity(android.view.Gravity.CENTER);
        tile.addView(caption, blockParams(dp(5)));
        TextView value = text("—", 12, INK, true);
        value.setGravity(android.view.Gravity.CENTER);
        value.setTag("metric-value");
        tile.addView(value, blockParams(dp(3)));
        return tile;
    }

    private TextView metricValue(LinearLayout tile) {
        for (int i = 0; i < tile.getChildCount(); i++) {
            View child = tile.getChildAt(i);
            if (child instanceof TextView && "metric-value".equals(child.getTag())) {
                return (TextView) child;
            }
        }
        throw new IllegalStateException("metric value missing");
    }

    private Button actionTile(String caption, int drawable) {
        Button control = button(caption, false);
        control.setTextSize(11);
        control.setCompoundDrawablesWithIntrinsicBounds(0, drawable, 0, 0);
        control.setCompoundDrawablePadding(dp(7));
        control.setPadding(dp(5), dp(9), dp(5), dp(8));
        control.setGravity(android.view.Gravity.CENTER);
        return control;
    }

    private String getAppVersion() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "未知版本";
        }
    }

    @Override
    public void onBackPressed() {
        if (activeTab != 0) {
            selectTab(0);
        } else {
            super.onBackPressed();
        }
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
        b.setLetterSpacing(0.015f);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setTextColor(primary ? WHITE : TEAL);
        b.setBackground(touchBackground(primary ? TEAL : LIGHT_TEAL, dp(18)));
        b.setMinHeight(dp(primary ? 56 : 50));
        b.setMinimumHeight(dp(primary ? 56 : 50));
        b.setPadding(dp(14), 0, dp(14), 0);
        b.setStateListAnimator(null);
        b.setOnTouchListener((view, event) -> {
            if (!view.isEnabled()) return false;
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    view.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                    view.animate().scaleX(.975f).scaleY(.975f).setDuration(90).start();
                    break;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    view.animate().scaleX(1f).scaleY(1f).setDuration(130).start();
                    break;
            }
            return false;
        });
        return b;
    }

    private RippleDrawable primaryGradientBackground() {
        GradientDrawable gradient = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[]{Color.rgb(58, 129, 255), Color.rgb(35, 105, 230)});
        gradient.setCornerRadius(dp(18));
        return new RippleDrawable(
                ColorStateList.valueOf(Color.argb(34, 255, 255, 255)),
                gradient, round(WHITE, dp(18)));
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
