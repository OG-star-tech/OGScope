#!/usr/bin/env python3
"""校验 wheel/sdist 的项目许可证 / Verify project licensing in wheel and sdist."""

import argparse
import tarfile
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

LICENSE_ID = "CC-BY-NC-SA-4.0"


def check_metadata(content):
    """允许新旧元数据字段，但不能互相冲突 / Accept either metadata field without conflicts."""
    metadata = BytesParser().parsebytes(content)
    values = [
        metadata[key] for key in ("License", "License-Expression") if metadata[key]
    ]
    if not values or any(value != LICENSE_ID for value in values):
        raise ValueError(f"许可证元数据不符 / Incorrect license metadata: {values}")


def check_distributions(directory, license_text):
    """两个发布格式均必须包含一致的授权 / Both distribution formats must carry matching terms."""
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError(
            "需要唯一 wheel 与 sdist / Expected exactly one wheel and one sdist"
        )
    with ZipFile(wheels[0]) as archive:
        metadata = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        licenses = [
            name
            for name in archive.namelist()
            if ".dist-info/" in name and name.endswith("/LICENSE")
        ]
        if len(metadata) != 1 or len(licenses) != 1:
            raise ValueError(
                "wheel 缺少唯一项目授权 / Missing unique wheel project license"
            )
        check_metadata(archive.read(metadata[0]))
        if archive.read(licenses[0]).decode("utf-8").strip() != license_text.strip():
            raise ValueError("wheel 授权文本不符 / Wheel license text differs")
    with tarfile.open(sources[0]) as archive:
        root = sources[0].name.removesuffix(".tar.gz")
        check_metadata(archive.extractfile(root + "/PKG-INFO").read())
        if (
            archive.extractfile(root + "/LICENSE").read().decode("utf-8").strip()
            != license_text.strip()
        ):
            raise ValueError("sdist 授权文本不符 / Sdist license text differs")


def main():
    """仅检查构建产物，不修改授权 / Inspect build artifacts without changing terms."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    license_text = (Path(__file__).resolve().parents[1] / "LICENSE").read_text(
        encoding="utf-8"
    )
    check_distributions(args.dist, license_text)


if __name__ == "__main__":
    main()
