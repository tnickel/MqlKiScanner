"""Read-only metadata/bytecode audit of the tested distribution jar."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
snapshot = root / "MqlDownloader_final"
artifact = snapshot / "target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar"
versions = {}
majors = {}
with zipfile.ZipFile(artifact) as jar:
    for entry in jar.infolist():
        name = entry.filename
        if name.endswith("/pom.properties") and any(
            f"/{coordinate}/" in name for coordinate in ("jsoup", "webdrivermanager", "log4j-api", "log4j-core")
        ):
            versions[name] = jar.read(entry).decode("utf-8").strip()
        if name.endswith(".class") and not name.startswith("META-INF/versions/") and not name.endswith("module-info.class"):
            magic, minor, major = struct.unpack(">IHH", jar.read(entry)[:8])
            assert magic == 0xCAFEBABE
            majors[major] = majors.get(major, 0) + 1
manifest = json.loads((root / "MqlDownloader_final.manifest.json").read_text(encoding="utf-8"))
pom_hash = hashlib.sha256((snapshot / "pom.xml").read_bytes()).hexdigest()
assert manifest["overlay_sha256"]["pom.xml"] == pom_hash
assert hashlib.sha256((Path(manifest["repo"]) / "pom.xml").read_bytes()).hexdigest() == pom_hash
assert max(majors) <= 55, majors
result = {
    "base_head": manifest["head"],
    "pom_sha256": pom_hash,
    "distribution_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    "artifact_versions": versions,
    "base_class_major_counts": majors,
    "highest_base_major": max(majors),
    "java11_class_version_compatible": max(majors) <= 55,
    "limitation": "Class version compatibility is necessary, not a full Java 11 execution test; tests ran on JDK 25. Multi-release alternatives excluded.",
}
(root / "artifact_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
