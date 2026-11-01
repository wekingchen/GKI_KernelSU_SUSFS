#!/usr/bin/env python3
"""One-time retention-safe GitHub Actions run cleanup for K50 Pro and Xiaomi OS4.

Dry-run by default. Deleting a run deletes its artifacts too; this script refuses
to delete any run with a non-expired artifact, any cited run, or any live build.
"""
import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = "wekingchen/GKI_KernelSU_SUSFS"
EXPLICIT_PROTECTED = {
    41239924766,  # K50Pro 5.10 build, flashed and verified
    41263720168,  # native upstream priority logic first check
    41262123405,  # first fork sync check
    41263607389,  # restoration policy fully passing regression
    41262029009,  # fork auto-sync integration regression
    41238861791,  # unified LKG routing PR green
    41237269292,  # complete synthetic OTA chain PR green
    41213989920,  # OS4 Gen3 LKG reconstruction
    41217776390,  # verified archive
    41211605491,  # verified LKG promotion
    41210530544,  # OS4 custom build source
    41206357785,  # OS4 Gen2 custom source
    41207919972,  # OS4 LKG promotion
    41072834543,  # tested OS4 AnyKernel3
    40112987860,  # K50Pro original BBG/LTO failure evidence
    38128504763,  # SUSFS incompatible guard evidence
    37964806118,  # earlier successful generic build reference
}
DOC_RUN = re.compile(r"(?<![0-9])(?:3|4)[0-9]{10}(?![0-9])")


def gh_json(endpoint):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{endpoint}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(f"GitHub API failed CLOSED for {endpoint}: {result.stderr[-800:]}")
    return json.loads(result.stdout)


def collect_array(endpoint, key):
    first = gh_json(f"{endpoint}?per_page=100&page=1")
    total = first.get("total_count", len(first[key]))
    result = list(first[key])
    for page in range(2, (total + 99) // 100 + 1):
        result.extend(gh_json(f"{endpoint}?per_page=100&page={page}")[key])
    if len(result) != total:
        raise RuntimeError(f"incomplete pagination {endpoint}: {len(result)} of {total}")
    return result


def referenced_ids():
    cited = set(EXPLICIT_PROTECTED)
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    for raw in tracked:
        if not raw:
            continue
        path = Path(os.fsdecode(raw))
        if not path.exists() or path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        cited.update(int(x) for x in DOC_RUN.findall(data.decode("utf-8", "replace")))
    return cited


def collect_artifacts():
    artifacts = collect_array("actions/artifacts", "artifacts")
    keep = set()
    for art in artifacts:
        if art.get("expired") is False:
            run = art.get("workflow_run")
            if not isinstance(run, dict) or not isinstance(run.get("id"), int):
                raise RuntimeError("nonexpired artifact has no originating run ID; refusing purge")
            keep.add(run["id"])
    return keep, len(artifacts)


def collect_release_refs():
    releases = gh_json("releases?per_page=100")
    protected = set()
    for item in releases:
        parts = [item.get("tag_name") or "", item.get("body") or ""]
        parts.extend((a.get("name") or "") for a in item.get("assets", []))
        for piece in parts:
            for match in DOC_RUN.findall(piece):
                protected.add(int(match))
    return protected


def plan(runs, workflows, keep):
    live = {f".github/workflows/{x}" for x in workflows}
    # Preserve recent two green guard/page check runs per active workflow.
    recent = collections.defaultdict(int)
    latest_success = set()
    for run in sorted(runs, key=lambda r: r["created_at"], reverse=True):
        path = run.get("path") or ""
        name = Path(path).name
        if path not in live or run.get("conclusion") != "success":
            continue
        if name in ("xiaomi-upstream-isolation-guard.yml",
                    "generic-custom-fork-guard.yml", "update-pages.yml",
                    "generic-custom-auto-sync.yml") and recent[path] < 2:
            recent[path] += 1
            latest_success.add(run["id"])

    delete, preserve = [], []
    for run in runs:
        rid = run["id"]
        path = run.get("path") or ""
        name = Path(path).name
        if rid in keep:
            reason = "protected anchor / cited record / unexpired Artifact / Release"
        elif run.get("status") != "completed":
            reason = "running or pending"
        elif rid in latest_success:
            reason = "latest passing CI for live workflow"
        elif path in live and run.get("event") in ("workflow_dispatch", "schedule"):
            reason = "retained direct full build / manual maintenance or schedule"
        elif path in live and name not in (
                "xiaomi-upstream-isolation-guard.yml",
                "generic-custom-fork-guard.yml",
                "update-pages.yml",
                "generic-custom-auto-sync.yml"):
            reason = "live workflow historical evidence"
        else:
            reason = None
        if reason is None:
            delete.append(run)
        else:
            preserve.append((run, reason))
    return delete, preserve


def main():
    apply = "--apply" in sys.argv
    if any(x not in ("--apply",) for x in sys.argv[1:]):
        raise RuntimeError("usage: prune_actions_runs.py [--apply]")
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise RuntimeError("wrong repository")
    if apply and (os.environ.get("GITHUB_REF") != "refs/heads/dev"
                  or os.environ.get("GITHUB_EVENT_NAME") != "push"):
        raise RuntimeError("destructive cleanup is allowed only by a dev push workflow")
    files = {p.name for p in Path(".github/workflows").glob("*.yml")}
    if len(files) < 18:
        raise RuntimeError("missing workflow inventory; abort")
    runs = collect_array("actions/runs", "workflow_runs")
    current = int(os.environ.get("GITHUB_RUN_ID", "0"))
    cited = referenced_ids()
    artifacts, artifact_count = collect_artifacts()
    releases = collect_release_refs()
    keep = cited | artifacts | releases | {current}
    delete, preserve = plan(runs, files, keep)
    if len(delete) > 135:
        raise RuntimeError(f"unexpectedly large purge ({len(delete)}), abort")

    print(json.dumps({
        "mode": "APPLY" if apply else "DRY_RUN",
        "runs_before": len(runs),
        "delete": len(delete),
        "preserve": len(preserve),
        "artifact_records_checked": artifact_count,
        "runs_with_live_artifacts": len(artifacts),
        "explicit_and_source_references": len(cited),
        "release_references": len(releases),
        "delete_by_workflow": dict(collections.Counter(Path(x["path"]).name for x in delete)),
        "delete_ids": [x["id"] for x in delete],
        "protected_live_artifact_runs": sorted(artifacts),
    }, ensure_ascii=False, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"### {'正式清理' if apply else '只读预演'}\n"
                         f"- 原有 {len(runs)} 条，待清理 {len(delete)} 条，"
                         f"保留 {len(preserve)} 条\n"
                         f"- 已检查 {artifact_count} 件 Artifact，"
                         f"所有未过期产物对应的 Run 均受保护\n"
                         f"- 保留完整内核构建、LKG、Release、历史文档引用和关键验收 Run\n")

    if not apply:
        return
    # Final repeat of branch head check (no force push, no rebase).
    actual = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/dev"], text=True).split()[0]
    own = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if actual != own:
        raise RuntimeError("dev advanced since checkout; refusing to delete using stale plan")
    for i, run in enumerate(delete, 1):
        rid = run["id"]
        result = subprocess.run(
            ["gh", "api", "-X", "DELETE", f"repos/{REPOSITORY}/actions/runs/{rid}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise RuntimeError(f"deletion failed at {i}/{len(delete)}, run {rid}: {result.stderr[-800:]}")
        if i % 10 == 0 or i == len(delete):
            print(f"Deleted {i}/{len(delete)} obsolete action runs", flush=True)
    now = collect_array("actions/runs", "workflow_runs")
    if len(now) != len(runs) - len(delete):
        # A new scheduled/push run may legitimately occur concurrently; don't
        # change anything else, just record count for the operator.
        print(f"::warning::post-cleanup count={len(now)}, expected={len(runs)-len(delete)}; concurrent run may exist")
    print(f"CLEANUP_COMPLETE: {len(delete)} removed, current listing {len(now)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("::error::Actions cleanup failed closed:", str(ex), file=sys.stderr)
        sys.exit(1)
