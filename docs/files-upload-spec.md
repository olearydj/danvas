# Canvas Files Upload Spec

## Purpose

Add a focused `danvas files upload` command for uploading one or more local
course files into Canvas Files.

This should cover the recurring course-material workflow where a user has a small
set of local assets, such as slides and spreadsheets, and needs them placed in an
existing Canvas Files folder without using the Canvas web UI. It is not intended
to be a bidirectional file sync feature.

## Proposed Command Surface

```bash
danvas files upload \
  --folder "course files/slides" \
  content/slides/Lecture\ 14\ -\ Book\ Depreciation.pptx \
  content/slides/Lecture\ 14\ -\ Sheets.xlsx
```

Useful variants:

```bash
danvas files upload --folder-id 15968602 --on-duplicate overwrite FILE...
danvas files upload --folder "course files/slides" --dry-run FILE...
danvas files upload --folder "course files/slides" --output .danvas/uploaded-files.json FILE...
```

Recommended options:

| Option | Type | Default | Notes |
|---|---|---:|---|
| `FILE...` | paths | required | One or more local files to upload. Directories are rejected for v1. |
| `--course-id` | int | config | Same resolution behavior as existing Canvas-backed commands. |
| `--folder` | text | none | Exact Canvas folder `full_name`, for example `course files/slides`. |
| `--folder-id` | int | none | Direct Canvas folder ID. Mutually exclusive with `--folder`. |
| `--on-duplicate` | enum | `overwrite` | Pass through to Canvas. Support `overwrite` and `rename` initially. |
| `--dry-run` | bool | false | Resolve course, folder, local files, sizes, and content types, but do not upload. |
| `--output` | path | none | Optional JSON upload report. |

Use the same auth options already present on other commands:

```text
--api-url
--secret-provider auto|1password|env
--op-reference
--api-key-env
```

## Non-Goals For V1

- Do not implement whole-tree sync.
- Do not delete Canvas files.
- Do not recursively upload directories.
- Do not create assignment, announcement, discussion, or quiz links.
- Do not rewrite Markdown sources.
- Do not create folders by default.

Folder creation can be a later explicit feature, for example
`--create-folder`, after the path rules are designed carefully.

## Behavior

1. Resolve course ID and API URL through the normal `args_for` and
   `.danvas/config.toml` path.
2. Resolve the Canvas token with `canvas_from_args`.
3. Validate every local path before any live upload:
   - path exists
   - path is a file
   - path is readable
   - no duplicate local basenames unless `--on-duplicate rename` is selected, or
     unless the command explicitly documents that Canvas will handle them
4. Resolve the destination folder:
   - `--folder-id` uses `canvas.get_folder(folder_id)`
   - `--folder` lists `course.get_folders()` and matches exact `folder.full_name`
   - zero matches fails with available nearby folder names when possible
   - multiple matches fails, even though Canvas full names should normally be unique
5. In `--dry-run`, print a JSON-ish preview:
   - course ID and course name
   - folder ID and folder full name
   - duplicate policy
   - file path, display name, byte size, and content type for each local file
6. In live mode, print a Canvas mutation banner before uploading:

```text
== Canvas write: upload 6 file(s) to course 1742717 folder course files/slides ==
```

7. Upload files one at a time and print one result row per file:
   - local source path
   - Canvas file ID
   - display name
   - filename
   - folder ID
   - size
   - content type
   - URL presence as a boolean, not the verifier/download URL itself
8. Exit nonzero on any failed upload. If some files already uploaded, report the
   partial success clearly.
9. If `--output` is set, write a JSON report with the preview fields plus upload
   results.

## Output Shape

The JSON report should avoid verifier URLs and other short-lived download links.

Suggested schema:

```json
{
  "course_id": 1742717,
  "course_name": "Eng Econ 6600",
  "folder_id": 15968602,
  "folder_full_name": "course files/slides",
  "on_duplicate": "overwrite",
  "dry_run": false,
  "files": [
    {
      "source": "content/slides/Lecture 14 - Sheets.xlsx",
      "name": "Lecture 14 - Sheets.xlsx",
      "size": 13345,
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "status": "uploaded",
      "canvas_id": 285247871,
      "display_name": "Lecture 14 - Sheets.xlsx",
      "filename": "Lecture+14+-+Sheets.xlsx",
      "folder_id": 15968602,
      "url_present": true
    }
  ]
}
```

The console output can be human-readable, but each uploaded row should contain
enough structured information to paste into a handoff note.

## Implementation Touchpoints

Primary code locations:

- `src/danvas/files.py`
  - add `command_files_upload(args)`
  - add helpers for folder resolution, content-type detection, and report row
    normalization
- `src/danvas/cli.py`
  - add `@files_app.command("upload")`
  - wire existing course/auth options plus upload-specific options
- `tests/test_files.py`
  - extend existing fake course/folder/file patterns for upload tests
- `README.md` and `/Users/djo/.codex/skills/teaching-danvas/references/danvas-commands.md`
  - update only when the implementation lands

Useful existing helpers and patterns:

- `canvas_from_args(args)` in `danvas.auth`
- `canvas_object_to_dict(...)` in `danvas.utils`
- `print_mutation_banner(...)` in `danvas.utils`
- existing file metadata normalization in `canvas_file_record(...)`
- existing `files inventory` tests for avoiding verifier URLs
- `quiz_import.command_quiz_import_qti(...)` for write-command dry-run and
  mutation-banner style

CanvasAPI already provides folder uploads:

```python
ok, response = folder.upload(
    str(path),
    on_duplicate=args.on_duplicate,
    content_type=content_type_for(path),
)
```

For content types, v1 can use `mimetypes.guess_type(...)` plus explicit mappings
for common Office extensions:

```python
{
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
```

## Prototype Sketch From 2026-06-14 Upload

The initial manual workflow uploaded six lecture files for INSY 6600:

- `Lecture 14 - Book Depreciation.pptx`
- `Lecture 14 - Sheets.xlsx`
- `Lecture 15 - Tax Depreciation.pptx`
- `Lecture 15 - Sheets.xlsx`
- `Lecture 16 - Corporate Taxes.pptx`
- `Lecture 16 - Sheets.xlsx`

Since `danvas files` only had `inventory` and `download`, the prototype used a
temporary Python driver in the installed danvas environment:

1. Read `.danvas/config.toml` to get Canvas API URL and course ID.
2. Used `danvas.auth.resolve_api_key(...)` so token behavior matched danvas.
3. Created `Canvas(api_url, api_key)` and loaded `course = canvas.get_course(course_id)`.
4. Listed `course.get_folders()` and matched the exact destination
   `folder.full_name == "course files/slides"`.
5. Built a dry-run payload with local absolute path, basename, byte size, and MIME
   type.
6. In live mode, printed:

```text
== Canvas write: upload 6 file(s) to course 1742717 folder course files/slides ==
```

7. Called `folder.upload(...)` once per local file with:

```python
on_duplicate="overwrite"
content_type=content_type_for(path)
```

8. Printed one JSON row per file with `ok`, source path, Canvas file ID,
   display name, encoded filename, size, content type, folder ID, and a
   `url_present` boolean.
9. Ran `danvas files inventory --local-root .` afterward to verify that all six
   uploaded files were `present_by_name_and_size`.

This prototype is intentionally close to the desired implementation. The main
production changes are to route through `canvas_from_args(args)`, use
`print_mutation_banner`, add tests, and formalize the CLI.

## Acceptance Tests

Unit-level tests:

- dry-run validates files and resolves the folder but does not call `folder.upload`
- missing local file exits nonzero before contacting Canvas for upload
- `--folder` exact match selects the intended fake folder
- zero `--folder` matches exits with a clear message
- ambiguous `--folder` matches exit with a clear message
- `--folder-id` calls `canvas.get_folder(folder_id)`
- live upload calls `folder.upload(...)` once per file
- `on_duplicate` and `content_type` are passed to CanvasAPI
- upload report excludes verifier URLs even if Canvas returns one
- partial failure reports already-uploaded files and exits nonzero

CLI-level tests:

- `danvas files upload --dry-run --folder "course files/slides" FILE` invokes
  `command_files_upload` with resolved args
- `--folder` and `--folder-id` are mutually exclusive
- auth/course options are accepted consistently with `files inventory`

Manual smoke test against a real course:

```bash
danvas files upload --folder "course files/slides" --dry-run content/slides/example.pptx
danvas files upload --folder "course files/slides" content/slides/example.pptx
danvas files inventory --output-dir .danvas/files-inventory-after-upload --local-root .
```

Expected verification: the uploaded file appears in the target Canvas folder and
the inventory classifies it as `present_by_name_and_size`.

## Open Questions

- Should `overwrite` or `rename` be the default? The prototype used `overwrite`
  because it was retrying known course-material filenames. `rename` is safer for
  accidental replacement, but creates duplicates during retries.
- Should v1 support `--create-folder`, or should folder creation wait until there
  is a separate `files folders` command?
- Should an optional `--verify` run a lightweight post-upload lookup, or should
  users continue to run `danvas files inventory` after uploads?
- Should output reports live by default under `.danvas/uploads/`, or only when
  `--output` is passed?
