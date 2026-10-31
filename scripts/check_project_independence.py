#!/usr/bin/env python3
"""阻止应用专属信息进入通用项目 / Keep application-specific data out of this project."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

# 仅保存不可逆指纹，避免在规则中复制受限名称 / Store digests without reproducing restricted names.
FINGERPRINTS = (
    ("word", 5, "3085e1a1e739cb5e1bfacbadc08b281cc579a3bb3cb5c226b834baf291d17b7e"),
    ("contains", 8, "6a6fecf63777d4066cd9c85bbc64dcabd5af8cfac833937a91cdb35fc70bd427"),
    (
        "contains",
        14,
        "b3e824eb34002a1eec9e238ab76f4258e23c36ec06b68037c6982f887fb26f53",
    ),
    ("contains", 9, "773c1422a823c0eb3f045caa749dacaf3800367cd95407a069df6c11c0183a9e"),
    ("contains", 4, "4440777329167b97368ed1198ec34e4bed0a61f97180ce1ab775bbe0c96e6025"),
)


def git(root, *args):
    """读取 Git，不使用 shell 插值 / Read Git without shell interpolation."""
    return subprocess.check_output(["git", "-C", str(root), *args])


def fingerprint(term, mode="contains"):
    """规范化指纹支持大小写和分隔符 / Normalize case and separators for fingerprints."""
    term = "".join(
        c for c in unicodedata.normalize("NFKC", term).casefold() if c.isalnum()
    )
    return mode, len(term), hashlib.sha256(term.encode()).hexdigest()


@lru_cache(maxsize=32)
def grouped_policy(policy):
    """缓存不变的规则分组 / Cache immutable policy groups."""
    by_mode = {}
    for mode, length, digest in policy:
        by_mode.setdefault((mode, length), set()).add(digest)
    return by_mode


@lru_cache(maxsize=131072)
def restricted_join(joined, policy, single_word):
    """缓存重复标识符和短语，避免逐版本重复散列 / Cache repeated identifiers and phrases across revisions."""
    for (mode, length), digests in grouped_policy(policy).items():
        if mode == "word":
            candidates = [joined] if single_word and len(joined) == length else []
        else:
            candidates = (
                joined[j : j + length] for j in range(len(joined) - length + 1)
            )
        if any(hashlib.sha256(c.encode()).hexdigest() in digests for c in candidates):
            return True
    return False


def restricted(text, policy=FINGERPRINTS):
    """检查词和相邻词组合，保留正常天文术语 / Check words and joins without rejecting astronomy terms."""
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", text).casefold())
    for i in range(len(words)):
        for count in range(1, 4):
            joined = "".join(words[i : i + count])
            if restricted_join(joined, policy, count == 1):
                return True
    return False


def inspect(label, data, findings):
    """只报告位置，不回显受限文本 / Report locations without echoing restricted content."""
    # 二进制仅提取可读字符串，不拼接随机字节 / Inspect readable binary strings without joining random bytes.
    texts = (
        (part.decode("ascii") for part in re.findall(rb"[\x20-\x7e]{4,}", data))
        if b"\0" in data
        else (data.decode("utf-8", errors="ignore"),)
    )
    if restricted(label) or any(restricted(text) for text in texts):
        findings.append(label)


def scan_repository(root, staged, findings):
    """覆盖完整索引或当前检出及非忽略新文件 / Scan the whole index or checkout and new files."""
    args = ["ls-files", "-z", "--cached"]
    if not staged:
        args += ["--others", "--exclude-standard"]
    for raw in sorted(set(git(root, *args).split(b"\0")) - {b""}):
        name = raw.decode("utf-8")
        path = root / name
        if staged:
            data = git(root, "show", ":" + name)
        elif path.is_symlink():
            data = str(path.readlink()).encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        inspect(name, data, findings)


def scan_archive(path, findings):
    """独立检查发布包内文件名与内容 / Check filenames and contents inside release archives."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                inspect(str(path.name) + ":" + name, archive.read(name), findings)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                stream = archive.extractfile(member) if member.isfile() else None
                inspect(
                    str(path.name) + ":" + member.name,
                    stream.read() if stream else b"",
                    findings,
                )
    else:
        raise ValueError("Unsupported release archive / 不支持的发布归档")


def scan_history(root, revision, findings):
    """检查新增历史对象，阻止旧克隆带回残留 / Scan introduced objects to prevent old-clone contamination."""
    objects = git(root, "rev-list", "--objects", revision).splitlines()
    with subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as process:
        try:
            for entry in objects:
                sha, _, path = entry.partition(b" ")
                process.stdin.write(sha + b"\n")
                process.stdin.flush()
                header = process.stdout.readline().split()
                data = process.stdout.read(int(header[2]))
                process.stdout.read(1)
                if header[1] in {b"blob", b"commit", b"tag"}:
                    label = "history " + sha.decode()
                    if path:
                        label += ":" + path.decode("utf-8", errors="replace")
                    inspect(label, data, findings)
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError("Cannot inspect history / 无法检查历史")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--message-file", type=Path)
    parser.add_argument("--commit-range")
    parser.add_argument("--event-file", type=Path)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    root = Path(git(args.repo, "rev-parse", "--show-toplevel").decode().strip())
    findings = []
    scan_repository(root, args.staged, findings)
    for ref in (
        git(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags")
        .decode()
        .splitlines()
    ):
        inspect("ref name", ref.encode(), findings)
    if args.message_file:
        inspect("candidate commit message", args.message_file.read_bytes(), findings)
    if args.commit_range:
        scan_history(root, args.commit_range, findings)
    if args.event_file:
        event = json.loads(args.event_file.read_text())
        pr = event.get("pull_request", {})
        metadata = [
            pr.get("title", ""),
            pr.get("body") or "",
            pr.get("head", {}).get("ref", ""),
        ]
        inspect("pull request metadata", "\n".join(metadata).encode(), findings)
    for path in args.artifact:
        scan_archive(path, findings)
    if findings:
        print("Project independence check failed / 项目独立性检查失败:")
        print("\n".join("- " + label for label in sorted(set(findings))))
        return 1
    print("Project independence check passed / 项目独立性检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
