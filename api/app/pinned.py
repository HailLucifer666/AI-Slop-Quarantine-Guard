"""Exact dependency pins for the ecosystems beyond pypi / npm / crates.

SQG004 can only ask OSV "is this known-vulnerable?" about an *exact* version. Until
now the Guard could read exact versions out of five files (requirements.txt,
package.json and three lockfiles), so a Go, Java, Ruby, PHP or .NET repository got a
vulnerability count of zero — not because it was clean, but because nothing was read.
``coverage._UNSUPPORTED_MANIFESTS`` at least made that visible; this module closes it.

Every parser answers one question — *which (name, version) pairs does this file pin?* —
and reports what it could **not** answer alongside the answer. ``ManifestPins.unresolved``
counts dependencies that are genuinely declared but whose installed version is not
determinable from this file alone:

* a Gradle version catalog reference (``implementation(libs.okhttp)``),
* a Maven ``${property}`` with no matching ``<properties>`` entry,
* a NuGet version range (``[13.0.1, )``) or MSBuild variable (``$(JsonVersion)``),
* a Bundler ``GIT``/``PATH`` gem, whose version is a commit, not a release.

That count is what lets the coverage report say `partial` instead of implying the whole
file was understood. Guessing at any of these would put a version we invented in front
of OSV and print the answer as fact, which is the one thing the product forbids.

Names use each ecosystem's OSV spelling — ``groupId:artifactId`` for Maven,
``vendor/package`` for Packagist, the full module path for Go — because that string is
the query key, and a near-miss returns a confident, wrong "no known vulnerabilities".
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# A pinned dependency: (name, exact version).
Pin = Tuple[str, str]


@dataclass
class ManifestPins:
    """What one manifest or lockfile pinned, and how much of it we could not resolve."""

    pins: List[Pin] = field(default_factory=list)
    unresolved: int = 0


def _strip_v(version: str) -> str:
    """Drop a leading ``v`` from a tag-style version (``v1.2.3`` → ``1.2.3``).

    Go and Composer both publish tags this way while OSV indexes the bare version, so
    the prefix has to go or every query misses. Only stripped when a digit follows, so
    a legitimately ``v``-initial version string is left alone.
    """
    if len(version) > 1 and version[0] == "v" and version[1].isdigit():
        return version[1:]
    return version


# --- Go ---------------------------------------------------------------------------

# A require entry: module path, then the version. Handles both the block form and the
# single-line `require mod v1.2.3` form; the trailing `// indirect` comment is ignored
# because an indirect dependency is still installed and still exploitable.
_GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([a-zA-Z0-9][^\s()]*\.[^\s()]*/?\S*)\s+(v\S+)")
_GO_REPLACE = re.compile(r"^\s*(?:replace\s+)?(\S+)(?:\s+\S+)?\s+=>\s+(\S+)")


def parse_go_mod(content: str) -> ManifestPins:
    """Pins from a go.mod. Modules redirected by ``replace`` are counted unresolved.

    A ``replace`` directive means the version written in ``require`` is not what gets
    built — the local path or forked module is. Reporting the required version's
    advisories would describe code that is not in the binary.
    """
    result = ManifestPins()
    replaced: set = set()
    in_require = False
    in_replace = False

    for raw in content.splitlines():
        line = raw.split("//", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("require") and stripped.endswith("("):
            in_require = True
            continue
        if stripped.startswith("replace") and stripped.endswith("("):
            in_replace = True
            continue
        if stripped == ")":
            in_require = in_replace = False
            continue

        if in_replace or stripped.startswith("replace "):
            m = _GO_REPLACE.match(stripped)
            if m:
                replaced.add(m.group(1))
            continue
        if stripped.startswith(("module ", "go ", "exclude ", "retract ", "toolchain ")):
            continue

        if in_require or stripped.startswith("require "):
            m = _GO_REQUIRE.match(stripped)
            if m:
                result.pins.append((m.group(1), _strip_v(m.group(2))))

    if replaced:
        kept = [(name, version) for name, version in result.pins if name not in replaced]
        result.unresolved += len(result.pins) - len(kept)
        result.pins = kept
    return result


# --- Maven (pom.xml / build.gradle) ------------------------------------------------

_PROPERTY_REF = re.compile(r"^\$\{([^}]+)\}$")


def _localname(tag: str) -> str:
    """Element name without its XML namespace (``{http://…}version`` → ``version``)."""
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> Optional[str]:
    for child in element:
        if _localname(child.tag) == name:
            text = (child.text or "").strip()
            return text or None
    return None


def parse_pom_xml(content: str) -> ManifestPins:
    """Pins from a Maven POM, including ``<dependencyManagement>`` and profiles.

    ``${property}`` versions are resolved against this POM's own ``<properties>`` block
    (plus ``${project.version}``). A property defined in a *parent* POM cannot be
    resolved from this file, so it is counted unresolved rather than guessed at —
    inheritance is exactly where a wrong version would look most plausible.
    """
    result = ManifestPins()
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return result

    properties: Dict[str, str] = {}
    project_version = _child_text(root, "version")
    for child in root:
        if _localname(child.tag) != "properties":
            continue
        for prop in child:
            properties[_localname(prop.tag)] = (prop.text or "").strip()
    if project_version:
        properties.setdefault("project.version", project_version)
        properties.setdefault("pom.version", project_version)

    for element in root.iter():
        if _localname(element.tag) != "dependency":
            continue
        group = _child_text(element, "groupId")
        artifact = _child_text(element, "artifactId")
        if not group or not artifact:
            continue
        # A system-scoped dependency is a jar on the local disk, not a published artifact.
        if _child_text(element, "scope") == "system":
            result.unresolved += 1
            continue

        version = _child_text(element, "version")
        if not version:
            result.unresolved += 1  # inherited from a parent POM or a BOM
            continue
        ref = _PROPERTY_REF.match(version)
        if ref:
            resolved = properties.get(ref.group(1))
            if not resolved or _PROPERTY_REF.match(resolved):
                result.unresolved += 1
                continue
            version = resolved
        if "$" in version or version.startswith(("[", "(")):
            result.unresolved += 1  # unresolved variable, or a Maven version range
            continue
        result.pins.append((f"{group}:{artifact}", version))
    return result


# Gradle string notation: "group:artifact:version" inside quotes, nothing else.
_GRADLE_COORD = re.compile(r"""['"]([A-Za-z0-9][\w.\-]*):([\w.\-]+):([^'"\s:]+)['"]""")
# Map notation: group: 'g', name: 'a', version: 'v' (order-independent in practice,
# but Gradle's own docs and every real build file write it in this order).
_GRADLE_MAP = re.compile(
    r"""group\s*:\s*['"]([^'"]+)['"]\s*,\s*name\s*:\s*['"]([^'"]+)['"]\s*,"""
    r"""\s*version\s*:\s*['"]([^'"]+)['"]"""
)
# A version-catalog reference (`implementation(libs.okhttp)`). The version lives in
# gradle/libs.versions.toml, which this file cannot see.
_GRADLE_CATALOG = re.compile(r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly|annotationProcessor|kapt|ksp|classpath)\s*[( ]\s*libs\.")
# Configuration names that introduce a real dependency, to avoid matching arbitrary
# colon-bearing strings elsewhere in a build script.
_GRADLE_CONFIG = re.compile(
    r"\b(?:implementation|api|compileOnly|compileOnlyApi|runtimeOnly|testImplementation"
    r"|testCompileOnly|testRuntimeOnly|androidTestImplementation|debugImplementation"
    r"|releaseImplementation|annotationProcessor|kapt|ksp|classpath|detektPlugins)\b"
)


def parse_build_gradle(content: str) -> ManifestPins:
    """Pins from a Groovy or Kotlin Gradle script — literal coordinates only.

    A Gradle build file is a program: versions routinely come from a variable, a version
    catalog, or a BOM-managed platform, none of which are readable here. Only a fully
    literal ``group:artifact:version`` on a dependency-declaration line is taken as a
    pin; everything else that is clearly a dependency is counted unresolved.
    """
    result = ManifestPins()
    for raw in content.splitlines():
        line = raw.split("//", 1)[0]
        if not _GRADLE_CONFIG.search(line):
            continue
        if _GRADLE_CATALOG.search(line):
            result.unresolved += 1
            continue

        found = False
        for group, artifact, version in _GRADLE_COORD.findall(line):
            found = True
            if "$" in version:
                result.unresolved += 1
                continue
            result.pins.append((f"{group}:{artifact}", version))
        for group, artifact, version in _GRADLE_MAP.findall(line):
            found = True
            if "$" in version:
                result.unresolved += 1
                continue
            result.pins.append((f"{group}:{artifact}", version))
        if not found and re.search(r"""['"][^'"\s]+:[^'"\s]+['"]""", line):
            # A two-part coordinate with the version supplied elsewhere (a BOM/platform).
            result.unresolved += 1
    return result


# --- NuGet ------------------------------------------------------------------------


def parse_csproj(content: str) -> ManifestPins:
    """Pins from a .csproj / .fsproj / .vbproj ``<PackageReference>`` list.

    NuGet's ``Version`` attribute may be an MSBuild variable or an interval range
    (``[13.0.1, )`` means "13.0.1 or newer"), neither of which names the version that
    restore actually installed — those come from packages.lock.json when it exists.
    """
    result = ManifestPins()
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return result

    for element in root.iter():
        if _localname(element.tag) != "PackageReference":
            continue
        name = element.get("Include") or element.get("Update")
        if not name:
            continue
        version = element.get("Version") or _child_text(element, "Version")
        if not version:
            result.unresolved += 1  # central package management (Directory.Packages.props)
            continue
        version = version.strip()
        if "$" in version or version.startswith(("[", "(")) or "*" in version:
            result.unresolved += 1
            continue
        result.pins.append((name, version))
    return result


def parse_packages_lock_json(content: str) -> ManifestPins:
    """Pins from a NuGet packages.lock.json — the restored, exact version per framework."""
    result = ManifestPins()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return result

    frameworks = data.get("dependencies")
    if not isinstance(frameworks, dict):
        return result
    for packages in frameworks.values():
        if not isinstance(packages, dict):
            continue
        for name, meta in packages.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("type") == "Project":
                continue  # a sibling project in the same solution, not a published package
            resolved = meta.get("resolved")
            if isinstance(resolved, str) and resolved:
                result.pins.append((name, resolved))
            else:
                result.unresolved += 1
    return result


# --- RubyGems ---------------------------------------------------------------------

# Under `specs:`, a resolved gem sits at exactly four spaces of indent; its own
# dependency constraints sit at six. Matching on indent is what separates the pinned
# gem ("nokogiri (1.13.9)") from a constraint on it ("nokogiri (>= 1.5.9)").
_GEMFILE_SPEC = re.compile(r"^ {4}([A-Za-z0-9][\w.\-]*) \(([^)]+)\)\s*$")

# Platform suffixes Bundler appends to a native gem's version. They are not part of the
# version RubyGems (or OSV) indexes, so they are trimmed — but only for these known
# tokens, so a prerelease like "1.2.3-alpha" is never mangled.
_GEM_PLATFORMS = (
    "x86_64", "x86", "x64", "arm64", "aarch64", "arm", "universal", "java",
    "darwin", "linux", "mingw32", "mingw", "mswin64", "mswin", "dalvik", "sparc",
)


def _gem_version(raw: str) -> Optional[str]:
    """Strip a platform suffix from a locked gem version, or None if it is a constraint."""
    version = raw.strip()
    if any(op in version for op in ("<", ">", "=", "~")):
        return None  # a dependency constraint, not a resolved version
    head, _, tail = version.partition("-")
    if tail and tail.split("-")[0].lower() in _GEM_PLATFORMS:
        return head
    return version


def parse_gemfile_lock(content: str) -> ManifestPins:
    """Pins from a Gemfile.lock ``GEM`` section.

    ``GIT``, ``PATH`` and ``PLUGIN`` sections also list specs, but those gems come from a
    commit or a directory rather than a published release — their version line does not
    identify anything RubyGems can be asked about, so they are counted unresolved.
    """
    result = ManifestPins()
    section: Optional[str] = None
    in_specs = False

    for raw in content.splitlines():
        if raw and not raw[0].isspace():
            section = raw.strip()
            in_specs = False
            continue
        if raw.strip() == "specs:":
            in_specs = True
            continue
        if not in_specs:
            continue
        m = _GEMFILE_SPEC.match(raw)
        if not m:
            continue
        version = _gem_version(m.group(2))
        if version is None:
            continue
        if section == "GEM":
            result.pins.append((m.group(1), version))
        else:
            result.unresolved += 1
    return result


# --- Packagist --------------------------------------------------------------------


def parse_composer_lock(content: str) -> ManifestPins:
    """Pins from a composer.lock (both ``packages`` and ``packages-dev``)."""
    result = ManifestPins()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return result

    for section in ("packages", "packages-dev"):
        block = data.get(section)
        if not isinstance(block, list):
            continue
        for package in block:
            if not isinstance(package, dict):
                continue
            name = package.get("name")
            version = package.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            # "dev-main" and friends pin a branch, not a release — no queryable version.
            if version.startswith("dev-") or version.endswith("-dev"):
                result.unresolved += 1
                continue
            result.pins.append((name, _strip_v(version)))
    return result


def composer_lock_licenses(content: str) -> List[Tuple[str, str]]:
    """(package, license) pairs declared inside a composer.lock.

    Composer records each resolved package's own ``license`` array in the lockfile, so
    SQG005 can cover Packagist with no network call at all — and the claim's source is
    the file in the repository rather than a registry lookup that might have changed
    since install. Packages that declare no license are omitted: absent metadata is not
    evidence of a permissive license, and silence is the fail-safe.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []

    pairs: List[Tuple[str, str]] = []
    for section in ("packages", "packages-dev"):
        block = data.get(section)
        if not isinstance(block, list):
            continue
        for package in block:
            if not isinstance(package, dict):
                continue
            name = package.get("name")
            licenses = package.get("license")
            if not isinstance(name, str):
                continue
            if isinstance(licenses, str):
                licenses = [licenses]
            if not isinstance(licenses, list):
                continue
            label = " OR ".join(str(item) for item in licenses if item)
            if label:
                pairs.append((name, label))
    return pairs
