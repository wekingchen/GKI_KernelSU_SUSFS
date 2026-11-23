#!/usr/bin/env python3
"""Keep warm ccache reuse scoped to one OTA and one immutable GKI source."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/xiaomi-sm8850-os4-custom.yml"
BUILDER = ROOT / "scripts/xiaomi-os4/build-r62-features.sh"


class OTACcachePolicy(unittest.TestCase):
    def test_snapshot_changes_may_restore_same_ota_cache(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        before, found, remainder = source.partition('      - name: "新 OTA 功能编译缓存"')
        self.assertTrue(found)
        block, found, _ = remainder.partition('      - name: "只使用最新稳定上游，在新 OTA GKI 上尝试功能编译"')
        self.assertTrue(found)
        ota = "${{ needs.select-baseline.outputs.build }}"
        upstream = "${{ needs.resolve-upstreams.outputs.snapshot_sha256 }}"
        self.assertIn("path: ~/.cache/xiaomi-os4/ccache-ota-*", block)
        self.assertIn("key: pandora-ota-features-" + ota + "-" + upstream + "-", block)
        self.assertIn(
            "restore-keys: |\n            pandora-ota-features-" + ota + "-",
            block,
        )
        self.assertNotIn("restore-keys: |\n            pandora-ota-features-\n", block)
        self.assertNotIn("xiaomi-pandora-os4-ccache-r62-", block)

    def test_directory_is_partitioned_by_gki_commit(self):
        script = BUILDER.read_text(encoding="utf-8")
        self.assertIn(
            'export CCACHE_DIR="$HOME/.cache/xiaomi-os4/ccache-ota-$OS4_GKI_COMMON_COMMIT"',
            script,
        )
        self.assertIn('export CCACHE_COMPILERCHECK="string:android-r536225"', script)
        self.assertIn('ccache --show-stats | tee "$RESULT/ccache-after-build.txt" || true', script)


if __name__ == "__main__":
    unittest.main()
