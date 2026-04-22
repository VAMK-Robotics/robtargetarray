# ABB RAPID – Robtarget Array Generator

A command-line Python script that reads `robtarget` declarations from an ABB
robot program module (`.mod` or `.modx`) and generates a one-dimensional
`robtarget` array from a user-specified line range. The array is inserted
directly into the file after the last included robtarget.

---

## Requirements

- Python 3.9 or later
- No third-party packages required (standard library only)

---

## Installation

1. **Clone or download** this repository into any folder on your machine.
2. Place your `.mod` or `.modx` module file(s) in the same folder as the
   script for the easiest workflow (the script lists them automatically at
   startup). Files in other locations can be reached by typing their full path.
3. No `pip install` step is needed.

---

## Usage

Open a terminal in the script folder and run:

```bash
python robtarget_array.py
```

The script will guide you through four prompts.

### Prompt 1 – Module file

```
Module files found in the script directory:
  [1]  MainModule.modx

Enter number, filename, or full path  (default = 1):
```

- Press **Enter** to select the first file in the list.
- Type a **list number** (e.g. `1`) to pick by number.
- Type a **filename** (e.g. `MainModule.modx`) to pick by name.
- Type a **full absolute path** to use a file outside the script folder.

### Prompt 2 – First line

```
Line number of the FIRST robtarget to include [1–195]:
```

Enter the line number in the module file where the first robtarget to be
included in the array is declared. Open the file in any text editor with
line numbers enabled to find the correct value.

### Prompt 3 – Last line

```
Line number of the LAST  robtarget to include [26–195]:
```

Enter the line number of the last robtarget to include. Any lines between the
first and last that contain other variable types (`num`, `bool`, `string`,
`speeddata`, `jointtarget`, etc.) are automatically ignored.

### Prompt 4 – Output mode

```
Write to (O)riginal file or create a (C)opy? [O/C, default = C]:
```

| Input | Behaviour |
|-------|-----------|
| `C` or Enter | Writes a new file named `<original>_modified.<ext>` next to the original. |
| `O` | Modifies the original file in-place. A backup is saved automatically as `<original>.<ext>.bak` before any changes are made. |

---

## What the script does

1. Parses every `CONST`, `VAR`, or `PERS robtarget` declaration in the chosen
   line range that has an initializer (`:=`).
2. Skips all other variable types and uninitialized `VAR robtarget` lines.
3. Builds a one-dimensional RAPID array whose:
   - **name** is the first robtarget's name plus the `_A` suffix
     (e.g. `pApproachMS10` → `pApproachMS10_A`)
   - **declaration keyword** (`CONST` / `VAR` / `PERS`) matches the first
     robtarget
   - **size** equals the number of robtargets found
4. Inserts the array immediately after the last included robtarget, without
   overwriting any existing code.

---

## Output format

Each array element is placed on its own line for readability:

```rapid
    CONST robtarget pApproachMS10_A{8}:=[
        [[122.75,-271.35,293.90],[0.083,0.962,0.257,0.026],[-1,0,2,1],[9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]],
        [[362.32,-46.75,480.93],[0.215,0.592,0.774,0.048],[-1,-1,3,1],[9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]],
        ...
        [[362.32,-46.75,480.93],[0.215,0.592,0.774,0.048],[-1,-1,3,1],[9E+09,9E+09,9E+09,9E+09,9E+09,9E+09]]
    ];
```

The indentation of the array declaration matches the indentation of the first
robtarget in the source file.

---

## Notes

- **Multi-line declarations** are handled correctly — the parser joins
  continuation lines until it finds the closing `;`.
- **Mixed indentation** (spaces and tabs) is preserved as-is from the source
  file.
- Backup files (`.bak`) and `_modified` copies are created next to the
  original file and are excluded from version control via `.gitignore`.
