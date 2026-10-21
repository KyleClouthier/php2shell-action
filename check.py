#!/usr/bin/env python3
"""PHP2Shell check for a repository: finds every place the project pins or runs PHP and flags versions without the fix.

Looks at: the PHP on the runner, composer.json (config.platform.php and the require constraint), Dockerfiles
(FROM php:...), .php-version / .tool-versions, and setup-php versions in GitHub workflows.
Writes GitHub annotations so problems show on the right line in pull requests. Reads only.
https://github.com/KyleClouthier/php2shell-action
"""
import json
import os
import re
import subprocess
import sys

FIXED = {"8.5": (8, 5, 12), "8.4": (8, 4, 27), "8.3": (8, 3, 36), "8.2": (8, 2, 35)}
SKIP_DIRS = {".git", "vendor", "node_modules", ".idea", ".vscode", "storage", "cache", "var"}
GH = os.environ.get("GITHUB_ACTIONS") == "true"

findings = []  # (level, file, line, message)


def ver_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def judge(version, where):
    """Return (level, message) for a version string like 8.3, 8.3.10 or 7.4."""
    t = ver_tuple(version)
    if len(t) < 2:
        return None
    branch = f"{t[0]}.{t[1]}"
    if branch in FIXED:
        fix = FIXED[branch]
        fix_s = ".".join(map(str, fix))
        if len(t) < 3:
            return ("warning", f"{where}: PHP {branch} is a floating version. Make sure it resolves to {fix_s} or newer (rebuild or re-pull).")
        if t >= fix:
            return ("ok", f"{where}: PHP {version} has the PHP2Shell fix.")
        return ("error", f"{where}: PHP {version} is missing the PHP2Shell fix. Use {fix_s} or newer.")
    if t[:2] in [(8, 1), (8, 0), (7, 4)]:
        return ("error", f"{where}: PHP {branch} is end of life and got no PHP2Shell release, only source backports. Move to 8.2.35 or newer, or use a vendor build with the backport.")
    if t[0] < 8:
        return ("error", f"{where}: PHP {branch} is end of life with no PHP2Shell fix of any kind. Move to 8.2.35 or newer.")
    return None


def add(level_msg, file=None, line=None):
    if level_msg:
        findings.append((level_msg[0], file, line, level_msg[1]))


def runtime():
    for exe in ("php",):
        try:
            out = subprocess.run([exe, "-r", "echo PHP_VERSION;"], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            continue
        if out:
            add(judge(out, "Runner PHP"))


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            yield os.path.join(dirpath, f)


def rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def line_of(text, needle):
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else None


def composer(path, root):
    try:
        text = open(path, encoding="utf-8").read()
        data = json.loads(text)
    except Exception:
        return
    r = rel(path, root)
    plat = (data.get("config") or {}).get("platform", {}).get("php")
    if plat:
        add(judge(plat, f"{r} config.platform.php"), r, line_of(text, '"php"'))
    req = (data.get("require") or {}).get("php")
    if req:
        # Lowest version the constraint allows, e.g. "^7.4|^8.0" -> 7.4, ">=8.1" -> 8.1.
        lows = [ver_tuple(m) for m in re.findall(r"(\d+\.\d+(?:\.\d+)?)", req)]
        if lows:
            low = min(lows)
            if low[:2] < (8, 2):
                findings.append(("warning", r, line_of(text, f'"{req}"') or line_of(text, '"php"'),
                                 f"{r}: require php \"{req}\" still allows PHP {low[0]}.{low[1]}, which has no PHP2Shell release. Consider requiring >=8.2."))


DOCKER_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(?:docker\.io/)?(?:library/)?php:([0-9][\w.\-]*)", re.I | re.M)


def dockerfile(path, root):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return
    r = rel(path, root)
    for m in DOCKER_FROM.finditer(text):
        tag = m.group(1)
        v = re.match(r"\d+\.\d+(?:\.\d+)?", tag)
        if v:
            add(judge(v.group(0), f"{r} FROM php:{tag}"), r, text.count("\n", 0, m.start()) + 1)


def version_files(path, root):
    name = os.path.basename(path)
    r = rel(path, root)
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return
    if name == ".php-version":
        v = text.strip().split()[0] if text.strip() else ""
        if v:
            add(judge(v, r), r, 1)
    elif name == ".tool-versions":
        for i, ln in enumerate(text.splitlines(), 1):
            parts = ln.split()
            if len(parts) >= 2 and parts[0] == "php":
                add(judge(parts[1], f"{r} php"), r, i)


SETUP_PHP = re.compile(r"php-version\s*:\s*['\"]?([0-9][0-9.]*)", re.I)
MATRIX = re.compile(r"php(?:-versions?)?\s*:\s*\[([^\]]+)\]", re.I)


def workflow(path, root):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return
    r = rel(path, root)
    for i, ln in enumerate(text.splitlines(), 1):
        m = SETUP_PHP.search(ln)
        if m:
            add(judge(m.group(1), f"{r} php-version"), r, i)
        m = MATRIX.search(ln)
        if m:
            for v in re.findall(r"\d+\.\d+(?:\.\d+)?", m.group(1)):
                res = judge(v, f"{r} matrix php {v}")
                if res and res[0] == "error":
                    # Testing old versions in CI is fine; deploying them is not. Warn instead of fail.
                    res = ("warning", res[1] + " (CI matrix: fine for testing, not for production.)")
                add(res, r, i)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    check_runtime = os.environ.get("INPUT_CHECK_RUNTIME", "true").lower() == "true"
    fail = os.environ.get("INPUT_FAIL", "true").lower() == "true"
    if check_runtime:
        runtime()
    # Every matching file anywhere in the tree is checked (monorepos and modular setups included), except vendor/ etc.
    scanned = {"composer.json": [], "Dockerfile": [], "version file": [], "workflow": []}
    for p in walk(root):
        name = os.path.basename(p)
        rp = rel(p, root)
        if name == "composer.json":
            composer(p, root)
            scanned["composer.json"].append(rp)
        elif name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile") or name.lower() == "containerfile":
            dockerfile(p, root)
            scanned["Dockerfile"].append(rp)
        elif name in (".php-version", ".tool-versions"):
            version_files(p, root)
            scanned["version file"].append(rp)
        elif rp.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
            workflow(p, root)
            scanned["workflow"].append(rp)

    errors = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] == "warning"]
    oks = [f for f in findings if f[0] == "ok"]
    print(f"PHP2Shell check: {len(errors)} to fix, {len(warns)} to review, {len(oks)} fixed.")
    print("Scanned " + ", ".join(f"{len(v)} {k}{'' if k.endswith('json') or len(v) == 1 else 's'}" for k, v in scanned.items()) + " (vendor/ and node_modules/ skipped).")
    for k, v in scanned.items():
        if len(v) > 1 or (k == "composer.json" and v):
            print(f"  {k}: " + ", ".join(v[:20]) + (" ..." if len(v) > 20 else ""))
    for level, file, line, msg in findings:
        if GH and level in ("error", "warning"):
            props = f"file={file},line={line or 1},title=PHP2Shell" if file else "title=PHP2Shell"
            print(f"::{level} {props}::{msg}")
        else:
            print(f"  [{level.upper():7}] {msg}")
    if not findings:
        print("  No PHP versions found in this repository or on the runner.")
    print("Fixed releases: 8.5.12, 8.4.27, 8.3.36, 8.2.35. Check a live site from the browser: https://simgen.dev/php-patch-check")

    status = "action-needed" if errors else ("review" if warns else "ok")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"status={status}\nerrors={len(errors)}\nwarnings={len(warns)}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## PHP2Shell check\n\n| | Where | Finding |\n|---|---|---|\n")
            for level, file, line, msg in findings:
                icon = {"error": "🔴", "warning": "🟡", "ok": "🟢"}[level]
                fh.write(f"| {icon} | {file or 'runner'}{':' + str(line) if line else ''} | {msg} |\n")
            if not findings:
                fh.write("| | | No PHP versions found. |\n")
            fh.write("\nFixed releases: 8.5.12, 8.4.27, 8.3.36, 8.2.35. Check a live site: https://simgen.dev/php-patch-check\n")
    sys.exit(1 if errors and fail else 0)


if __name__ == "__main__":
    main()
