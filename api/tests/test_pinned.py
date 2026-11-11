"""Parsers for the Go / Maven / RubyGems / Packagist / NuGet ecosystems (app.pinned).

Every test pairs the pins a file yields with the ``unresolved`` count, because the count
is the honesty half of the contract: a dependency we cannot version must be *reported*
as unread, not dropped. A parser that silently skipped a Gradle version catalog would
make a half-read build file look fully checked, which is the exact failure the coverage
model exists to prevent.
"""

from app.coverage import take_census
from app.manifests import (
    LOCKFILE_ECOSYSTEM,
    extract_pinned_lockfile,
    lockfile_ecosystem,
    manifest_ecosystem,
    parse_pins,
    versioned_manifest_ecosystem,
)
from app.pinned import (
    parse_build_gradle,
    parse_composer_lock,
    parse_csproj,
    parse_gemfile_lock,
    parse_go_mod,
    parse_packages_lock_json,
    parse_pom_xml,
)

# --- Go ---------------------------------------------------------------------------

GO_MOD = """module github.com/example/service

go 1.21

require (
\tgithub.com/gin-gonic/gin v1.9.1
\tgithub.com/stretchr/testify v1.8.4 // indirect
\tgolang.org/x/crypto v0.14.0
)

require github.com/spf13/cobra v1.7.0

replace github.com/gin-gonic/gin => ../vendored/gin

exclude github.com/bad/pkg v1.0.0
"""


def test_go_mod_reads_require_blocks_and_single_lines():
    result = parse_go_mod(GO_MOD)
    assert ("github.com/stretchr/testify", "1.8.4") in result.pins
    assert ("golang.org/x/crypto", "0.14.0") in result.pins
    assert ("github.com/spf13/cobra", "1.7.0") in result.pins


def test_go_mod_leading_v_stripped_for_osv():
    # OSV indexes Go versions without the tag's "v" prefix; querying "v1.9.1" misses.
    assert all(not v.startswith("v") for _n, v in parse_go_mod(GO_MOD).pins)


def test_go_mod_replaced_module_is_unresolved_not_reported():
    """A `replace` means the required version is not what gets built."""
    result = parse_go_mod(GO_MOD)
    assert all(name != "github.com/gin-gonic/gin" for name, _v in result.pins)
    assert result.unresolved == 1


def test_go_mod_ignores_module_go_and_exclude_directives():
    names = [name for name, _v in parse_go_mod(GO_MOD).pins]
    assert "github.com/example/service" not in names
    assert "github.com/bad/pkg" not in names


# --- Maven ------------------------------------------------------------------------

POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <groupId>com.example</groupId>
  <artifactId>service</artifactId>
  <version>2.1.0</version>
  <properties>
    <jackson.version>2.15.2</jackson.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.logging.log4j</groupId>
      <artifactId>log4j-core</artifactId>
      <version>2.14.1</version>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>${jackson.version}</version>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>sibling</artifactId>
      <version>${project.version}</version>
    </dependency>
    <dependency>
      <groupId>org.inherited</groupId>
      <artifactId>from-parent</artifactId>
    </dependency>
    <dependency>
      <groupId>org.unknown</groupId>
      <artifactId>prop</artifactId>
      <version>${defined.in.parent}</version>
    </dependency>
    <dependency>
      <groupId>com.vendor</groupId>
      <artifactId>local-jar</artifactId>
      <version>1.0</version>
      <scope>system</scope>
    </dependency>
  </dependencies>
</project>
"""


def test_pom_uses_osv_group_colon_artifact_naming():
    # OSV's Maven ecosystem is keyed on "groupId:artifactId"; artifactId alone misses.
    assert ("org.apache.logging.log4j:log4j-core", "2.14.1") in parse_pom_xml(POM).pins


def test_pom_resolves_own_properties():
    pins = parse_pom_xml(POM).pins
    assert ("com.fasterxml.jackson.core:jackson-databind", "2.15.2") in pins
    assert ("com.example:sibling", "2.1.0") in pins


def test_pom_counts_versions_it_cannot_resolve_instead_of_guessing():
    """Parent-inherited versions, parent-defined properties and system jars."""
    result = parse_pom_xml(POM)
    names = [name for name, _v in result.pins]
    assert "org.inherited:from-parent" not in names
    assert "org.unknown:prop" not in names
    assert "com.vendor:local-jar" not in names
    assert result.unresolved == 3


def test_pom_namespace_is_ignored():
    # The declared xmlns must not stop element lookup — a namespaced POM is the norm.
    assert parse_pom_xml(POM).pins


def test_malformed_pom_yields_nothing_rather_than_raising():
    result = parse_pom_xml("<project><dependencies>")
    assert result.pins == [] and result.unresolved == 0


GRADLE = """plugins { id 'java' }

dependencies {
    implementation 'org.apache.commons:commons-text:1.9'
    api("com.squareup.okhttp3:okhttp:4.9.0")
    testImplementation group: 'junit', name: 'junit', version: '4.13.1'
    implementation "org.example:configurable:$exampleVersion"
    implementation(libs.retrofit)
    implementation platform('org.springframework.boot:spring-boot-dependencies')
    // implementation 'com.commented:out:1.0.0'
}
"""


def test_gradle_reads_string_and_map_notation():
    pins = parse_build_gradle(GRADLE).pins
    assert ("org.apache.commons:commons-text", "1.9") in pins
    assert ("com.squareup.okhttp3:okhttp", "4.9.0") in pins
    assert ("junit:junit", "4.13.1") in pins


def test_gradle_variable_catalog_and_platform_count_as_unresolved():
    """Three shapes whose version lives in a file this parser cannot see."""
    result = parse_build_gradle(GRADLE)
    names = [name for name, _v in result.pins]
    assert "org.example:configurable" not in names
    assert result.unresolved == 3


def test_gradle_ignores_commented_dependencies():
    assert all(name != "com.commented:out" for name, _v in parse_build_gradle(GRADLE).pins)


def test_gradle_kts_shares_the_parser():
    assert versioned_manifest_ecosystem("app/build.gradle.kts") == "maven"


# --- NuGet ------------------------------------------------------------------------

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="12.0.1" />
    <PackageReference Include="Serilog"><Version>2.10.0</Version></PackageReference>
    <PackageReference Include="Ranged" Version="[13.0.1, )" />
    <PackageReference Include="Variable" Version="$(SomeVersion)" />
    <PackageReference Include="Floating" Version="6.*" />
    <PackageReference Include="Centrally.Managed" />
  </ItemGroup>
</Project>
"""


def test_csproj_reads_attribute_and_element_versions():
    pins = parse_csproj(CSPROJ).pins
    assert ("Newtonsoft.Json", "12.0.1") in pins
    assert ("Serilog", "2.10.0") in pins


def test_csproj_ranges_variables_and_wildcards_are_unresolved():
    """None of these name the version restore actually installed."""
    result = parse_csproj(CSPROJ)
    names = [name for name, _v in result.pins]
    assert names == ["Newtonsoft.Json", "Serilog"]
    assert result.unresolved == 4


def test_csproj_matches_on_extension_not_basename():
    assert versioned_manifest_ecosystem("src/Api/Api.csproj") == "nuget"
    assert versioned_manifest_ecosystem("src/Api/Api.fsproj") == "nuget"
    assert versioned_manifest_ecosystem("src/Api/Api.sln") is None


PACKAGES_LOCK = """{
  "version": 1,
  "dependencies": {
    "net8.0": {
      "Newtonsoft.Json": {"type": "Direct", "requested": "[12.0.1, )", "resolved": "12.0.1"},
      "System.Text.Json": {"type": "Transitive", "resolved": "8.0.4"},
      "MyApp.Core": {"type": "Project"}
    }
  }
}
"""


def test_packages_lock_reads_resolved_versions_and_skips_sibling_projects():
    result = parse_packages_lock_json(PACKAGES_LOCK)
    assert ("Newtonsoft.Json", "12.0.1") in result.pins
    assert ("System.Text.Json", "8.0.4") in result.pins
    assert all(name != "MyApp.Core" for name, _v in result.pins)
    assert result.unresolved == 0


# --- RubyGems ---------------------------------------------------------------------

GEMFILE_LOCK = """GIT
  remote: https://github.com/example/forked.git
  revision: abc123
  specs:
    forked (1.0.0)

PATH
  remote: engines/billing
  specs:
    billing (0.1.0)

GEM
  remote: https://rubygems.org/
  specs:
    actionpack (7.0.4)
      rack (~> 2.0, >= 2.2.0)
    nokogiri (1.13.9-x86_64-linux)
    rack (2.2.4)
    sidekiq (7.0.0.beta1)

PLATFORMS
  ruby

DEPENDENCIES
  rails
"""


def test_gemfile_lock_reads_gem_section_specs():
    pins = parse_gemfile_lock(GEMFILE_LOCK).pins
    assert ("actionpack", "7.0.4") in pins
    assert ("rack", "2.2.4") in pins


def test_gemfile_lock_ignores_nested_dependency_constraints():
    """`rack (~> 2.0, >= 2.2.0)` under actionpack is a constraint, not a resolved gem."""
    versions = [v for n, v in parse_gemfile_lock(GEMFILE_LOCK).pins if n == "rack"]
    assert versions == ["2.2.4"]


def test_gemfile_lock_strips_platform_suffix_but_keeps_prereleases():
    pins = dict(parse_gemfile_lock(GEMFILE_LOCK).pins)
    assert pins["nokogiri"] == "1.13.9"
    assert pins["sidekiq"] == "7.0.0.beta1"


def test_gemfile_lock_git_and_path_gems_are_unresolved():
    """A gem from a commit or a directory has no release version to ask RubyGems about."""
    result = parse_gemfile_lock(GEMFILE_LOCK)
    names = [name for name, _v in result.pins]
    assert "forked" not in names and "billing" not in names
    assert result.unresolved == 2


# --- Packagist --------------------------------------------------------------------

COMPOSER_LOCK = """{
  "packages": [
    {"name": "monolog/monolog", "version": "1.25.3"},
    {"name": "symfony/http-kernel", "version": "v4.4.13"},
    {"name": "vendor/unstable", "version": "dev-main"}
  ],
  "packages-dev": [
    {"name": "phpunit/phpunit", "version": "9.5.0"}
  ]
}
"""


def test_composer_lock_reads_both_sections_and_strips_tag_prefix():
    pins = parse_composer_lock(COMPOSER_LOCK).pins
    assert ("monolog/monolog", "1.25.3") in pins
    assert ("symfony/http-kernel", "4.4.13") in pins
    assert ("phpunit/phpunit", "9.5.0") in pins


def test_composer_lock_branch_pins_are_unresolved():
    result = parse_composer_lock(COMPOSER_LOCK)
    assert all(name != "vendor/unstable" for name, _v in result.pins)
    assert result.unresolved == 1


# --- routing ----------------------------------------------------------------------


def test_new_lockfiles_route_through_the_existing_lockfile_api():
    for name in ("Gemfile.lock", "composer.lock", "packages.lock.json"):
        assert name in LOCKFILE_ECOSYSTEM
    assert lockfile_ecosystem("composer.lock") == "packagist"
    assert extract_pinned_lockfile("composer.lock", COMPOSER_LOCK)


def test_versioned_manifests_stay_out_of_the_name_lookup_map():
    """SQG001/SQG005 query a registry by name and have no client for these ecosystems.

    Listing them in MANIFEST_ECOSYSTEM would make SQG001 report every Java dependency as
    "registry unreachable" — a false explanation of why we don't know.
    """
    for path in ("go.mod", "pom.xml", "build.gradle", "Api.csproj"):
        assert manifest_ecosystem(path) is None


def test_parse_pins_is_inert_for_unrelated_files():
    result = parse_pins("src/main.py", "import os\n")
    assert result.pins == [] and result.unresolved == 0


def test_parse_pins_survives_empty_content():
    # The PR path builds a census from paths alone, with empty content for each.
    for path in ("pom.xml", "go.mod", "composer.lock", "Api.csproj"):
        assert parse_pins(path, "").pins == []


# --- coverage integration ---------------------------------------------------------


def test_census_reports_the_new_ecosystems_as_readable():
    census = take_census({"pom.xml": POM, "go.mod": GO_MOD, "Gemfile.lock": GEMFILE_LOCK})
    assert census.ecosystems == {"maven", "go", "rubygems"}
    assert census.unreadable_manifests == {}


def test_census_flags_unresolvable_versions_as_a_range_ecosystem():
    """The POM has three versions it cannot resolve, so maven is not fully pinned."""
    census = take_census({"pom.xml": POM})
    assert "maven" in census.range_ecosystems


def test_census_does_not_call_an_ecosystem_both_covered_and_unreadable():
    """Gemfile alone is unreadable; with its lockfile present, rubygems is covered."""
    gemfile_only = take_census({"Gemfile": "gem 'rails'\n"})
    assert gemfile_only.unreadable_ecosystems == {"rubygems"}

    with_lock = take_census({"Gemfile": "gem 'rails'\n", "Gemfile.lock": GEMFILE_LOCK})
    assert with_lock.unreadable_ecosystems == set()
    assert "rubygems" in with_lock.ecosystems


def test_java_only_repo_no_longer_reports_vulnerabilities_as_unsupported():
    """The regression this work exists to fix: a Maven repo used to get SQG004 =
    not_run_unsupported (or worse, a silent zero), because nothing read pom.xml."""
    from app.coverage import NOT_RUN_UNSUPPORTED, plan_rule

    coverage = plan_rule("SQG004", take_census({"pom.xml": POM}))
    assert coverage.status != NOT_RUN_UNSUPPORTED
    assert "maven" in coverage.covered
