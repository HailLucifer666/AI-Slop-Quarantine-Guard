"""Parse dependency manifests into the set of declared package names (Phase 3, SQG001).

Real parsers (stdlib ``tomllib`` + ``json``). Each returns only the *names* of
declared dependencies, with local / git / url / workspace references already
filtered out — those can never be checked against a public registry and flagging
them would be a false positive.
"""

import json
import re
import tomllib
from typing import Callable, Dict, List, Optional, Tuple

from app.pinned import (
    ManifestPins,
    parse_build_gradle,
    parse_composer_lock,
    parse_csproj,
    parse_gemfile_lock,
    parse_go_mod,
    parse_packages_lock_json,
    parse_pom_xml,
)
from app.analyzers.paths import in_test_path  # noqa: E402 — shared classifier; paths imports nothing, no cycle
from app.registries import normalize_pypi

# Map a manifest basename to the ecosystem whose registry should answer for it.
#
# This map drives SQG001 (existence) and SQG005 (license), both of which query a public
# registry by name. A basename only belongs here once `registries._registry_url` and
# `licenses._SUPPORTED` can actually answer for that ecosystem — otherwise SQG001 reports
# every dependency as "registry unreachable", which is a false statement about why we
# don't know. Ecosystems we can read *versions* from but not yet query by name live in
# VERSIONED_MANIFEST_ECOSYSTEM below.
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
    if " @ " in spec:  # PEP 508 direct reference, e.g. "name @ https://..." — never a registry lookup
        return True
    return any(spec.startswith(p) for p in _NON_REGISTRY_PREFIXES)


# A `scheme:` prefix on a version spec. Plain ranges and dist-tags ("^1.2.3", "latest",
# "*") have none. `npm:` is the one scheme that still names a registry package — under
# a different local name — so it is resolved rather than skipped.
_SPEC_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):", re.IGNORECASE)
# `npm:<target>[@<range>]`, where <target> may be scoped (`@scope/name`).
_NPM_ALIAS_SPEC = re.compile(r"^npm:((?:@[^/@]+/)?[^@]+)(?:@.+)?$", re.IGNORECASE)


def _registry_name(name: str, spec: str) -> Optional[str]:
    """The package name a registry can answer about, or None when we cannot know it.

    Scan #38 (firecrawl, 2026-11-27): `"typescript-7": "npm:typescript@7.0.2"` was
    reported as `Package 'typescript-7' does not exist in npm (404)` — CERTAIN and
    block-eligible — because the local alias *label* was sent to the registry as if it
    were a package name. An `npm:` alias installs the target package under a different
    local name, so the label 404s by design; asking about it invents a hallucinated
    dependency out of a legitimate alias, and the gate would block the PR. Resolving to
    the target fixes typosquat too (SQG007 reads the same name set): a look-alike alias
    *target* is still caught, while a look-alike alias *label* is not a package at all.

    Any other `scheme:` spec reaching here is one we cannot interpret — the
    file:/git:/workspace:/portal:/url forms are filtered before this. Returning the key
    would turn "I do not understand this spec" into "this package does not exist", the
    same confident false claim in a different dress (gate E, kee class 4d). Hence None:
    an unreadable spec produces no claim, never a guess.
    """
    m = _SPEC_SCHEME.match(spec)
    if m is None:
        return name
    if m.group(1).lower() == "npm":
        alias = _NPM_ALIAS_SPEC.match(spec)
        return alias.group(1) if alias else None
    return None


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
                if not isinstance(version, str) or _is_non_registry(version):
                    continue
                registry_name = _registry_name(name, version)
                if registry_name is None:
                    continue  # a spec form we cannot resolve — never guess a name
                deps[registry_name] = version
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


# pip directive that declares a non-public package index. Lives as its own line
# in requirements.txt (`--extra-index-url https://...` / `--index-url https://...`
# / their `-i`/`-e` short forms — note `-e` here is pip's *editable install* flag,
# unrelated to `--extra-index-url`'s short form `-i`). A hit means SOME dependency
# in this specific file may resolve from a private index the public registry has
# never heard of — existence-checking against the public registry alone would
# false-block a real package, so callers downgrade MISSING to advisory for this
# file rather than treating it as a proven fact.
_PIP_INDEX_DIRECTIVE = re.compile(r"^\s*(?:--extra-index-url|--index-url|-i)\b", re.IGNORECASE)


def has_pip_extra_index(content: str) -> bool:
    """True if a requirements.txt declares a custom package index."""
    return any(_PIP_INDEX_DIRECTIVE.match(line) for line in content.splitlines())


# .npmrc scope→registry override, e.g. "@myorg:registry=https://npm.myorg.com".
# Declaring this tells npm that names under "@myorg/*" resolve from that registry,
# not the public one — the same false-block risk as the pip case above, but
# precisely scoped to the declared scope(s) rather than the whole ecosystem.
_NPMRC_SCOPE_RE = re.compile(r"^\s*(@[a-z0-9][a-z0-9._-]*):registry\s*=", re.IGNORECASE | re.MULTILINE)


def npmrc_private_scopes(content: str) -> set[str]:
    """Scopes (e.g. {"@myorg"}) an .npmrc redirects to a non-public registry."""
    return {m.group(1) for m in _NPMRC_SCOPE_RE.finditer(content)}


def collect_workspace_names(files: Dict[str, str]) -> Dict[str, set[str]]:
    """Names this repository itself declares as packages, per ecosystem.

    Why this exists: a public-registry 404 for a name the repo declares is a
    workspace-internal package (npm workspaces / monorepo tooling), not a
    hallucinated dependency — SQG001 must never block on it (derived from the
    manifests' own ``name`` fields, never a hand-kept list).

    Returns ``{"npm": {...}, "pypi": {...}}`` — the registry answers per
    ecosystem, so the downgrade must too: an npm-declared ``helper`` says
    nothing about a PyPI package named ``helper`` (review finding, 2026-11-12).

    Manifests under test/fixture paths are skipped: a fixture package.json
    declaring an unpublished name must not legitimize a production-path 404 of
    that name — the fixture rung (the path itself) already carries that case.
    PyPI names are stored PEP 503-normalized (``normalize_pypi``), because the
    registry normalizes and both spellings of the repo's own name are common.

    Coverage is ``package.json`` → npm and ``pyproject.toml`` → pypi.
    Cargo/poetry workspaces are not collected: their internal dependencies are
    path/git references, filtered before any registry lookup, so a name set
    would never be consulted. ``workspaces``/``packages`` globs are likewise
    not parsed: a glob can only point at directories that themselves carry a
    manifest, and those manifests' names are already collected here.

    Malformed files are skipped: collection is best-effort and one broken
    manifest must not void the set (the registry check answers per-name anyway).
    Whole-repo scans pass the full ingested tree; PR mode passes only the
    manifests the diff touches, so an un-touched workspace package keeps its
    CERTAIN finding (fail-safe: absent evidence never downgrades).
    """
    declared: Dict[str, set[str]] = {}
    for path, content in files.items():
        normalized_path = path.replace("\\", "/")
        if in_test_path(normalized_path):
            continue  # fixture-declared names never legitimize a production-path 404
        base = normalized_path.rsplit("/", 1)[-1]
        if base == "package.json":
            ecosystem = "npm"
            try:
                data = json.loads(content)
            except ValueError:
                continue
            if isinstance(data, dict):
                name = data.get("name")
                if isinstance(name, str) and name.strip():
                    declared.setdefault(ecosystem, set()).add(name)
        elif base == "pyproject.toml":
            ecosystem = "pypi"
            try:
                data = tomllib.loads(content)
            except tomllib.TOMLDecodeError:
                continue
            project = data.get("project") if isinstance(data, dict) else None
            name = project.get("name") if isinstance(project, dict) else None
            if isinstance(name, str) and name.strip():
                declared.setdefault(ecosystem, set()).add(normalize_pypi(name))
    return declared


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
    "pnpm-lock.yaml": "npm",
    "bun.lock": "npm",
    "poetry.lock": "pypi",
    "uv.lock": "pypi",
    "Cargo.lock": "crates",
    "go.sum": "go",
    "Gemfile.lock": "rubygems",
    "composer.lock": "packagist",
    "packages.lock.json": "nuget",
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


def parse_pnpm_lock_yaml(content: str) -> List[Tuple[str, str]]:
    """Extract pinned (name, version) pairs from pnpm-lock.yaml (v6 and v9 formats).

    Parses the top-level ``packages:`` section without requiring PyYAML. Keys look like:
      - v9: ``  lodash@4.17.23:`` or ``  '@babel/core@7.24.0':``
      - v6: ``  /lodash@4.17.23:`` or ``  /@babel/core@7.24.0(peer@1.0.0):``
    """
    pins: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    in_packages = False
    for raw in content.splitlines():
        if not raw or raw.startswith("#"):
            continue
        if not raw[0].isspace():
            in_packages = raw.strip() == "packages:"
            continue
        if not in_packages:
            continue
        # Package keys sit at indent level 2 (two spaces) and end with ':'
        if raw.startswith("  ") and not raw.startswith("   ") and raw.rstrip().endswith(":"):
            key = raw.strip()[:-1].strip().strip("'\"")
            if key.startswith("/"):
                key = key[1:]
            # Strip peer-dependency qualifier suffix `(peer@...)` or `_peer@...`
            if "(" in key:
                key = key.split("(", 1)[0]
            at = key.rfind("@")
            if at <= 0:
                continue
            name, version = key[:at], key[at + 1 :]
            if name and version and (name, version) not in seen:
                seen.add((name, version))
                pins.append((name, version))
    return pins


def _strip_jsonc_trailing_commas(text: str) -> str:
    """Remove trailing commas before ``}`` or ``]`` in JSONC (used by ``bun.lock``)."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def parse_bun_lock(content: str) -> List[Tuple[str, str]]:
    """Extract pinned (name, version) pairs from Bun's text ``bun.lock`` (JSONC)."""
    cleaned = _strip_jsonc_trailing_commas(content)
    data = json.loads(cleaned)
    packages = data.get("packages")
    if not isinstance(packages, dict):
        return []
    pins: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for _key, entry in packages.items():
        if not isinstance(entry, list) or not entry or not isinstance(entry[0], str):
            continue
        spec = entry[0]  # e.g. "lodash@4.17.23" or "@babel/core@7.24.0"
        at = spec.rfind("@")
        if at <= 0:
            continue
        name, version = spec[:at], spec[at + 1 :]
        if name and version and (name, version) not in seen:
            seen.add((name, version))
            pins.append((name, version))
    return pins


def extract_pinned_lockfile(filename: str, content: str) -> List[Tuple[str, str]]:
    """Dispatch to the right lockfile parser; return pinned (name, version) pairs.

    A malformed lockfile yields ``[]`` (stay silent — never guess), preserving the
    zero-false-positive bar the analyzers rely on.
    """
    base = filename.rsplit("/", 1)[-1]
    try:
        if base in ("poetry.lock", "Cargo.lock", "uv.lock"):
            return _parse_toml_packages(content)
        if base == "package-lock.json":
            return parse_package_lock_json(content)
        if base == "yarn.lock":
            return parse_yarn_lock(content)
        if base == "pnpm-lock.yaml":
            return parse_pnpm_lock_yaml(content)
        if base == "bun.lock":
            return parse_bun_lock(content)
        if base == "go.sum":
            return parse_go_sum(content)
        if base in _EXTRA_LOCKFILE_PARSERS:
            return _EXTRA_LOCKFILE_PARSERS[base](content).pins
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError, AttributeError):
        return []
    return []


# --- Ecosystems we can version but not yet name-check ------------------------------
# Go, Maven, RubyGems, Packagist and NuGet manifests pin exact versions, which is all
# SQG004 needs to ask OSV whether a version is known-vulnerable. They are deliberately
# NOT in MANIFEST_ECOSYSTEM: SQG001 would then query a registry client that has no URL
# for them and report "registry unreachable" — describing a support gap as an outage.
# Parsers live in app/pinned.py; this section is only the routing table.

VERSIONED_MANIFEST_ECOSYSTEM: Dict[str, str] = {
    "go.mod": "go",
    "pom.xml": "maven",
    "build.gradle": "maven",
    "build.gradle.kts": "maven",
}

# .NET project files are named after the project, so they match on extension.
VERSIONED_MANIFEST_SUFFIXES: Dict[str, str] = {
    ".csproj": "nuget",
    ".fsproj": "nuget",
    ".vbproj": "nuget",
}

_VERSIONED_PARSERS: Dict[str, Callable[[str], ManifestPins]] = {
    "go.mod": parse_go_mod,
    "pom.xml": parse_pom_xml,
    "build.gradle": parse_build_gradle,
    "build.gradle.kts": parse_build_gradle,
}

_EXTRA_LOCKFILE_PARSERS: Dict[str, Callable[[str], ManifestPins]] = {
    "Gemfile.lock": parse_gemfile_lock,
    "composer.lock": parse_composer_lock,
    "packages.lock.json": parse_packages_lock_json,
}


def versioned_manifest_ecosystem(filename: str) -> str | None:
    """Ecosystem for a manifest we can read exact versions from, else None.

    Covers only the ecosystems absent from MANIFEST_ECOSYSTEM — callers that want "any
    file with pins" check this, `manifest_ecosystem` and `lockfile_ecosystem` in turn.
    """
    base = filename.rsplit("/", 1)[-1]
    if base in VERSIONED_MANIFEST_ECOSYSTEM:
        return VERSIONED_MANIFEST_ECOSYSTEM[base]
    dot = base.rfind(".")
    if dot > 0:
        return VERSIONED_MANIFEST_SUFFIXES.get(base[dot:].lower())
    return None


def parse_pins(filename: str, content: str) -> ManifestPins:
    """Pins plus unresolved count for any file in the newly supported ecosystems.

    Returns an empty result for anything else, including the pypi/npm/crates files whose
    pins are read elsewhere — this is the extension point, not a replacement for them.
    A parse failure yields no pins and no unresolved count: an unparseable file is a
    silence we report through coverage, never a guess.
    """
    base = filename.rsplit("/", 1)[-1]
    parser = _VERSIONED_PARSERS.get(base) or _EXTRA_LOCKFILE_PARSERS.get(base)
    if parser is None:
        dot = base.rfind(".")
        if dot > 0 and base[dot:].lower() in VERSIONED_MANIFEST_SUFFIXES:
            parser = parse_csproj
    if parser is None:
        return ManifestPins()
    try:
        return parser(content)
    except (json.JSONDecodeError, ValueError, AttributeError):
        return ManifestPins()
