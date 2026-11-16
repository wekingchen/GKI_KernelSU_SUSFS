#!/usr/bin/env python3
"""Fail-closed Pandora-only integration guard for upstream SUSFS priority UID filter.

The newer SUSFS branch puts *both call sites* behind
CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER but leaves their two private credential
helpers unconditionally compiled. R62 Clang treats those now-unused helpers as
errors under -Werror. Guard the definitions with the *same* Kconfig symbol;
never disable -Wunused-function or turn on the optional feature as a workaround.

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


def validate_guarded_calls(source: str, sw: int, restore: int, section: int) -> None:
    """Every real helper call must be in one of two exact feature scopes."""
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
            "unknown priority UID filter guard structure")
    require(headers[0] < endings[0] < headers[1] < endings[1],
            "priority UID filter blocks overlap or have invalid ends")
    scopes = tuple(zip(headers, endings))
    executable = strip_noncode(source)

    totals = []
    for name, definition in (
        ("susfs_switch_to_ksu_domain", sw),
        ("susfs_restore_creds", restore),
    ):
        occurrences = [m.start() for m in re.finditer(
            r"\b" + re.escape(name) + r"\s*\(", executable,
        )]
        definitions = [p for p in occurrences if definition <= p < section]
        require(len(definitions) == 1,
                name + " must have exactly one helper definition")
        calls = [p for p in occurrences if p >= section]
        require(bool(calls), name + " has no feature-guarded call sites")
        require(all(any(start < p < finish for start, finish in scopes)
                    for p in calls),
                name + " is referenced outside the feature guard")
        require(len(occurrences) == len(calls) + 1,
                name + " has an unexpected declaration or unguarded reference")
        totals.append(len(calls))
    require(totals[0] == totals[1],
            "credential switch/restore invocation counts diverged")


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
    # Older stable SUSFS keeps the priority UID filter unconditional. Do not
    # introduce a config dependency it never had.
    if IFDEF not in source:
        return source, "UNCHANGED_OLD_LAYOUT"

    # Newer upstream defines a feature-scoped section and a separate scoped
    # feature listing. We only support this proven, exact layout.
    feature = source.find(IFDEF, section)
    require(feature > section, "priority UID filter block must follow helpers")
    end = source.find(FEATURE_END, feature)
    require(end > feature, "priority UID filter scope has no exact end marker")
    if ENDIF in source:
        require(directive_count(source, IFDEF) == 3 and source.count(ENDIF) == 1
                and source[sw - len(IFDEF) - 1:sw] == IFDEF + "\n"
                and ENDIF + "\n\n" + NEXT_SECTION in source,
                "partial or divergent existing compatibility guard")
        validate_guarded_calls(source, sw, restore, section)
        return source, "ALREADY_GUARDED"
    require(directive_count(source, IFDEF) == 2 and source.count(FEATURE_END) == 2,
            "unknown priority UID filter preprocessor structure")
    # The new upstream can add more call sites or comments. Every actual
    # invocation must remain under CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER;
    # count and location are verified structurally, not by a fixed magic 4.
    validate_guarded_calls(source, sw, restore, section)

    # An upstream-owned fix that changes these definitions must be reviewed,
    # never silently overwritten by a generic regex.
    require(ENDIF not in source, "conflicting or incomplete compatibility guard")
    require(source[sw - len(IFDEF) - 1:sw] != IFDEF + "\n",
            "unexpected existing helper guard")

    # Insert after the helper's explanatory comment, and close the scope
    # immediately before sus_path. No function body or call site is changed.
    output = source[:sw] + IFDEF + "\n" + source[sw:]
    idx = output.index(NEXT_SECTION)
    require(output[idx - 2:idx] == "\n\n", "unexpected section separator")
    output = output[:idx] + ENDIF + "\n\n" + output[idx:]
    require(directive_count(output, IFDEF) == 3 and output.count(ENDIF) == 1,
            "guard insertion failed to preserve upstream feature section")
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
