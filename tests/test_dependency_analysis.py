from __future__ import annotations

import unittest

from src.indexer.dependencies import DependencyAnalyzer


class DependencyAnalysisTests(unittest.TestCase):
    def test_parse_pyproject_counts_direct_and_dev_dependencies(self) -> None:
        content = """
[project]
dependencies = ["httpx>=0.27", "rich==15.0.0"]

[project.optional-dependencies]
docs = ["mkdocs>=1.5"]

[dependency-groups]
dev = ["pytest>=8.0", "ruff==0.5.0"]
"""

        result = DependencyAnalyzer.parse_manifest("pyproject.toml", content)

        self.assertIsNotNone(result)
        self.assertEqual(result.ecosystem, "python")
        self.assertEqual(result.direct_dependency_count, 3)
        self.assertEqual(result.dev_dependency_count, 2)
        self.assertGreaterEqual(result.unpinned_or_broad_range_count, 3)

    def test_parse_package_json_detects_workspace_and_overrides(self) -> None:
        content = """
{
  "dependencies": {"react": "^18.3.0", "left-pad": "file:../left-pad"},
  "devDependencies": {"vitest": "^2.0.0"},
  "workspaces": ["packages/*"],
  "overrides": {"debug": "4.3.5"}
}
"""

        result = DependencyAnalyzer.parse_manifest("package.json", content)

        self.assertIsNotNone(result)
        self.assertEqual(result.ecosystem, "node")
        self.assertEqual(result.direct_dependency_count, 2)
        self.assertEqual(result.dev_dependency_count, 1)
        self.assertEqual(result.git_or_path_dependency_count, 1)
        self.assertTrue(result.workspace_or_multi_module)
        self.assertEqual(result.override_or_replace_count, 1)

    def test_parse_cargo_toml_detects_overrides_and_workspace(self) -> None:
        content = """
[workspace]
members = ["crates/*"]

[dependencies]
serde = "1.0"
tokio = { version = "1", features = ["rt-multi-thread"] }
local-crate = { path = "../local-crate" }

[dev-dependencies]
pretty_assertions = "1.4"

[patch.crates-io]
serde = { git = "https://github.com/serde-rs/serde" }
"""

        result = DependencyAnalyzer.parse_manifest("Cargo.toml", content)

        self.assertIsNotNone(result)
        self.assertEqual(result.ecosystem, "rust")
        self.assertEqual(result.direct_dependency_count, 3)
        self.assertEqual(result.dev_dependency_count, 1)
        self.assertGreaterEqual(result.git_or_path_dependency_count, 1)
        self.assertTrue(result.workspace_or_multi_module)
        self.assertGreaterEqual(result.override_or_replace_count, 1)

    def test_parse_go_mod_detects_replace(self) -> None:
        content = """
module example.com/demo

require (
    github.com/pkg/errors v0.9.1
    golang.org/x/text v0.14.0 // indirect
)

replace example.com/shared => ../shared
"""

        result = DependencyAnalyzer.parse_manifest("go.mod", content)

        self.assertIsNotNone(result)
        self.assertEqual(result.ecosystem, "go")
        self.assertEqual(result.direct_dependency_count, 1)
        self.assertEqual(result.override_or_replace_count, 1)

    def test_parse_build_manifests_for_cpp_and_java(self) -> None:
        cmake = """
find_package(fmt REQUIRED)
FetchContent_Declare(mydep GIT_REPOSITORY https://example.com/dep.git)
add_subdirectory(src/lib)
"""
        pom = """
<project>
  <modules><module>api</module></modules>
  <dependencyManagement>
    <dependencies>
      <dependency><groupId>x</groupId><artifactId>y</artifactId><version>1.0.0</version></dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency><groupId>a</groupId><artifactId>b</artifactId><version>1.2.3</version></dependency>
    <dependency><groupId>t</groupId><artifactId>test</artifactId><version>${test.version}</version><scope>test</scope></dependency>
  </dependencies>
</project>
"""

        cmake_result = DependencyAnalyzer.parse_manifest("CMakeLists.txt", cmake)
        pom_result = DependencyAnalyzer.parse_manifest("pom.xml", pom)

        self.assertEqual(cmake_result.ecosystem, "cpp")
        self.assertEqual(cmake_result.direct_dependency_count, 2)
        self.assertTrue(cmake_result.workspace_or_multi_module)
        self.assertEqual(pom_result.ecosystem, "java")
        self.assertEqual(pom_result.direct_dependency_count, 1)
        self.assertEqual(pom_result.dev_dependency_count, 1)
        self.assertTrue(pom_result.workspace_or_multi_module)
        self.assertEqual(pom_result.override_or_replace_count, 1)


if __name__ == "__main__":
    unittest.main()
