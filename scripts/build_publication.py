"""Stage an explicit allowlist of public files, excluding all APK analysis."""

import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
stage = ROOT / "publication" / "home-assistant-nirvana"
files = [
    ROOT / name
    for name in (
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "VALIDATION.md",
        "hacs.json",
        ".gitignore",
        "pyproject.toml",
        "requirements-dev.txt",
    )
]
for name in ("custom_components/nirvana_cloud", "tests", "scripts", ".github", "docs", "examples"):
    files.extend(
        p
        for p in (ROOT / name).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )
for path in files:
    relative = path.relative_to(ROOT)
    assert path.suffix not in {".apk", ".xapk"}
    assert "analysis" not in relative.parts
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
archive_path = ROOT / "dist" / "home-assistant-nirvana-publication.zip"
with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        relative = path.relative_to(ROOT)
        archive.write(stage / relative, relative)
with ZipFile(archive_path) as archive:
    assert archive.testzip() is None
print(f"Prepared {len(files)} public files in {stage}")
print(archive_path)
