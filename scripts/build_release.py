"""Create an installable ZIP containing only the integration and user docs."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
component = ROOT / "custom_components" / "nirvana_cloud"
version = json.loads((component / "manifest.json").read_text())["version"]
out = ROOT / "dist" / f"nirvana-cloud-{version}.zip"
out.parent.mkdir(exist_ok=True)
files = sorted(p for p in component.rglob("*") if p.is_file() and p.suffix in {".py", ".json"})
files.extend(
    ROOT / p
    for p in (
        "README.md",
        "docs/README.fr.md",
        "VALIDATION.md",
        "LICENSE",
        "CHANGELOG.md",
        "examples/dashboard.yaml",
    )
)
with ZipFile(out, "w", ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT))
with ZipFile(out) as archive:
    assert archive.testzip() is None
    assert "custom_components/nirvana_cloud/manifest.json" in archive.namelist()
    assert not any(
        "__pycache__" in name or name.endswith((".apk", ".xapk")) for name in archive.namelist()
    )
digest = hashlib.sha256(out.read_bytes()).hexdigest()
out.with_suffix(".zip.sha256").write_text(f"{digest}  {out.name}\n")
print(f"{out}: {len(files)} files, {out.stat().st_size} bytes, SHA-256 {digest}")
