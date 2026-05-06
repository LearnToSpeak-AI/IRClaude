import hashlib
import tarfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

ERGO_URL_TEMPLATE = (
    "https://github.com/ergochat/ergo/releases/download/"
    "v{version}/ergo-{version}-linux-x86_64.tar.gz"
)


@dataclass(frozen=True)
class VersionPin:
    version: str
    sha256: str


def parse_version_pin(path: Path) -> VersionPin:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        fields[k.strip()] = v.strip()
    return VersionPin(version=fields["version"], sha256=fields["sha256"])


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _extract_ergo(tar_bytes: bytes, target: Path) -> Path:
    with tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith("/ergo") or member.name == "ergo":
                fobj = tf.extractfile(member)
                if fobj is None:
                    raise RuntimeError("could not read ergo entry from tarball")
                payload = fobj.read()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                target.chmod(0o755)
                return target
    raise RuntimeError("ergo binary not found in tarball")


def download_ergo(
    target_dir: Path,
    version: str,
    expected_sha256: str,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    binary = target_dir / "ergo"
    if binary.exists():
        actual = _sha256(binary.read_bytes())
        if actual == expected_sha256:
            return binary

    url = ERGO_URL_TEMPLATE.format(version=version)
    with urlopen(url, timeout=60) as resp:
        tar_bytes = resp.read()

    actual = _sha256(tar_bytes)
    if actual != expected_sha256:
        raise ValueError(
            f"sha256 mismatch for {url}: expected {expected_sha256}, got {actual}"
        )

    return _extract_ergo(tar_bytes, binary)
