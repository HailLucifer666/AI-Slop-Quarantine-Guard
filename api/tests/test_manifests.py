"""Test manifest parsers: real names extracted, local/git/url refs filtered out."""

from app.manifests import (
    extract_dependency_names,
    extract_pinned_lockfile,
    lockfile_ecosystem,
    manifest_ecosystem,
    parse_cargo_toml,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
)


def test_ecosystem_mapping():
    assert manifest_ecosystem("requirements.txt") == "pypi"
    assert manifest_ecosystem("a/b/pyproject.toml") == "pypi"
    assert manifest_ecosystem("package.json") == "npm"
    assert manifest_ecosystem("Cargo.toml") == "crates"
    assert manifest_ecosystem("package-lock.json") is None  # lockfiles ignored
    assert manifest_ecosystem("README.md") is None


def test_requirements_basic_and_filters():
    content = (
        "requests==2.31.0\n"
        "Flask>=2.0  # web\n"
        "\n"
        "# a comment\n"
        "-r other.txt\n"
        "-e .\n"
        "git+https://github.com/x/y.git\n"
        "./local-pkg\n"
        "quantumllm-helper==9.9.9\n"
    )
    names = parse_requirements_txt(content)
    assert names == ["requests", "Flask", "quantumllm-helper"]


def test_pyproject_pep621_and_poetry():
    content = """
[project]
dependencies = ["httpx>=0.25", "fastapi"]

[tool.poetry.dependencies]
python = "^3.12"
pydantic = "^2.5"
mylocal = { path = "../mylocal" }
fromgit = { git = "https://example.com/x.git" }
"""
    names = parse_pyproject_toml(content)
    assert "httpx" in names and "fastapi" in names and "pydantic" in names
    assert "python" not in names
    assert "mylocal" not in names and "fromgit" not in names


def test_package_json_sections_and_filters():
    content = """
{
  "dependencies": {"left-pad": "^1.0.0", "@scope/pkg": "1.2.3", "local": "file:../local"},
  "devDependencies": {"jest": "^29"},
  "scripts": {"build": "tsc"}
}
"""
    deps = parse_package_json(content)
    assert set(deps) == {"left-pad", "@scope/pkg", "jest"}  # 'local' filtered, scripts ignored


def test_cargo_sections_and_filters():
    content = """
[dependencies]
serde = "1.0"
local = { path = "../local" }
remote = { git = "https://example.com/x" }
tokio = { version = "1", features = ["full"] }

[dev-dependencies]
criterion = "0.5"
"""
    deps = parse_cargo_toml(content)
    assert set(deps) == {"serde", "tokio", "criterion"}


def test_extract_dispatch():
    assert extract_dependency_names("requirements.txt", "requests==2\n") == ["requests"]
    assert extract_dependency_names("unknown.txt", "x") == []


# --- Lockfiles (Sprint B): pinned (name, version) for the vuln scanner -------

def test_lockfile_ecosystem_mapping():
    assert lockfile_ecosystem("package-lock.json") == "npm"
    assert lockfile_ecosystem("a/b/yarn.lock") == "npm"
    assert lockfile_ecosystem("poetry.lock") == "pypi"
    assert lockfile_ecosystem("Cargo.lock") == "crates"
    assert lockfile_ecosystem("go.sum") == "go"
    assert lockfile_ecosystem("requirements.txt") is None  # a manifest, not a lockfile


def test_lockfiles_stay_out_of_the_manifest_channel():
    # SQG001/SQG005 must never see lockfiles (private-pkg false-CERTAIN guard).
    assert manifest_ecosystem("poetry.lock") is None
    assert extract_dependency_names("poetry.lock", "[[package]]\nname='x'\n") == []


def test_parse_poetry_lock():
    content = """
[[package]]
name = "requests"
version = "2.31.0"

[[package]]
name = "urllib3"
version = "2.0.7"
"""
    assert extract_pinned_lockfile("poetry.lock", content) == [
        ("requests", "2.31.0"),
        ("urllib3", "2.0.7"),
    ]


def test_parse_cargo_lock():
    content = """
[[package]]
name = "serde"
version = "1.0.193"

[[package]]
name = "tokio"
version = "1.35.0"
"""
    assert extract_pinned_lockfile("Cargo.lock", content) == [
        ("serde", "1.0.193"),
        ("tokio", "1.35.0"),
    ]


def test_parse_package_lock_v3():
    content = """
{
  "lockfileVersion": 3,
  "packages": {
    "": {"name": "root", "version": "1.0.0"},
    "node_modules/lodash": {"version": "4.17.21"},
    "node_modules/@scope/pkg": {"version": "2.3.4"},
    "node_modules/a/node_modules/b": {"version": "0.1.0"}
  }
}
"""
    pins = extract_pinned_lockfile("package-lock.json", content)
    assert ("lodash", "4.17.21") in pins
    assert ("@scope/pkg", "2.3.4") in pins
    assert ("b", "0.1.0") in pins        # nested transitive, name from last segment
    assert all(name != "root" for name, _ in pins)  # the "" root entry is skipped


def test_parse_package_lock_v1():
    content = """
{
  "lockfileVersion": 1,
  "dependencies": {
    "lodash": {"version": "4.17.4"},
    "express": {"version": "4.18.2", "dependencies": {
      "accepts": {"version": "1.3.8"}
    }}
  }
}
"""
    pins = extract_pinned_lockfile("package-lock.json", content)
    assert ("lodash", "4.17.4") in pins
    assert ("express", "4.18.2") in pins
    assert ("accepts", "1.3.8") in pins  # nested dependency walked


def test_parse_yarn_lock_classic_and_scoped():
    content = '''\
# yarn lockfile v1
"@babel/core@^7.0.0", "@babel/core@^7.1.0":
  version "7.1.0"
  resolved "https://registry.yarnpkg.com/@babel/core/-/core-7.1.0.tgz"

lodash@^4.17.4:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz"
'''
    pins = extract_pinned_lockfile("yarn.lock", content)
    assert ("@babel/core", "7.1.0") in pins
    assert ("lodash", "4.17.21") in pins


def test_parse_yarn_lock_berry_skips_metadata():
    content = '''\
__metadata:
  version: 6
  cacheKey: 8

"lodash@npm:^4.17.4":
  version: 4.17.21
  resolution: "lodash@npm:4.17.21"
'''
    pins = extract_pinned_lockfile("yarn.lock", content)
    assert ("lodash", "4.17.21") in pins
    assert all(name != "__metadata" for name, _ in pins)


def test_parse_go_sum_dedupes_and_strips_v():
    content = (
        "github.com/foo/bar v1.2.3 h1:abc=\n"
        "github.com/foo/bar v1.2.3/go.mod h1:def=\n"
        "golang.org/x/net v0.17.0 h1:ghi=\n"
    )
    pins = extract_pinned_lockfile("go.sum", content)
    assert pins == [
        ("github.com/foo/bar", "1.2.3"),  # the /go.mod duplicate line collapsed
        ("golang.org/x/net", "0.17.0"),
    ]


def test_malformed_lockfile_is_silent():
    # Can't parse → empty, never a guess (protects the zero-FP bar).
    assert extract_pinned_lockfile("package-lock.json", "{ not json") == []
    assert extract_pinned_lockfile("Cargo.lock", "= = =") == []
    assert extract_pinned_lockfile("unknown.lock", "whatever") == []
