# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the Gradle parser."""

from pathlib import Path

from macaron.parsers.gradleparser import (
    extract_gav_from_gradle_project,
    extract_included_gradle_modules,
    find_matching_gradle_module_build_configs,
    find_nearest_modules_gradle_config,
)


def test_extract_gav_from_gradle_project(tmp_path: Path) -> None:
    """Test extracting Gradle coordinates from project files."""
    repo_path = tmp_path.joinpath("gradle_repo")
    repo_path.mkdir()
    repo_path.joinpath("gradle.properties").write_text("group=com.example\nversion=1.2.3\n")
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'demo-app'\n")

    assert extract_gav_from_gradle_project(repo_path) == ("com.example", "demo-app", "1.2.3")


def test_extract_gav_from_gradle_project_project_keys(tmp_path: Path) -> None:
    """Test extracting Gradle coordinates from projectGroup/projectVersion keys."""
    repo_path = tmp_path.joinpath("gradle_repo")
    repo_path.mkdir()
    repo_path.joinpath("gradle.properties").write_text("projectGroup=io.micronaut.test\nprojectVersion=4.5.0\n")
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'test-parent'\n")

    assert extract_gav_from_gradle_project(repo_path) == ("io.micronaut.test", "test-parent", "4.5.0")


def test_extract_gav_from_gradle_project_project_group_id_key(tmp_path: Path) -> None:
    """Test extracting Gradle coordinates from projectGroupId key."""
    repo_path = tmp_path.joinpath("gradle_repo")
    repo_path.mkdir()
    repo_path.joinpath("gradle.properties").write_text("projectGroupId=io.micronaut\nprojectVersion=4.2.3\n")
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'micronaut'\n")

    assert extract_gav_from_gradle_project(repo_path) == ("io.micronaut", "micronaut", "4.2.3")


def test_extract_gav_from_gradle_project_not_found(tmp_path: Path) -> None:
    """Test extracting Gradle coordinates when no config values exist."""
    repo_path = tmp_path.joinpath("gradle_repo_empty")
    repo_path.mkdir()
    repo_path.joinpath("build.gradle").write_text("plugins { id 'java' }\n")

    assert extract_gav_from_gradle_project(repo_path) == (None, None, None)


def test_extract_gav_from_gradle_project_method_style_group(tmp_path: Path) -> None:
    """Test extracting group from Gradle method-style syntax (group '...')."""
    repo_path = tmp_path.joinpath("gradle_repo")
    repo_path.mkdir()
    repo_path.joinpath("gradle.properties").write_text("version=3.0.0\n")
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'spring-boot-build'\n")
    repo_path.joinpath("build.gradle").write_text(
        "\n".join(
            [
                "allprojects {",
                '    group "org.springframework.boot"',
                "}",
            ]
        )
        + "\n"
    )

    assert extract_gav_from_gradle_project(repo_path) == ("org.springframework.boot", "spring-boot-build", "3.0.0")


def test_extract_included_gradle_modules(tmp_path: Path) -> None:
    """Test extracting module names from include directives."""
    settings_file = tmp_path.joinpath("settings.gradle")
    settings_file.write_text(
        "\n".join(
            [
                "include 'test-core'",
                'include "test-junit5"',
                "include(':feature:service', ':feature:api')",
            ]
        )
        + "\n"
    )

    assert extract_included_gradle_modules(settings_file) == [
        "test-core",
        "test-junit5",
        ":feature:service",
        ":feature:api",
    ]


def test_extract_included_gradle_modules_dynamic_it_name(tmp_path: Path) -> None:
    """Test expanding dynamic include entries that use ${it.name}."""
    repo_path = tmp_path.joinpath("repo")
    starters_dir = repo_path.joinpath("spring-boot-project", "spring-boot-starters")
    starters_dir.joinpath("spring-boot-starter-thymeleaf").mkdir(parents=True)
    starters_dir.joinpath("spring-boot-starter-web").mkdir(parents=True)
    repo_path.joinpath("settings.gradle").write_text(
        "\n".join(
            [
                'file("${rootDir}/spring-boot-project/spring-boot-starters").eachDirMatch(~/spring-boot-starter.*/) {',
                '    include "spring-boot-project:spring-boot-starters:${it.name}"',
                "}",
            ]
        )
        + "\n"
    )

    assert extract_included_gradle_modules(repo_path.joinpath("settings.gradle")) == [
        "spring-boot-project:spring-boot-starters:spring-boot-starter-thymeleaf",
        "spring-boot-project:spring-boot-starters:spring-boot-starter-web",
    ]


def test_find_matching_gradle_module_build_configs(tmp_path: Path) -> None:
    """Test finding module build files based on artifact id suffix matching."""
    repo_path = tmp_path.joinpath("repo")
    repo_path.joinpath("test-junit5").mkdir(parents=True)
    repo_path.joinpath("settings.gradle").write_text("include 'test-core'\ninclude 'test-junit5'\n")
    target_build = repo_path.joinpath("test-junit5", "build.gradle")
    target_build.write_text("plugins { id 'java' }\n")

    assert find_matching_gradle_module_build_configs(repo_path, "micronaut-test-junit5") == [target_build]


def test_find_matching_gradle_module_build_configs_dynamic_it_name(tmp_path: Path) -> None:
    """Test finding module build files from dynamically included Gradle modules."""
    repo_path = tmp_path.joinpath("repo")
    starter_thymeleaf = repo_path.joinpath(
        "spring-boot-project", "spring-boot-starters", "spring-boot-starter-thymeleaf"
    )
    starter_web = repo_path.joinpath("spring-boot-project", "spring-boot-starters", "spring-boot-starter-web")
    starter_thymeleaf.mkdir(parents=True)
    starter_web.mkdir(parents=True)
    target_build = starter_thymeleaf.joinpath("build.gradle")
    target_build.write_text("plugins { id 'java' }\n")
    starter_web.joinpath("build.gradle").write_text("plugins { id 'java' }\n")
    repo_path.joinpath("settings.gradle").write_text(
        "\n".join(
            [
                'file("${rootDir}/spring-boot-project/spring-boot-starters").eachDirMatch(~/spring-boot-starter.*/) {',
                '    include "spring-boot-project:spring-boot-starters:${it.name}"',
                "}",
            ]
        )
        + "\n"
    )

    assert find_matching_gradle_module_build_configs(repo_path, "spring-boot-starter-thymeleaf") == [target_build]


def test_find_matching_gradle_module_build_configs_nested_fallback(tmp_path: Path) -> None:
    """Test nested settings fallback when root settings do not match."""
    repo_path = tmp_path.joinpath("repo")
    repo_path.joinpath("build-logic", "test-junit5").mkdir(parents=True)
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'repo'\n")
    repo_path.joinpath("build-logic", "settings.gradle").write_text("include 'test-junit5'\n")
    target_build = repo_path.joinpath("build-logic", "test-junit5", "build.gradle")
    target_build.write_text("plugins { id 'java' }\n")

    assert find_matching_gradle_module_build_configs(repo_path, "micronaut-test-junit5") == [target_build]


def test_extract_included_gradle_modules_include_it_name(tmp_path: Path) -> None:
    """Test extracting include(it.name) modules from top-level Gradle subprojects."""
    repo_path = tmp_path.joinpath("repo")
    repo_path.joinpath("acra-core").mkdir(parents=True)
    repo_path.joinpath("acra-http").mkdir(parents=True)
    repo_path.joinpath("examples").mkdir(parents=True)
    repo_path.joinpath("acra-core", "build.gradle.kts").write_text("plugins {}\n")
    repo_path.joinpath("acra-http", "build.gradle.kts").write_text("plugins {}\n")
    repo_path.joinpath("examples", "build.gradle.kts").write_text("plugins {}\n")
    settings_file = repo_path.joinpath("settings.gradle.kts")
    settings_file.write_text(
        "\n".join(
            [
                "rootDir.listFiles()?.forEach {",
                "  include(it.name)",
                "}",
            ]
        )
        + "\n"
    )

    assert extract_included_gradle_modules(settings_file) == ["acra-core", "acra-http", "examples"]


def test_find_nearest_modules_gradle_config(tmp_path: Path) -> None:
    """Test finding the nearest module-defining Gradle settings file."""
    repo_path = tmp_path.joinpath("repo")
    submodule_path = repo_path.joinpath("project1")
    submodule_path.mkdir(parents=True)
    repo_path.joinpath("settings.gradle").write_text("include 'project1'\n")
    submodule_build = submodule_path.joinpath("build.gradle")
    submodule_build.write_text("plugins { id 'java' }\n")

    assert find_nearest_modules_gradle_config(submodule_build, repo_path) == "settings.gradle"


def test_find_nearest_modules_gradle_config_no_modules(tmp_path: Path) -> None:
    """Test module settings lookup when no include declaration exists."""
    repo_path = tmp_path.joinpath("repo")
    repo_path.mkdir()
    repo_path.joinpath("settings.gradle").write_text("rootProject.name = 'demo'\n")
    build_path = repo_path.joinpath("build.gradle")
    build_path.write_text("plugins { id 'java' }\n")

    assert find_nearest_modules_gradle_config(build_path, repo_path) is None
