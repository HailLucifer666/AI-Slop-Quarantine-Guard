"""Parse dependency manifests into the set of declared package names (Phase 3, SQG001).

Real parsers (stdlib ``tomllib`` + ``json``). Each returns only the *names* of
declared dependencies, with local / git / url / workspace references already
filtered out — those can never be checked against a public registry and flagging
them would be a false positive.
"""

import json
import re
import tomllib
from typing import Dict, List, Tuple

# Map a manifest basename to the ecosystem whose registry should answer for it.
MANIFEST_ECOSYSTEM: Dict[str, str] = {
    "requirements.txt": "pypi",
    "pyproject.toml": "pypi",
    "package.json": "npm",
    "Cargo.toml": "crates",
}

# A version spec that points at a local path, VCS, or URL — never registry-checkable.
_NON_REGISTRY_PREFIXES = (
    "file:", "link:", "workspace:", "portal:", "git+", "git:", "github:",
    "http:", "https:", "/", "./", "../",
)

# PEP 508 / requirements name token (stops at the first version/marker char).
_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def manifest_ecosystem(filename: str) -> str | None:
    """Return the registry ecosystem for a manifest path, or None if unsupported."""
    base = filename.rsplit("/", 1)[-1]
    return MANIFEST_ECOSYSTEM.get(base)


def _is_non_registry(spec: str) -> bool:
    spec = spec.strip().strip('"').strip("'")
    return any(spec.startswith(p) for p in _NON_REGISTRY_PREFIXES)


def parse_requirements_txt(content: str) -> List[str]:
    """Extract package names from a requirements.txt (skips options, comments, VCS/url refs)."""
    names: List[str] = []
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-") or _is_non_registry(line) or "/" in line:
            continue
        m = _NAME_RE.match(line)
        if m:
            names.append(m.group(1))
    return names


def parse_pyproject_toml(content: str) -> List[str]:
    """Extract package names from [project].dependencies and [tool.poetry.dependencies]."""
    data = tomllib.loads(content)
    names: List[str] = []

    for dep in data.get("project", {}).get("dependencies", []):
        if isinstance(dep, str) and not _is_non_registry(dep):
            m = _NAME_RE.match(dep.strip())
            if m:
                names.append(m.group(1))

    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        # Table specs with path/git/url keys are local/VCS → not registry-checkable.
        if isinstance(spec, dict) and any(k in spec for k in ("path", "git", "url")):
            continue
        names.append(name)

    return names


def parse_package_json(content: str) -> Dict[str, str]:
    """Extract {name: version} across all dependency sections of a package.json."""
    data = json.loads(content)
    sections = (
        "dependencies", "devDependencies",
        "optionalDependencies", "peerDependencies",
    )
    deps: Dict[str, str] = {}
    for section in sections:
        block = data.get(section)
        if isinstance(block, dict):
            for name, version in block.items():
                if isinstance(version, str) and not _is_non_registry(version):
                    deps[name] = version
    return deps


def parse_cargo_toml(content: str) -> Dict[str, str]:
    """Extract {crate: version} from Cargo dependency tables (skips path/git deps)."""
    data = tomllib.loads(content)
    deps: Dict[str, str] = {}
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        block = data.get(section, {})
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if isinstance(spec, dict):
                if any(k in spec for k in ("path", "git")):
                    continue
                deps[name] = str(spec.get("version", ""))
            else:
                deps[name] = str(spec)
    return deps


def extract_dependency_names(filename: str, content: str) -> List[str]:
    """Dispatch to the right parser by filename; return registry-checkable names."""
    base = filename.rsplit("/", 1)[-1]
    if base == "requirements.txt":
        return parse_requirements_txt(content)
    if base == "pyproject.toml":
        return parse_pyproject_toml(content)
    if base == "package.json":
        return list(parse_package_json(content).keys())
    if base == "Cargo.toml":
        return list(parse_cargo_toml(content).keys())
    return []


# --- Lockfiles (Sprint B) ---------------------------------------------------
# Lockfiles pin the *fully resolved* dependency tree (transitive included) to
# exact versions. That makes them ideal for the vulnerability scanner (SQG004),
# which needs an exact version to ask OSV "is this known-vulnerable?".
#
# They are deliberately kept OUT of MANIFEST_ECOSYSTEM / extract_dependency_names.
# Those drive SQG001 (existence) and SQG005 (license), and a lockfile routinely
# names private-registry packages by their exact name. Existence-checking those
# against the *public* registry would emit a false "does not exist" CERTAIN block
# on a package that genuinely exists privately — the one thing the product promise
# forbids. So lockfiles are a separate, advisory-only channel consumed by vulns.py.

LOCKFILE_ECOSYSTEM: Dict[str, str] = {
    "package-lock.json": "npm",
    "yarn.lock": "npm",
    "poetry.lock": "pypi",
    "Cargo.lock": "crates",
    "go.sum": "go",
}

# yarn.lock resolved version line — classic v1 (`version "1.2.3"`) and berry
# (`version: 1.2.3`).
_YARN_VERSION_RE = re.compile(r'^\s+version[:\s]+"?([^"\s]+)"?\s*$')


def lockfile_ecosystem(filename: str) -> str | None:
    """Return the ecosystem for a lockfile path, or None if it is not a lockfile."""
    base = filename.rsplit("/", 1)[-1]
    return LOCKFILE_ECOSYSTEM.get(base)


def _parse_toml_packages(content: str) -> List[Tuple[str, str]]:
    """Read the ``[[package]]`` array shared by poetry.lock and Cargo.lock."""
    data = tomllib.loads(content)
    pins: List[Tuple[str, str]] = []
    for pkg in data.get("package", []):
        name = pkg.get("name")
        version = pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            pins.append((name, version))
    return pins


def _walk_npm_v1(deps: dict, pins: List[Tuple[str, str]]) -> None:
    """Recurse the nested ``dependencies`` tree of a v1 package-lock.json."""
    for name, meta in deps.items():
        if not isinstance(meta, dict):
            continue
        version = meta.get("version")
        if isinstance(version, str):
            pins.append((name, version))
        nested = meta.get("dependencies")
        if isinstance(nested, dict):
            _walk_npm_v1(nested, pins)


def parse_package_lock_json(content: str) -> List[Tuple[str, str]]:
    """Extract pinned (name, version) from package-lock.json (v1, v2 and v3)."""
    data = json.loads(content)
    pins: List[Tuple[str, str]] = []
    packages = data.get("packages")
    if isinstance(packages, dict):  # lockfileVersion 2 / 3
        for key, meta in packages.items():
            if not key or not isinstance(meta, dict):
                continue  # "" is the root project itself
            version = meta.get("version")
            if not isinstance(version, str):
                continue
            name = key.split("node_modules/")[-1]
            if name:
                pins.append((name, version))
        return pins
    deps = data.get("dependencies")  # lockfileVersion 1
    if isinstance(deps, dict):
        _walk_npm_v1(deps, pins)
    return pins


def _yarn_name(spec: str) -> str:
    """Derive a package name from a yarn descriptor like ``@babel/core@^7.0.0``."""
    spec = spec.strip().strip('"')
    # Scoped names start with '@'; the separator '@' is the *second* one.
    at = spec.find("@", 1) if spec.startswith("@") else spec.find("@")
    return spec[:at] if at > 0 else spec


def parse_yarn_lock(content: str) -> List[Tuple[str, str]]:
    """Extract pinned (name, version) from a yarn.lock (classic v1 + berry)."""
    pins: List[Tuple[str, str]] = []
    current: str | None = None
    for line in content.splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            header = line.rstrip(":").strip()
            current = _yarn_name(header.split(",")[0])
            continue
        m = _YARN_VERSION_RE.match(line)
        if m and current and current != "__metadata":
            pins.append((current, m.group(1)))
            current = None
    return pins


def parse_go_sum(content: str) -> List[Tuple[str, str]]:
    """Extract pinned (module, version) from a go.sum (deduped, ``v`` prefix stripped)."""
    pins: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for line in content.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        module, version = parts[0], parts[1]
        version = version.split("/", 1)[0]  # drop the "/go.mod" suffix line
        if version.startswith("v"):
            version = version[1:]  # OSV "Go" versions carry no leading 'v'
        key = (module, version)
        if key in seen:
            continue
        seen.add(key)
        pins.append((module, version))
    return pins


def extract_pinned_lockfile(filename: str, content: str) -> List[Tuple[str, str]]:
    """Dispatch to the right lockfile parser; return pinned (name, version) pairs.

    A malformed lockfile yields ``[]`` (stay silent — never guess), preserving the
    zero-false-positive bar the analyzers rely on.
    """
    base = filename.rsplit("/", 1)[-1]
    try:
        if base in ("poetry.lock", "Cargo.lock"):
            return _parse_toml_packages(content)
        if base == "package-lock.json":
            return parse_package_lock_json(content)
        if base == "yarn.lock":
            return parse_yarn_lock(content)
        if base == "go.sum":
            return parse_go_sum(content)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError, AttributeError):
        return []
    return []
