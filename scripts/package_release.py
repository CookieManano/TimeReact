"""Build a source archive from the allowed project files."""

import argparse
import hashlib
import tomllib
import zipfile
from pathlib import Path

ROOT_FILES = {"README.md", "pyproject.toml", "plugin.json", "mcp.json", "requirements-lock.txt", ".gitignore", "LICENSE"}
SOURCE_DIRS = {"src", "scripts", "skills", "tests", "examples", ".github"}
SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".yaml", ".yml"}


def source_files(root: Path) -> list[Path]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink():
            continue
        if len(relative.parts) == 1:
            allowed = path.name in ROOT_FILES
        else:
            allowed = relative.parts[0] in SOURCE_DIRS and path.suffix in SUFFIXES
        if allowed and "__pycache__" not in relative.parts and not path.name.startswith(".env"):
            result.append(path)
    return result


def package(root: Path, output: Path) -> Path:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    name = f"TimeReact-v{version}"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{name}-source.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in source_files(root):
            info = zipfile.ZipInfo(f"{name}/{path.relative_to(root).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="打包 GitHub 源码，排除环境、聊天数据库和本机生成的配置")
    parser.add_argument("--output", type=Path, default=root / "dist")
    args = parser.parse_args()
    print(package(root, args.output.expanduser().resolve()))


if __name__ == "__main__":
    main()
