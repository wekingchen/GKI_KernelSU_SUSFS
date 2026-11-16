#!/usr/bin/env python3
"""Fail-closed Pandora-only integration guard for upstream SUSFS priority UID filter.

The current SUSFS branch can use the same credential helpers from either
SUS_PATH or PRIORITY_UID_FILTER. Guard helper definitions by the precise union
of options that invoke them. If neither option is selected, R62 Clang must not
compile unused helpers with -Werror. Never weaken warnings or enable features
as a workaround; unknown or unguarded upstream call sites fail closed.

This operates only on the isolated kernel source checkout copied from the
exact per-run pinned SUSFS commit; it never modifies an upstream repository.
"""
import argparse
import re
from pathlib import Path

SYMBOL = "CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER"
IFDEF = f"#ifdef {SYMBOL}"
ENDIF = f"#endif /* {SYMBOL}: Pandora credential helpers */"
HELPER_SWITCH = "static struct cred *susfs_switch_to_ksu_domain(void) {"
HELPER_RESTORE = "static void susfs_restore_creds(struct cred *orig_cred) {"
NEXT_SECTION = "/* sus_path */"
FEATURE_END = f"#endif // #ifdef {SYMBOL}"
SUS_PATH_SYMBOL = "CONFIG_KSU_SUSFS_SUS_PATH"
COMBINED_IFDEF = f"#if defined({SYMBOL}) || defined({SUS_PATH_SYMBOL})"
COMBINED_ENDIF = (
    f"#endif /* {SYMBOL} || {SUS_PATH_SYMBOL}: Pandora credential helpers */"
)



class CompatibilityError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError("SUSFS priority UID filter layout changed: " + message)


def directive_count(source: str, directive: str) -> int:
    return sum(line.strip() == directive for line in source.splitlines())


def strip_noncode(source: str) -> str:
    """Mask C comments and literals without shifting source positions."""
    literal = re.compile(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        re.DOTALL,
    )
    return literal.sub(
        lambda hit: "".join("\n" if ch == "\n" else " " for ch in hit.group()),
        source,
    )


def validate_guarded_calls(source: str, sw: int, restore: int,
                           section: int) -> frozenset[str]:
    """Prove the real call sites are guarded by exactly one supported option."""
    headers = [m.start() for m in re.finditer(
        r"(?m)^[ \t]*#ifdef[ \t]+" + re.escape(SYMBOL) + r"[ \t]*$",
        source,
    ) if m.start() > section]
    endings = [m.start() for m in re.finditer(
        r"(?m)^[ \t]*#endif[ \t]*//[ \t]*#ifdef[ \t]+"
        + re.escape(SYMBOL) + r"[ \t]*$",
        source,
    ) if m.start() > section]
    require(len(headers) == 2 and len(endings) == 2,
            "priority UID option must have two exact protected blocks")
    require(headers[0] < endings[0] < headers[1] < endings[1],
            "priority UID protected blocks overlap or have invalid ends")

    # Associate each source line with its true preprocessor stack. This also
    # accounts for SUS_PATH, which gained credential-helper callers upstream.
    # No unknown #else/#elif branch can masquerade as a positive config scope.
    known = {SYMBOL, SUS_PATH_SYMBOL}
    stack: list[tuple[str | None, bool]] = []
    scope_spans: list[tuple[int, int, frozenset[str]]] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        directive = re.match(
            r"^[ \t]*#[ \t]*(ifdef|ifndef|if|elif|else|endif)\b(.*)", line
        )
        if directive:
            op, tail = directive.group(1), directive.group(2).strip()
            if op == "ifdef":
                stack.append((tail if tail in known else None, True))
            elif op == "ifndef":
                stack.append((None, True))
            elif op == "if":
                stack.append((None, True))
            elif op in {"else", "elif"}:
                require(bool(stack), "preprocessor else/elif without opener")
                stack[-1] = (None, False)
            elif op == "endif":
                require(bool(stack), "preprocessor endif without opener")
                stack.pop()
        positive = frozenset(name for name, enabled in stack
                             if enabled and name in known)
        scope_spans.append((offset, offset + len(line), positive))
        offset += len(line)
    require(not stack, "preprocessor scopes are not balanced")

    executable = strip_noncode(source)
    used: set[str] = set()
    call_totals: list[int] = []
    for name, definition in (
        ("susfs_switch_to_ksu_domain", sw),
        ("susfs_restore_creds", restore),
    ):
        positions = [m.start() for m in re.finditer(
            r"\b" + re.escape(name) + r"\s*\(", executable,
        )]
        require(sum(definition <= p < section for p in positions) == 1,
                name + " definition no longer matches the expected layout")
        calls = [p for p in positions if p >= section]
        require(bool(calls), name + " has no guarded callers")
        require(len(positions) == len(calls) + 1,
                name + " has an unexpected declaration or early caller")
        for p in calls:
            contexts = [scope for lo, hi, scope in scope_spans if lo <= p < hi]
            require(len(contexts) == 1 and len(contexts[0]) == 1,
                    name + " is referenced outside one supported feature guard")
            used.update(contexts[0])
        call_totals.append(len(calls))
    require(call_totals[0] == call_totals[1],
            "credential switch/restore invocation counts diverged")
    require(SYMBOL in used, "priority UID filter has no credential call sites")
    require(used.issubset(known), "unknown helper feature scope")
    return frozenset(used)


def transform(source: str) -> tuple[str, str]:
    require(source.count(HELPER_SWITCH) == 1, "switch helper definition must be unique")
    require(source.count(HELPER_RESTORE) == 1, "restore helper definition must be unique")
    require(source.count(NEXT_SECTION) == 1, "sus_path section boundary must be unique")
    require(source.count(FEATURE_END) <= 2, "feature section end is ambiguous")
    sw = source.index(HELPER_SWITCH)
    restore = source.index(HELPER_RESTORE)
    section = source.index(NEXT_SECTION)
    require(sw < restore < section, "credential helpers no longer precede sus_path")
    require(source[restore:section].count("\n}\n") == 1,
            "restore helper body/section boundary unexpected")

    # Historical stable SUSFS versions keep this feature unconditional.
    if IFDEF not in source:
        return source, "UNCHANGED_OLD_LAYOUT"

    feature = source.find(IFDEF, section)
    require(feature > section, "priority UID block must follow helpers")
    end = source.find(FEATURE_END, feature)
    require(end > feature, "priority UID filter block has no exact end marker")
    required = validate_guarded_calls(source, sw, restore, section)
    if required == {SYMBOL}:
        begin_guard, end_guard = IFDEF, ENDIF
    elif required == {SYMBOL, SUS_PATH_SYMBOL}:
        begin_guard, end_guard = COMBINED_IFDEF, COMBINED_ENDIF
    else:
        raise CompatibilityError("unexpected credential helper feature dependencies")

    existing_end = [guard for guard in (ENDIF, COMBINED_ENDIF) if guard in source]
    if existing_end:
        require(len(existing_end) == 1 and existing_end[0] == end_guard,
                "helper option dependencies changed since previous patch")
        require(source.count(end_guard) == 1
                and source[sw - len(begin_guard) - 1:sw] == begin_guard + "\n"
                and end_guard + "\n\n" + NEXT_SECTION in source,
                "partial or divergent helper compatibility guard")
        require(directive_count(source, IFDEF) == (
                3 if begin_guard == IFDEF else 2),
                "unexpected guard directive count on second application")
        return source, "ALREADY_GUARDED"

    require(directive_count(source, IFDEF) == 2
            and source.count(FEATURE_END) == 2,
            "unknown priority UID filter preprocessor structure")
    require(source[sw - len(begin_guard) - 1:sw] != begin_guard + "\n",
            "unexpected existing helper guard")
    output = source[:sw] + begin_guard + "\n" + source[sw:]
    idx = output.index(NEXT_SECTION)
    require(output[idx - 2:idx] == "\n\n", "unexpected helper section separator")
    output = output[:idx] + end_guard + "\n\n" + output[idx:]
    require(output.count(end_guard) == 1
            and directive_count(output, IFDEF) == (3 if begin_guard == IFDEF else 2),
            "helper guard insertion failed")
    return output, "WRAPPED_OPTIONAL_PRIORITY_UID_HELPERS"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="isolated kernel fs/susfs.c")
    args = parser.parse_args()
    before = args.source.read_text()
    after, status = transform(before)
    if after != before:
        args.source.write_text(after)
    print(f"[OS4 SUSFS] priority UID helper compatibility: {status}")


if __name__ == "__main__":
    main()
