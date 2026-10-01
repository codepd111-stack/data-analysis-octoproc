import re
from importlib.metadata import PackageNotFoundError, version

lines = []
with open("requirements.txt", encoding="utf-8") as f:
    for raw in f:
        spec = raw.strip()
        if not spec or spec.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?", spec)
        pkg, extras = match.group(1), match.group(2) or ""
        try:
            lines.append(f"{pkg}{extras}=={version(pkg)}")
        except PackageNotFoundError:
            lines.append(spec)
            print("Not installed, left unpinned:", spec)

with open("requirements.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))