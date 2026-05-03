from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


DEPENDENCY_MANIFEST_PATTERNS: dict[str, list[str]] = {
    "python": ["requirements*.txt", "pyproject.toml"],
    "node": ["package.json"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"],
    "cpp": ["CMakeLists.txt", "conanfile.txt", "conanfile.py", "vcpkg.json"],
}

DEPENDENCY_MANIFEST_HINTS = {
    pattern.lower()
    for patterns in DEPENDENCY_MANIFEST_PATTERNS.values()
    for pattern in patterns
}


@dataclass
class DependencyProfile:
    repo_id: str
    manifest_count: int = 0
    ecosystems: list[str] = field(default_factory=list)
    manifest_paths: list[str] = field(default_factory=list)
    direct_dependency_count: int = 0
    dev_dependency_count: int = 0
    unpinned_or_broad_range_count: int = 0
    git_or_path_dependency_count: int = 0
    override_or_replace_count: int = 0
    workspace_or_multi_module: bool = False
    risk_flags: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    def complexity_score(self) -> float:
        if self.manifest_count == 0:
            return 0.0

        score = 0.0
        score += min(self.manifest_count / 6, 1.0) * 0.12
        score += min(self.direct_dependency_count / 80, 1.0) * 0.34
        score += min(self.dev_dependency_count / 50, 1.0) * 0.10
        score += min(self.unpinned_or_broad_range_count / 20, 1.0) * 0.16
        score += min(self.git_or_path_dependency_count / 6, 1.0) * 0.11
        score += min(self.override_or_replace_count / 5, 1.0) * 0.09
        if len(self.ecosystems) > 1:
            score += 0.04
        if self.workspace_or_multi_module:
            score += 0.04
        return min(score, 1.0)


@dataclass
class ManifestDependencyStats:
    ecosystem: str
    path: str
    direct_dependency_count: int = 0
    dev_dependency_count: int = 0
    unpinned_or_broad_range_count: int = 0
    git_or_path_dependency_count: int = 0
    override_or_replace_count: int = 0
    workspace_or_multi_module: bool = False


class DependencyAnalyzer:
    @classmethod
    def is_dependency_manifest(cls, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        lower_name = posix_path.name.lower()
        for patterns in DEPENDENCY_MANIFEST_PATTERNS.values():
            for pattern in patterns:
                if posix_path.match(pattern) or lower_name == pattern.lower():
                    return True
        return False

    @classmethod
    def analyze_repository(
        cls,
        repo_root: Path,
        repo_id: str,
        candidate_paths: list[str] | None = None,
    ) -> DependencyProfile:
        manifest_paths = cls._discover_manifest_paths(repo_root, candidate_paths)
        stats = []
        for relative_path in manifest_paths:
            file_path = repo_root / relative_path
            try:
                content = file_path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                stat = cls.parse_manifest(relative_path, content)
            except Exception:
                continue
            if stat:
                stats.append(stat)

        return cls._aggregate(repo_id, stats)

    @classmethod
    def parse_manifest(cls, relative_path: str, content: str) -> ManifestDependencyStats | None:
        parser = cls._select_parser(relative_path)
        if parser is None:
            return None
        return parser(relative_path, content)

    @classmethod
    def _discover_manifest_paths(cls, repo_root: Path, candidate_paths: list[str] | None) -> list[str]:
        if candidate_paths is not None:
            paths = [path for path in candidate_paths if cls.is_dependency_manifest(path)]
            return sorted(dict.fromkeys(paths))

        discovered: list[str] = []
        for file_path in repo_root.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(repo_root).as_posix()
                if cls.is_dependency_manifest(relative_path):
                    discovered.append(relative_path)
        return sorted(dict.fromkeys(discovered))

    @classmethod
    def _select_parser(cls, relative_path: str):
        filename = Path(relative_path).name.lower()
        if filename.startswith("requirements") and filename.endswith(".txt"):
            return cls._parse_requirements
        if filename == "pyproject.toml":
            return cls._parse_pyproject
        if filename == "package.json":
            return cls._parse_package_json
        if filename == "cargo.toml":
            return cls._parse_cargo_toml
        if filename == "go.mod":
            return cls._parse_go_mod
        if filename == "pom.xml":
            return cls._parse_pom_xml
        if filename in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
            return cls._parse_gradle
        if filename == "cmakelists.txt":
            return cls._parse_cmake
        if filename == "conanfile.txt":
            return cls._parse_conan_txt
        if filename == "conanfile.py":
            return cls._parse_conan_py
        if filename == "vcpkg.json":
            return cls._parse_vcpkg
        return None

    @staticmethod
    def _empty(path: str, ecosystem: str) -> ManifestDependencyStats:
        return ManifestDependencyStats(ecosystem=ecosystem, path=path)

    @staticmethod
    def _count_constraints(values: list[str]) -> tuple[int, int]:
        broad = 0
        git_or_path = 0
        for value in values:
            normalized = value.strip()
            if not normalized:
                broad += 1
                continue
            lowered = normalized.lower()
            if any(
                token in lowered
                for token in ("git+", "github.com", "file:", "path =", "path=", "../", "./", "workspace:", "link:")
            ):
                git_or_path += 1
            if not re.fullmatch(r"=?v?\d+(?:\.\d+){0,3}", normalized):
                broad += 1
        return broad, git_or_path

    @classmethod
    def _parse_requirements(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "python")
        is_dev = any(token in Path(relative_path).name.lower() for token in ("dev", "test"))
        constraints: list[str] = []

        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            if line.startswith((".", "/")) or "git+" in line or "@" in line:
                constraints.append(line)
            else:
                match = re.match(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(.*)$", line)
                if not match:
                    continue
                constraints.append(match.group(1).strip())

        if is_dev:
            stats.dev_dependency_count = len(constraints)
        else:
            stats.direct_dependency_count = len(constraints)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(constraints)
        return stats

    @classmethod
    def _parse_pyproject(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "python")
        data = tomllib.loads(content)

        project = data.get("project", {})
        dependencies = project.get("dependencies", [])
        optional_deps = project.get("optional-dependencies", {})
        dependency_groups = data.get("dependency-groups", {})

        poetry = data.get("tool", {}).get("poetry", {})
        poetry_deps = poetry.get("dependencies", {})
        poetry_dev = poetry.get("group", {}).get("dev", {}).get("dependencies", {})
        poetry_legacy_dev = poetry.get("dev-dependencies", {})

        direct_constraints = [cls._extract_pep508_constraint(dep) for dep in dependencies]
        for dep_list in optional_deps.values():
            direct_constraints.extend(cls._extract_pep508_constraint(dep) for dep in dep_list)

        for name, spec in poetry_deps.items():
            if name.lower() != "python":
                direct_constraints.append(cls._extract_poetry_constraint(spec))

        dev_constraints = []
        for dep_list in dependency_groups.values():
            dev_constraints.extend(cls._extract_pep508_constraint(dep) for dep in dep_list)
        for spec in poetry_dev.values():
            dev_constraints.append(cls._extract_poetry_constraint(spec))
        for spec in poetry_legacy_dev.values():
            dev_constraints.append(cls._extract_poetry_constraint(spec))

        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        all_constraints = direct_constraints + dev_constraints
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(all_constraints)
        return stats

    @classmethod
    def _parse_package_json(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "node")
        data = json.loads(content)
        deps = data.get("dependencies", {})
        optional = data.get("optionalDependencies", {})
        peer = data.get("peerDependencies", {})
        dev = data.get("devDependencies", {})

        direct_constraints = [str(value) for value in {**deps, **optional, **peer}.values()]
        dev_constraints = [str(value) for value in dev.values()]

        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        all_constraints = direct_constraints + dev_constraints
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(all_constraints)
        stats.workspace_or_multi_module = bool(data.get("workspaces"))
        if data.get("overrides"):
            stats.override_or_replace_count = len(data.get("overrides", {}))
        return stats

    @classmethod
    def _parse_cargo_toml(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "rust")
        data = tomllib.loads(content)

        direct_constraints = cls._extract_toml_dependency_block(data.get("dependencies", {}))
        dev_constraints = cls._extract_toml_dependency_block(data.get("dev-dependencies", {}))

        for key, value in data.items():
            if key.startswith("target.") and isinstance(value, dict):
                direct_constraints.extend(cls._extract_toml_dependency_block(value.get("dependencies", {})))
                dev_constraints.extend(cls._extract_toml_dependency_block(value.get("dev-dependencies", {})))

        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        all_constraints = direct_constraints + dev_constraints
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(all_constraints)
        if data.get("replace"):
            stats.override_or_replace_count += len(data.get("replace", {}))
        if data.get("patch"):
            stats.override_or_replace_count += sum(
                len(value) for value in data.get("patch", {}).values() if isinstance(value, dict)
            )
        workspace = data.get("workspace", {})
        stats.workspace_or_multi_module = bool(workspace.get("members")) or bool(workspace)
        return stats

    @classmethod
    def _parse_go_mod(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "go")
        constraints: list[str] = []
        replace_count = 0

        in_require_block = False
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue
            if line.startswith("require ("):
                in_require_block = True
                continue
            if in_require_block and line == ")":
                in_require_block = False
                continue
            if line.startswith("replace "):
                replace_count += 1
            if line.startswith("module "):
                continue

            if in_require_block or line.startswith("require "):
                parts = line.replace("require ", "", 1).split()
                if len(parts) >= 2:
                    if "// indirect" not in line:
                        constraints.append(parts[1])

        stats.direct_dependency_count = len(constraints)
        stats.override_or_replace_count = replace_count
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(constraints)
        return stats

    @classmethod
    def _parse_pom_xml(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "java")
        root = ElementTree.fromstring(content)
        namespace_match = re.match(r"\{(.+)\}", root.tag)
        namespace = {"m": namespace_match.group(1)} if namespace_match else {}
        prefix = "m:" if namespace else ""
        parent_map = {child: parent for parent in root.iter() for child in parent}

        direct_constraints: list[str] = []
        dev_constraints: list[str] = []
        for dep in root.findall(f".//{prefix}dependency", namespace):
            parent = parent_map.get(dep)
            grandparent = parent_map.get(parent) if parent is not None else None
            if grandparent is not None and grandparent.tag.endswith("dependencyManagement"):
                continue
            version = dep.findtext(f"{prefix}version", default="", namespaces=namespace).strip()
            scope = dep.findtext(f"{prefix}scope", default="", namespaces=namespace).strip().lower()
            if scope == "test":
                dev_constraints.append(version)
            else:
                direct_constraints.append(version)

        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(
            direct_constraints + dev_constraints
        )

        modules = root.findall(f".//{prefix}modules/{prefix}module", namespace)
        stats.workspace_or_multi_module = bool(modules)
        dep_mgmt = root.findall(f".//{prefix}dependencyManagement/{prefix}dependencies/{prefix}dependency", namespace)
        stats.override_or_replace_count = len(dep_mgmt)
        return stats

    @classmethod
    def _parse_gradle(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "java")
        direct_constraints: list[str] = []
        dev_constraints: list[str] = []

        for match in re.finditer(
            r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|\s)\s*[\"']([^\"']+)[\"']",
            content,
        ):
            config_name = match.group(1).lower()
            notation = match.group(2)
            version = notation.rsplit(":", 1)[-1] if ":" in notation else ""
            if "test" in config_name:
                dev_constraints.append(version)
            else:
                direct_constraints.append(version)

        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(
            direct_constraints + dev_constraints
        )
        stats.workspace_or_multi_module = "include(" in content or "include " in content
        if "dependencyManagement" in content or "resolutionStrategy" in content:
            stats.override_or_replace_count = 1
        return stats

    @classmethod
    def _parse_cmake(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "cpp")
        direct_count = len(re.findall(r"\bfind_package\s*\(", content, flags=re.IGNORECASE))
        direct_count += len(re.findall(r"\bFetchContent_Declare\s*\(", content, flags=re.IGNORECASE))
        stats.direct_dependency_count = direct_count
        stats.workspace_or_multi_module = "add_subdirectory(" in content
        stats.git_or_path_dependency_count = len(
            re.findall(r"\b(?:GIT_REPOSITORY|SOURCE_DIR|URL)\b", content, flags=re.IGNORECASE)
        )
        return stats

    @classmethod
    def _parse_conan_txt(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "cpp")
        section = None
        direct_constraints: list[str] = []
        dev_constraints: list[str] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line.strip("[]").lower()
                continue
            if section == "requires":
                direct_constraints.append(line)
            elif section == "tool_requires":
                dev_constraints.append(line)
        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(
            direct_constraints + dev_constraints
        )
        return stats

    @classmethod
    def _parse_conan_py(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "cpp")
        requires = re.findall(r"requires\s*=\s*\(([^)]*)\)|requires\s*=\s*\[([^\]]*)\]", content)
        tool_requires = re.findall(r"tool_requires\s*=\s*\(([^)]*)\)|tool_requires\s*=\s*\[([^\]]*)\]", content)
        direct_constraints = cls._extract_python_string_literals(requires)
        dev_constraints = cls._extract_python_string_literals(tool_requires)
        stats.direct_dependency_count = len(direct_constraints)
        stats.dev_dependency_count = len(dev_constraints)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(
            direct_constraints + dev_constraints
        )
        return stats

    @classmethod
    def _parse_vcpkg(cls, relative_path: str, content: str) -> ManifestDependencyStats:
        stats = cls._empty(relative_path, "cpp")
        data = json.loads(content)
        dependencies = data.get("dependencies", [])
        versions: list[str] = []
        for item in dependencies:
            if isinstance(item, str):
                versions.append("")
            elif isinstance(item, dict):
                version = str(
                    item.get("version>=")
                    or item.get("version")
                    or item.get("baseline")
                    or ""
                )
                versions.append(version)
        stats.direct_dependency_count = len(dependencies)
        stats.unpinned_or_broad_range_count, stats.git_or_path_dependency_count = cls._count_constraints(versions)
        if data.get("overrides"):
            stats.override_or_replace_count = len(data.get("overrides", []))
        return stats

    @classmethod
    def _aggregate(cls, repo_id: str, stats_list: list[ManifestDependencyStats]) -> DependencyProfile:
        ecosystems = sorted({stats.ecosystem for stats in stats_list})
        profile = DependencyProfile(
            repo_id=repo_id,
            manifest_count=len(stats_list),
            ecosystems=ecosystems,
            manifest_paths=[stats.path for stats in stats_list],
            direct_dependency_count=sum(stats.direct_dependency_count for stats in stats_list),
            dev_dependency_count=sum(stats.dev_dependency_count for stats in stats_list),
            unpinned_or_broad_range_count=sum(stats.unpinned_or_broad_range_count for stats in stats_list),
            git_or_path_dependency_count=sum(stats.git_or_path_dependency_count for stats in stats_list),
            override_or_replace_count=sum(stats.override_or_replace_count for stats in stats_list),
            workspace_or_multi_module=any(stats.workspace_or_multi_module for stats in stats_list),
        )

        flags = []
        if profile.direct_dependency_count >= 50:
            flags.append("Large dependency surface area")
        if profile.unpinned_or_broad_range_count >= 5:
            flags.append("Several dependencies use broad or unpinned version constraints")
        if profile.git_or_path_dependency_count > 0:
            flags.append("Includes git or local path dependencies")
        if profile.override_or_replace_count > 0:
            flags.append("Uses dependency overrides or replacements")
        if profile.workspace_or_multi_module:
            flags.append("Workspace or multi-module build increases coordination cost")
        if len(profile.ecosystems) > 1:
            flags.append("Multiple dependency ecosystems are active in this repository")

        profile.risk_flags = flags
        return profile

    @staticmethod
    def _extract_pep508_constraint(value: str) -> str:
        if ";" in value:
            value = value.split(";", 1)[0]
        if "@" in value:
            return value.split("@", 1)[1].strip()
        match = re.match(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(.*)$", value.strip())
        return match.group(1).strip() if match else value.strip()

    @staticmethod
    def _extract_poetry_constraint(spec: Any) -> str:
        if isinstance(spec, str):
            return spec
        if isinstance(spec, dict):
            if "version" in spec:
                return str(spec["version"])
            if "path" in spec:
                return f"path={spec['path']}"
            if "git" in spec:
                return f"git={spec['git']}"
        return ""

    @staticmethod
    def _extract_toml_dependency_block(block: dict[str, Any]) -> list[str]:
        constraints: list[str] = []
        for name, spec in block.items():
            if not name:
                continue
            constraints.append(DependencyAnalyzer._extract_poetry_constraint(spec))
        return constraints

    @staticmethod
    def _extract_python_string_literals(matches: list[tuple[str, str]]) -> list[str]:
        values: list[str] = []
        for left, right in matches:
            chunk = left or right
            values.extend(re.findall(r"[\"']([^\"']+)[\"']", chunk))
        return values


__all__ = [
    "DEPENDENCY_MANIFEST_HINTS",
    "DEPENDENCY_MANIFEST_PATTERNS",
    "DependencyAnalyzer",
    "DependencyProfile",
]
