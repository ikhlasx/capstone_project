"""Build the submission archive in exactly the layout the Submission Guide requires.

    python -m scripts.package_submission --name IkhlasPV \
        --video path/to/IkhlasPV_Capstone_Video.mp4   (or --video-link https://...) \
        --report path/to/IkhlasPV_Capstone_Report.pdf \
        --effort-log path/to/IkhlasPV_Effort_Log.pdf

Produces dist/<Name>_Capstone_Submission.zip containing:
    01_Video/        the MP4, or video_link.txt
    02_Report/       the report PDF
    03_Workbooks/    the five stage workbooks (from workbooks/) and the effort log PDF
    04_Source_Code/  the repository at the last commit (git archive): no .env, no storage/

It refuses to build if a required part is missing or wrongly named, and it checks the source for
anything that looks like an API key before packing it.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKBOOKS = ["Stage_1_Discovery_Workbook.docx", "Stage_2_PRD_Template.docx", "Stage_3_Prompt_Library.docx",
             "Stage_4_Sprint_Plan.docx", "Stage_5_PRD_Revision_Log.docx"]
KEY_PATTERN = re.compile(rb"sk-or-v1-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}")


def fail(msg: str) -> int:
    print(f"Not built: {msg}")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="full name as enrolled, no spaces, e.g. IkhlasPV")
    video = ap.add_mutually_exclusive_group(required=True)
    video.add_argument("--video", help="the MP4 file")
    video.add_argument("--video-link", help="a link, if the file is too large")
    ap.add_argument("--report", required=True)
    ap.add_argument("--effort-log", required=True)
    ap.add_argument("--workbooks-dir", default=str(ROOT / "workbooks"))
    ap.add_argument("--out-dir", default=str(ROOT / "dist"))
    args = ap.parse_args(argv)

    name = args.name
    if not re.fullmatch(r"[A-Za-z]+", name):
        return fail(f"--name must be letters only, no spaces or numbers (got '{name}')")

    expected = {"report": f"{name}_Capstone_Report.pdf", "effort": f"{name}_Effort_Log.pdf",
                "video": f"{name}_Capstone_Video.mp4"}
    report, effort = Path(args.report), Path(args.effort_log)
    for path, want in ((report, expected["report"]), (effort, expected["effort"])):
        if not path.is_file():
            return fail(f"missing file: {path}")
        if path.name != want:
            return fail(f"{path.name} should be named {want}")
    if args.video:
        vid = Path(args.video)
        if not vid.is_file():
            return fail(f"missing video: {vid}")
        if vid.name != expected["video"]:
            return fail(f"{vid.name} should be named {expected['video']}")
    workbooks = [Path(args.workbooks_dir) / w for w in WORKBOOKS]
    missing = [w.name for w in workbooks if not w.is_file()]
    if missing:
        return fail(f"workbooks missing from {args.workbooks_dir}: {', '.join(missing)}")

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        print("Warning: there are uncommitted changes; the source code folder contains the last commit only.")
    source = subprocess.run(["git", "archive", "--format=zip", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    src_zip = zipfile.ZipFile(io.BytesIO(source))
    for info in src_zip.infolist():
        if info.filename == ".env" or info.filename.startswith("storage/"):
            return fail(f"{info.filename} must not be in the source code")
        if not info.is_dir() and info.file_size < 5_000_000 and KEY_PATTERN.search(src_zip.read(info)):
            return fail(f"{info.filename} contains something that looks like an API key")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{name}_Capstone_Submission.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        if args.video:
            z.write(args.video, f"01_Video/{expected['video']}")
        else:
            z.writestr("01_Video/video_link.txt", args.video_link.strip() + "\n")
        z.write(report, f"02_Report/{expected['report']}")
        for w in workbooks:
            z.write(w, f"03_Workbooks/{w.name}")
        z.write(effort, f"03_Workbooks/{expected['effort']}")
        for info in src_zip.infolist():
            if not info.is_dir():
                z.writestr(f"04_Source_Code/{info.filename}", src_zip.read(info))
    with zipfile.ZipFile(archive) as z:
        tops = sorted({n.split("/")[0] for n in z.namelist()})
        count = len(z.namelist())
    print(f"built {archive}  ({archive.stat().st_size / 1e6:.1f} MB, {count} files)")
    print("top-level folders: " + ", ".join(tops))
    return 0


if __name__ == "__main__":
    sys.exit(main())
