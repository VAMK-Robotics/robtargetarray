#!/usr/bin/env python3
"""
ABB RAPID – Robtarget Array Generator
======================================
Reads robtarget declarations from a .mod/.modx file within a user-specified
line range and generates a one-dimensional RAPID robtarget array from them.
The array is inserted directly after the last robtarget in the range.

• Handles CONST / VAR / PERS declarations.
• Skips other variable types (num, string, bool, jointtarget, speeddata …).
• Skips uninitialized robtargets (no := assignment).
• Handles multi-line declarations.
• Preserves original file indentation style.
• Can write to the original file (with auto-backup) or create a _modified copy.
"""

import re
import os
import sys
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches the start of any robtarget declaration line (with assignment)
_RT_START = re.compile(
    r"^\s*(CONST|VAR|PERS)\s+robtarget\s+(\w+)\s*:=",
    re.IGNORECASE,
)

# Matches a complete (possibly joined) robtarget declaration
_RT_FULL = re.compile(
    r"(CONST|VAR|PERS)\s+robtarget\s+(\w+)\s*:=\s*(.*?)\s*;",
    re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def find_mod_files(directory: str) -> list:
    """Return sorted list of .mod/.modx Path objects found in *directory*."""
    try:
        return sorted(
            f for f in Path(directory).iterdir()
            if f.is_file() and f.suffix.lower() in (".mod", ".modx")
        )
    except (PermissionError, FileNotFoundError):
        return []


def prompt_file(script_dir: str) -> Path:
    """
    Interactively ask the user for a module file.
    Lists .mod/.modx files in the script directory as numbered shortcuts.
    """
    mod_files = find_mod_files(script_dir)

    if mod_files:
        print("\nModule files found in the script directory:")
        for i, f in enumerate(mod_files, 1):
            print(f"  [{i}]  {f.name}")
        print()
        hint = "Enter number, filename, or full path  (default = 1): "
    else:
        print("\nNo .mod/.modx files found in the script directory.")
        hint = "Enter filename or full path: "

    while True:
        raw = input(hint).strip()

        # Default → first file in list
        if raw == "" and mod_files:
            return mod_files[0]

        # Numeric shortcut
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(mod_files):
                return mod_files[idx]
            print(f"  Invalid number – enter 1 to {len(mod_files)}.")
            continue

        # Path entered by the user
        p = Path(raw)
        if not p.is_absolute():
            candidate = Path(script_dir) / p
            if candidate.exists():
                p = candidate

        if not p.exists():
            print(f"  File not found: {p}")
            continue
        if p.suffix.lower() not in (".mod", ".modx"):
            print("  File must have a .mod or .modx extension.")
            continue
        return p


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def prompt_int(prompt_text: str, lo: int, hi: int) -> int:
    """Repeatedly ask for an integer in [lo, hi]."""
    while True:
        try:
            val = int(input(prompt_text).strip())
            if lo <= val <= hi:
                return val
            print(f"  Please enter a number between {lo} and {hi}.")
        except ValueError:
            print("  Please enter a valid integer.")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _collect_declaration(lines: list, start_0: int) -> tuple:
    """
    Starting at *start_0* (0-indexed), concatenate lines until a ';' is found.
    Returns (joined_text, end_0_index).
    """
    combined = lines[start_0].rstrip()
    j = start_0
    while ";" not in combined and j + 1 < len(lines):
        j += 1
        combined += " " + lines[j].strip()
    return combined, j


def parse_robtargets(lines: list, start_line: int, end_line: int) -> list:
    """
    Find all initialised robtarget declarations within the 1-indexed line range
    [start_line, end_line].

    Returns a list of dicts:
        decl_type  – 'CONST', 'VAR', or 'PERS'
        name       – variable name
        value      – everything between := and ; (the robtarget value)
        start_line – 1-indexed first line of declaration
        end_line   – 1-indexed last line of declaration (for multi-line)
        raw_indent – leading whitespace of the declaration line
    """
    results = []
    i = start_line - 1          # convert to 0-indexed
    end_0 = end_line - 1

    while i <= end_0:
        line = lines[i]
        if _RT_START.match(line):
            combined, j = _collect_declaration(lines, i)
            m = _RT_FULL.search(combined)
            if m:
                # Preserve the original leading whitespace
                raw_indent = line[: len(line) - len(line.lstrip())]
                results.append(
                    {
                        "decl_type": m.group(1).upper(),
                        "name": m.group(2),
                        "value": m.group(3).strip(),
                        "start_line": i + 1,
                        "end_line": j + 1,
                        "raw_indent": raw_indent,
                    }
                )
            i = j + 1
        else:
            i += 1

    return results


# ---------------------------------------------------------------------------
# Array building
# ---------------------------------------------------------------------------

def build_array_text(robtargets: list) -> str:
    """
    Build the RAPID robtarget array declaration.

    Layout:
        <indent><DECL> robtarget <name>{<n>}:=[
        <indent>    <value>,
        <indent>    <value>
        <indent>];

    The declaration type and indentation are taken from the first robtarget.
    """
    first = robtargets[0]
    decl_type = first["decl_type"]
    array_name = first["name"] + "_A"
    count = len(robtargets)

    # Match the indentation of the first declaration line
    base_indent = first["raw_indent"]
    # Use 4 extra spaces for array elements
    elem_indent = base_indent + "    "

    out = [f"{base_indent}{decl_type} robtarget {array_name}{{{count}}}:=["]
    for idx, rt in enumerate(robtargets):
        comma = "," if idx < count - 1 else ""
        out.append(f"{elem_indent}{rt['value']}{comma}")
    out.append(f"{base_indent}];")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# File modification
# ---------------------------------------------------------------------------

def insert_after_line(lines: list, after_1idx: int, new_text: str) -> list:
    """
    Return a new lines list with *new_text* inserted after *after_1idx*
    (1-indexed).  Each logical line in *new_text* becomes a separate element
    with a trailing newline, matching the surrounding file content.
    """
    new_lines = [ln + "\n" for ln in new_text.splitlines()]
    return lines[:after_1idx] + new_lines + lines[after_1idx:]


def make_output_path(file_path: Path) -> Path:
    """Return a non-colliding '_modified' copy path."""
    candidate = file_path.with_name(file_path.stem + "_modified" + file_path.suffix)
    counter = 1
    while candidate.exists():
        candidate = file_path.with_name(
            f"{file_path.stem}_modified_{counter}{file_path.suffix}"
        )
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = str(Path(sys.argv[0]).parent.resolve())

    print()
    print("=" * 62)
    print("   ABB RAPID  –  Robtarget Array Generator")
    print("=" * 62)

    # ── 1. File selection ────────────────────────────────────────────────
    file_path = prompt_file(script_dir)
    print(f"\nUsing file: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"Error reading file: {exc}")
        _pause()
        sys.exit(1)

    total = len(lines)
    print(f"Total lines in file: {total}")

    # ── 2. Line range ────────────────────────────────────────────────────
    print()
    start_line = prompt_int(
        f"Line number of the FIRST robtarget to include [1–{total}]: ",
        1,
        total,
    )
    end_line = prompt_int(
        f"Line number of the LAST  robtarget to include [{start_line}–{total}]: ",
        start_line,
        total,
    )

    # ── 3. Parse robtargets ──────────────────────────────────────────────
    print()
    robtargets = parse_robtargets(lines, start_line, end_line)

    if not robtargets:
        print(
            f"No initialised robtargets found between lines {start_line} and {end_line}.\n"
            "Tip: uninitialized VAR robtargets (no ':=' assignment) are not included.\n"
            "Please check the line range and try again."
        )
        _pause()
        sys.exit(1)

    # Report what was found (and what was skipped)
    _report_found(robtargets, start_line, end_line, lines)

    # ── 4. Output mode ───────────────────────────────────────────────────
    print()
    write_original = _ask_output_mode()

    # ── 5. Build array text ──────────────────────────────────────────────
    array_text = build_array_text(robtargets)
    first = robtargets[0]
    array_name = first["name"] + "_A"

    print(f"\nGenerated declaration  →  "
          f"{first['decl_type']} robtarget {array_name}{{{len(robtargets)}}}")
    print("\nPreview:")
    print("─" * 62)
    print(array_text)
    print("─" * 62)

    # ── 6. Determine insertion point ─────────────────────────────────────
    # Insert after the last *physical* line of the last robtarget
    insert_after = robtargets[-1]["end_line"]
    print(f"\nArray will be inserted after line {insert_after}.")

    # ── 7. Build modified lines list ─────────────────────────────────────
    modified = insert_after_line(lines, insert_after, array_text)

    # ── 8. Write output ──────────────────────────────────────────────────
    if write_original:
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)
        output_path = file_path
        print(f"Backup saved: {backup_path}")
    else:
        output_path = make_output_path(file_path)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.writelines(modified)
    except OSError as exc:
        print(f"Error writing output file: {exc}")
        _pause()
        sys.exit(1)

    print(f"\nDone!  Output written to:  {output_path}")
    _pause()


# ---------------------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------------------

def _report_found(robtargets: list, start_line: int, end_line: int, lines: list) -> None:
    """Print a summary of what was found (and list skipped non-robtarget lines)."""
    print(f"Found {len(robtargets)} robtarget(s) in lines {start_line}–{end_line}:")
    for rt in robtargets:
        span = (
            f"line {rt['start_line']}"
            if rt["start_line"] == rt["end_line"]
            else f"lines {rt['start_line']}–{rt['end_line']}"
        )
        print(f"  {span:18s}  {rt['decl_type']} robtarget {rt['name']}")

    # Report robtarget lines that were skipped (uninitialized)
    rt_start_re = re.compile(
        r"^\s*(CONST|VAR|PERS)\s+robtarget\s+(\w+)\s*(?!:=)",
        re.IGNORECASE,
    )
    found_names = {rt["name"] for rt in robtargets}
    skipped = []
    for lno in range(start_line - 1, end_line):
        m = rt_start_re.match(lines[lno])
        if m and m.group(2) not in found_names:
            skipped.append((lno + 1, m.group(2)))
    if skipped:
        print(
            f"\nNote: {len(skipped)} robtarget(s) skipped "
            "(uninitialized – no ':=' assignment):"
        )
        for lno, name in skipped:
            print(f"  line {lno}: {name}")


def _ask_output_mode() -> bool:
    """Ask the user whether to write to the original file or a copy."""
    while True:
        choice = input(
            "Write to (O)riginal file or create a (C)opy? [O/C, default = C]: "
        ).strip().upper()
        if choice in ("", "C"):
            return False
        if choice == "O":
            return True
        print("  Please enter 'O' or 'C'.")


def _pause() -> None:
    input("\nPress Enter to exit …")


if __name__ == "__main__":
    main()
