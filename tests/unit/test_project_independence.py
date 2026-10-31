"""项目边界扫描器的行为回归 / Behavioral regressions for the project boundary scanner."""

import importlib.util
import subprocess
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "project_independence",
    Path(__file__).parents[2] / "scripts/check_project_independence.py",
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_normalization_and_embedded_identifiers():
    policy = (scanner.fingerprint("AcmeRuntime"), scanner.fingerprint("acme", "word"))
    for text in (
        "ACME-runtime",
        "ＡｃｍｅＲｕｎｔｉｍｅ",
        "test_acmeruntime_adapter",
        "acme.service",
    ):
        assert scanner.restricted(text, policy)
    assert not scanner.restricted("acmeology and a zenith observation", policy)


def test_staged_content_is_checked_instead_of_working_copy(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "sample.txt"
    path.write_text("AcmeRuntime")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)
    path.write_text("generic provider")
    original = scanner.restricted
    monkeypatch.setattr(
        scanner,
        "restricted",
        lambda text: original(text, (scanner.fingerprint("AcmeRuntime"),)),
    )
    findings = []
    scanner.scan_repository(tmp_path, True, findings)
    assert findings == ["sample.txt"]
    findings.clear()
    scanner.scan_repository(tmp_path, False, findings)
    assert not findings


def test_release_archive_content_and_filename_are_checked(tmp_path, monkeypatch):
    original = scanner.restricted
    monkeypatch.setattr(
        scanner,
        "restricted",
        lambda text: original(text, (scanner.fingerprint("AcmeRuntime"),)),
    )
    archive = tmp_path / "package.whl"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("provider.txt", "AcmeRuntime")
        output.writestr("acmeruntime/empty.txt", "")
    findings = []
    scanner.scan_archive(archive, findings)
    assert len(findings) == 2


def test_old_history_is_rejected_even_when_tip_is_clean(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "sample.txt"
    for content in ["AcmeRuntime", "generic provider"]:
        path.write_text(content)
        subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "测试历史 / Test history",
            ],
            check=True,
        )
    original = scanner.restricted
    monkeypatch.setattr(
        scanner,
        "restricted",
        lambda text: original(text, (scanner.fingerprint("AcmeRuntime"),)),
    )
    findings = []
    scanner.scan_repository(tmp_path, False, findings)
    assert not findings
    scanner.scan_history(tmp_path, "HEAD", findings)
    assert any(label.endswith(":sample.txt") for label in findings)


def test_readable_binary_metadata_is_checked(monkeypatch):
    original = scanner.restricted
    monkeypatch.setattr(
        scanner,
        "restricted",
        lambda text: original(text, (scanner.fingerprint("AcmeRuntime"),)),
    )
    findings = []
    scanner.inspect("sample.bin", b"\x00\xffAcmeRuntime\x00", findings)
    assert findings == ["sample.bin"]
