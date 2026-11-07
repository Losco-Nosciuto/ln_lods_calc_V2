# build_zip.py
# LN LODs — Free Edition release builder.
#
# Builds a CLEAN zip using an explicit allowlist, so development leftovers
# (ln_debug.py, .git/, previous zips, editor files) can never leak into a
# release again. It also refuses to build if the Free sources reference a
# Pro-only module or if the requested version does not match bl_info.

import ast
import hashlib
import os
import re
import sys
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Files that make up the Free add-on. Nothing else is shipped.
INCLUDE = (
    "__init__.py",
    "ReadMe.txt",
    "ln_lod_calculator.py",
    "ln_lod_screen.py",
    "ln_ui.py",
    "ln_vertex_count.py",
)

# Modules that only exist in the Pro edition. The Free build must never
# reference them, otherwise it would break for Free users.
PRO_ONLY = ("ln_pro_extras", "ln_lod_viewer", "ln_testing_state")

# Stable add-on folder name inside the archive. Keeping it constant across
# releases lets Blender replace the previous install instead of creating a
# second, conflicting copy of the add-on.
MODULE_FOLDER = "LN_LODs_FREE"

VERSION_PATTERN = re.compile(r'"version"\s*:\s*\((\d+),\s*(\d+),\s*(\d+)\)')
NAME_PATTERN = re.compile(r'"name"\s*:\s*"([^"]+)"')


def _read(name):
    with open(os.path.join(BASE_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def declared_version():
    match = VERSION_PATTERN.search(_read("__init__.py"))
    if not match:
        return None
    return ".".join(match.groups())


def check_sources():
    problems = []
    for name in INCLUDE:
        if not os.path.isfile(os.path.join(BASE_DIR, name)):
            problems.append(f"missing file: {name}")

    for name in INCLUDE:
        if not name.endswith(".py"):
            continue
        tree = ast.parse(_read(name), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in PRO_ONLY:
                    problems.append(f"{name} imports Pro-only module '{module}'")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in PRO_ONLY:
                        problems.append(f"{name} imports Pro-only module '{module}'")

    match = NAME_PATTERN.search(_read("__init__.py"))
    if not match or match.group(1) != "LN LODs":
        found = match.group(1) if match else "missing"
        problems.append(f"bl_info name should be 'LN LODs', found '{found}'")

    return problems


def main():
    problems = check_sources()
    if problems:
        print("Build aborted:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    version = declared_version()
    if not version:
        print("Build aborted: could not read bl_info['version'] from __init__.py")
        sys.exit(1)

    answer = (sys.argv[1] if len(sys.argv) > 1 else input(f"Version [{version}]: ")).strip()
    answer = answer.strip("\"'")
    answer = answer or version
    if answer != version:
        print(f"Build aborted: __init__.py declares {version}, but you asked for {answer}.")
        print("Update bl_info['version'] first, then build again.")
        sys.exit(1)

    zip_name = f"LN_LODs_FREE_{version.replace('.', '_')}"
    zip_path = os.path.join(BASE_DIR, f"{zip_name}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in INCLUDE:
            archive.write(
                os.path.join(BASE_DIR, filename),
                arcname=f"{MODULE_FOLDER}/{filename}",
            )

    with open(zip_path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()

    print(f"Created {zip_path}")
    print(f"Add-on folder inside the archive: {MODULE_FOLDER}/")
    print(f"Files: {len(INCLUDE)}")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
