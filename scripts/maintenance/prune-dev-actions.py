#!/usr/bin/env python3
"""Safely remove repetitive CI-only GitHub Actions runs; preserve real OTA/LKG evidence.

No workflow deletion. Manual and repository-dispatch runs are never candidates.
Keep newest eight, oldest one and newest three failed per repetitive CI workflow;
also keep every run ID referenced by the current repository's documents/config.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import time

REPOSITORY = "wekingchen/GKI_KernelSU_SUSFS"
NOISY_CI_NAMES = frozenset({
    "小米内核 / 上游文件隔离门禁",
    "小米17 Pro OS4 / 手机 OTA 接收契约回归",
    "小米17 Pro OS4 / 全链路可信阶段状态",
    "小米17 Pro OS4 / OTA 助手 Android 模拟器验证",
    "小米17 Pro OS4 / OTA 助手 APK 与固定签名校验",
    "Update Data & Deploy Pages",
    "小米17 Pro OS4 / OTA V2 真实 ABI 阻断回放（只读）",
    "自定义内核 / 隔离修复版回归与上游保护",
    "小米17 Pro OS4 / EEXIST 自定义构建路由回归",
    "小米17 Pro OS4 / SUSFS 固定上游源码兼容验证",
})
OLD_SINGLE_USE = ("仓库维护 / ", "维护 / 清理", ".github/workflows/maintenance-prune-",
                  ".github/workflows/pandora-actions-history-hygiene.yml")
NON_DELETABLE_EVENTS = {"workflow_dispatch", "repository_dispatch", "workflow_run", "release"}
RUN_ID_RE = re.compile(r"(?<!\d)\d{10,12}(?!\d)")
MAX_DELETIONS = 650


def gh(path: str, method: str = "GET") -> dict:
    cmd = ["gh", "api"]
    if method != "GET":
        cmd += ["-X", method]
    cmd.append("repos/" + REPOSITORY + "/" + path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"GitHub {method} {path}: {result.stderr[:350]}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def referenced_run_ids(repo: Path) -> set[int]:
    """Conservative: retain any numeric Run ID appearing in auditable repo text."""
    refs: set[int] = set()
    for parent in ("docs", "tools/pandora-ota-companion", ".github/config",
                   "scripts/xiaomi-os4/ota-v2-references"):
        directory = repo / parent
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix not in {".md", ".json", ".env", ".txt"}:
                continue
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
            refs.update(int(x) for x in RUN_ID_RE.findall(path.read_text(
                encoding="utf-8", errors="replace")))
    # Critical original tested custom, promotion, Gen7 stage, and replay proof.
    refs.update({
        45124613997, 45128727756, 45135431152, 45139674561,
        45141955267, 45141107858, 45142648013, 45142882806,
        44888223032, 44925895903, 41280701707,
        45196414652,  # Successful OTA V2 branch/CI cleanup transaction (34 removed).
    })
    return refs


def make_plan(runs: list[dict], pinned: set[int], current_id: int,
              active_pr_heads: set[str] | None = None) -> tuple[list[int], dict]:
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for run in runs:
        if run.get("name") in NOISY_CI_NAMES:
            groups[run["name"]].append(run)

    protected = set(pinned) | {current_id}
    active_pr_heads = active_pr_heads or set()
    for members in groups.values():
        ordered = sorted(members, key=lambda r: (r["created_at"], r["id"]), reverse=True)
        protected.update(r["id"] for r in ordered[:8])  # newest useful CI results
        protected.add(ordered[-1]["id"])               # original regression baseline
        protected.update(r["id"] for r in [
            x for x in ordered if x.get("conclusion") == "failure"][:3])

    deletable = []
    by_name = collections.Counter()
    seen = set()
    for r in sorted(runs, key=lambda r: r["id"]):
        rid = r["id"]
        if rid in seen:
            continue
        seen.add(rid)
        if (rid in protected or r.get("status") != "completed"
                or r.get("head_sha") in active_pr_heads
                or r.get("event") in NON_DELETABLE_EVENTS):
            continue
        n = r.get("name", "")
        if n in NOISY_CI_NAMES or n.startswith(OLD_SINGLE_USE):
            deletable.append(rid)
            by_name[n] += 1
    if len(deletable) > MAX_DELETIONS:
        raise ValueError(f"Safety cap exceeded: {len(deletable)} > {MAX_DELETIONS}")
    return deletable, dict(by_name)


def read_runs() -> list[dict]:
    result = []
    for page in range(1, 31):
        data = gh(f"actions/runs?per_page=100&page={page}")
        batch = data.get("workflow_runs", [])
        result.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("Too many Actions runs to audit in a single bounded pass")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Delete only the exact plan that was just checked")
    args = parser.parse_args()
    if (os.getenv("GITHUB_REPOSITORY") != REPOSITORY
            or os.getenv("GITHUB_REF_NAME") != "dev"
            or not os.getenv("GH_TOKEN")):
        raise SystemExit("Only the owner's checked-out dev workflow with a token may run")
    pinned = referenced_run_ids(Path.cwd())
    runs = read_runs()
    prs = gh("pulls?state=open&per_page=100")
    active_heads = {p["head"]["sha"] for p in prs if p.get("head", {}).get("sha")}
    plan, by_name = make_plan(runs, pinned, int(os.getenv("GITHUB_RUN_ID", "0")),
                              active_pr_heads=active_heads)
    print(json.dumps({
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "before": len(runs), "planned_deletions": len(plan),
        "protected_document_run_ids": len(pinned),
        "protected_open_pr_heads": len(active_heads),
        "by_workflow": by_name,
    }, ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        return

    removed = 0
    errors = []
    for rid in plan:
        for attempt in range(3):
            try:
                gh(f"actions/runs/{rid}", "DELETE")
                removed += 1
                break
            except RuntimeError as exc:
                if attempt == 2:
                    errors.append(f"{rid}: {exc}")
                else:
                    time.sleep((attempt + 1) * 2)

    summary = (f"Action 日志安全清理：原有 {len(runs)} 条，"
               f"计划删除重复 CI {len(plan)} 条，成功 {removed} 条；"
               f"保留用户手动操作、手机接收/OTA/LKG、仓库文档引用的 Run，"
               f"及每条 CI 的最新/最早/重要失败证据。")
    print(summary, flush=True)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### dev Actions 运行记录安全清理\n\n" + summary + "\n")
            if errors:
                f.write(f"\n失败 {len(errors)} 条，可重试。不会删除其他类型的 Run。\n")
    if errors:
        raise SystemExit("\n".join(errors[:12]))


if __name__ == "__main__":
    main()
