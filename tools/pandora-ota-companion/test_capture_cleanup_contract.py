"""Static guard against intermediate OTA snapshot accumulation; device test still required."""
from pathlib import Path
import unittest

ROOT = Path(__file__).parent
SOURCE = (ROOT / "app/src/main/java/com/wekingchen/pandoraota/RootCollector.java").read_text(encoding="utf-8")
UI = (ROOT / "app/src/main/java/com/wekingchen/pandoraota/MainActivity.java").read_text(encoding="utf-8")


class CaptureStorageContract(unittest.TestCase):
    def test_success_deletes_staging_before_returning_zip(self):
        before_return = SOURCE[:SOURCE.index("return zip;")]
        self.assertIn("cleanStaging(parent, dir);", before_return)
        self.assertIn("complete = true;", before_return)
        self.assertLess(before_return.rfind("cleanStaging(parent, dir);"),
                        before_return.rfind("complete = true;"))
        self.assertIn("new ZipOutputStream(", SOURCE)

    def test_failures_delete_partial_zip_and_staging(self):
        self.assertIn("finally {", SOURCE)
        self.assertIn("!complete && zip.isFile() && !zip.delete()", SOURCE)
        self.assertIn("if (dir.exists())", SOURCE)
        self.assertIn("cleanStaging(parent, dir);", SOURCE)

    def test_orphan_recovery_limits_deletion_to_app_staging(self):
        self.assertIn("purgeStaleStaging(ctx)", SOURCE)
        self.assertIn("STALE_AFTER_MS", SOURCE)
        self.assertIn("dir.getCanonicalFile().getParentFile().equals(parent.getCanonicalFile())", SOURCE)
        self.assertNotIn("rm -rf", SOURCE)
        self.assertNotIn("fastboot flash", SOURCE)
        self.assertNotIn("fastboot erase", SOURCE)

    def test_final_archives_are_only_user_deleted_after_remote_confirmation(self):
        self.assertIn("确认删除本地文件？", UI)
        self.assertIn("GitHubUploader.sha256(target)", UI)
        self.assertIn("if (!target.delete())", UI)
        self.assertIn("store.isUploaded(", UI)

    def test_required_ota_metadata_and_partitions(self):
        self.assertIn("ro.mi.os.version.incremental", SOURCE)
        for name in ("boot", "init_boot", "vendor_boot", "dtbo"):
            self.assertIn(name, SOURCE)


if __name__ == "__main__":
    unittest.main()
