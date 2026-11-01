package com.wekingchen.pandoraota;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.text.InputType;
import android.graphics.Typeface;
import android.view.View;
import android.widget.*;
import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Minimal Chinese UI; long-running operations execute off the main thread. */
public final class MainActivity extends Activity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private SecretStore store;
    private EditText repoField;
    private EditText tokenField;
    private CheckBox bootOption;
    private TextView status;
    private Button collectButton;
    private Button uploadButton;
    private Button rootButton;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SecretStore(this);
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dip(18);
        root.setPadding(pad, dip(24), pad, dip(30));
        scroll.addView(root);
        setContentView(scroll);

        TextView title = label("小米17 Pro / OS4 OTA 采集助手", 21);
        title.setTypeface(null, Typeface.BOLD);
        root.addView(title);
        root.addView(label("实验版：只读采集，不自动刷机；上传成功不等于已通过 ABI/KMI 检查。", 13));
        root.addView(label("设备代号：" + Build.DEVICE + " / Android " + Build.VERSION.RELEASE, 14));

        root.addView(label("GitHub 接收仓库（owner/repo）", 14));
        repoField = edit(store.repo());
        root.addView(repoField);
        root.addView(label("Fine-grained PAT（留空则保留已保存凭据）", 14));
        tokenField = edit("");
        tokenField.setHint("只授权单一仓库的 Contents: Read and write");
        tokenField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(tokenField);

        Button saveButton = button("保存仓库与加密凭据", root);
        saveButton.setOnClickListener(v -> {
            try {
                String name = repoField.getText().toString().trim();
                if (!name.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")) {
                    throw new IllegalArgumentException("仓库格式须为 owner/repo");
                }
                store.saveRepo(name);
                String token = tokenField.getText().toString().trim();
                if (!token.isEmpty()) store.saveToken(token);
                tokenField.setText("");
                showStatus("设置已保存。令牌以 Android Keystore AES-GCM 加密存放。");
            } catch (Exception e) {
                showStatus("设置失败：" + safeMessage(e));
            }
        });
        Button clearButton = button("删除本机 GitHub 凭据", root);
        clearButton.setOnClickListener(v -> {
            store.clearToken();
            tokenField.setText("");
            showStatus("已清除本机保存的令牌；GitHub 服务端令牌仍需到 GitHub 撤销。");
        });

        bootOption = new CheckBox(this);
        bootOption.setText("额外采集当前 boot/init_boot/vendor_boot/dtbo（较大且可能并非原厂）");
        bootOption.setChecked(false);
        root.addView(bootOption);
        root.addView(label("默认只采集系统元数据与 OEM 模块。不包含序列号、IMEI 或个人文件。", 13));

        rootButton = button("1. 检查 Root 授权", root);
        rootButton.setOnClickListener(v -> runTask(() -> "Root 正常：" + RootCollector.checkRoot()));
        collectButton = button("2. 一键采集并打包 ZIP", root);
        collectButton.setOnClickListener(v -> runTask(() -> {
            File zip = RootCollector.capture(getApplicationContext(), bootOption.isChecked());
            store.saveArchive(zip.getAbsolutePath());
            return "采集完成：" + zip.getAbsolutePath()
                    + "\n大小：" + (zip.length() / 1024 / 1024) + " MiB（本地文件已保留）";
        }));
        uploadButton = button("3. 上传 Draft Release 并发送触发事件", root);
        uploadButton.setOnClickListener(v -> runTask(() -> {
            File file = new File(store.lastArchive());
            String token = store.loadToken();
            return GitHubUploader.upload(store.repo(), token, file);
        }));

        status = label("尚未操作。建议先检查 Root，再执行只读采集。", 14);
        status.setTextIsSelectable(true);
        root.addView(status);
        root.addView(label("提醒：GitHub Release 单个附件必须小于 2 GiB；完整 OTA ZIP 分片与自动适配桥接尚未实现。", 13));
    }

    private interface Task { String run() throws Exception; }

    private void runTask(Task action) {
        rootButton.setEnabled(false);
        collectButton.setEnabled(false);
        uploadButton.setEnabled(false);
        showStatus("正在执行……请保持应用前台运行。");
        worker.execute(() -> {
            String result;
            try {
                result = action.run();
            } catch (Exception e) {
                result = "失败：" + safeMessage(e);
            }
            final String display = result;
            runOnUiThread(() -> {
                showStatus(display);
                rootButton.setEnabled(true);
                collectButton.setEnabled(true);
                uploadButton.setEnabled(true);
            });
        });
    }

    private String safeMessage(Exception e) {
        String text = e.getMessage();
        if (text == null || text.isEmpty()) return e.getClass().getSimpleName();
        return text.length() > 400 ? text.substring(0, 400) : text;
    }

    private void showStatus(String message) {
        if (status != null) status.setText(message);
    }

    private EditText edit(String initial) {
        EditText box = new EditText(this);
        box.setSingleLine(true);
        box.setTextSize(14);
        box.setText(initial);
        return box;
    }

    private Button button(String text, LinearLayout parent) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        parent.addView(b);
        return b;
    }

    private TextView label(String text, int size) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(size);
        label.setPadding(0, dip(8), 0, dip(8));
        return label;
    }

    private int dip(int dp) {
        return (int) (dp * getResources().getDisplayMetrics().density + 0.5f);
    }

    @Override
    protected void onDestroy() {
        worker.shutdown();
        super.onDestroy();
    }
}
