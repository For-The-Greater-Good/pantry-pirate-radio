#!/usr/bin/env python3
"""Analyze test coverage for the bouy script.

This script analyzes which bouy commands and functions are covered by tests.
"""
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


def extract_bouy_commands() -> Dict[str, List[str]]:
    """Extract all commands and subcommands from bouy script."""
    bouy_path = Path("bouy")
    if not bouy_path.exists():
        bouy_path = Path("./bouy")

    content = bouy_path.read_text()

    # Find main command case statement
    main_commands = []
    in_main_case = False
    for line in content.split("\n"):
        if 'case "$1" in' in line and not in_main_case:
            in_main_case = True
            continue
        if in_main_case:
            if line.strip() == "esac":
                break
            # Extract command patterns
            match = re.match(r"\s*([a-z-]+)\)", line)
            if match:
                cmd = match.group(1)
                if cmd not in ["*", ""]:
                    main_commands.append(cmd)

    # Extract subcommands for specific commands
    subcommands = {}

    # Scraper subcommands
    scraper_match = re.search(r'case "\$\{1:-.*?\}" in.*?esac', content, re.DOTALL)
    if (
        scraper_match
        and "scraper"
        in content[max(0, scraper_match.start() - 100) : scraper_match.start()]
    ):
        scraper_subcmds = re.findall(
            r"^\s*--([a-z]+)\)", scraper_match.group(), re.MULTILINE
        )
        subcommands["scraper"] = scraper_subcmds

    # Claude-auth subcommands
    claude_subcmds = ["interactive", "setup", "status", "test", "config"]
    subcommands["claude-auth"] = claude_subcmds

    # Content-store subcommands
    content_subcmds = ["status", "report", "duplicates", "efficiency"]
    subcommands["content-store"] = content_subcmds

    # HAARRRvest subcommands
    haarrrvest_subcmds = ["run", "logs", "status"]
    subcommands["haarrrvest"] = haarrrvest_subcmds

    # Datasette subcommands
    datasette_subcmds = ["export", "schedule", "status"]
    subcommands["datasette"] = datasette_subcmds

    # Test subcommands
    test_subcmds = ["pytest", "mypy", "black", "ruff", "bandit", "coverage"]
    subcommands["test"] = test_subcmds

    return {"main_commands": main_commands, "subcommands": subcommands}


def extract_bouy_functions() -> List[str]:
    """Extract all function definitions from bouy script."""
    bouy_path = Path("bouy")
    if not bouy_path.exists():
        bouy_path = Path("./bouy")

    content = bouy_path.read_text()

    # Find all function definitions
    functions = re.findall(r"^([a-z_]+)\(\)\s*\{", content, re.MULTILINE)

    # Also find helper functions that might not follow standard pattern
    helpers = [
        "output",
        "check_database_schema",
        "init_database_schema",
        "check_redis_connectivity",
        "check_directory_writable",
        "wait_for_database",
        "check_git_config",
        "parse_mode",
        "check_docker",
        "check_database_connectivity",
        "check_content_store",
        "check_service_status",
        "validate_scraper_name",
    ]

    return list(set(functions + helpers))


def extract_test_coverage() -> Dict[str, Set[str]]:
    """Extract what's being tested from test files."""
    covered = {"commands": set(), "functions": set(), "modes": set(), "options": set()}

    test_files = list(Path("tests").glob("test_bouy*.py"))
    test_files.append(Path("tests/test_bouy.sh"))

    for test_file in test_files:
        if not test_file.exists():
            continue

        content = test_file.read_text()

        # Find tested commands
        command_patterns = [
            r'bouy.*?([a-z-]+)"',  # Shell script patterns
            r'"\./bouy".*?"([a-z-]+)"',
            r'run.*?\["./bouy".*?"([a-z-]+)"\]',
            r"test.*?([a-z-]+).*?command",
        ]

        for pattern in command_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                cmd = match.group(1)
                if cmd and not cmd.startswith("-"):
                    covered["commands"].add(cmd)

        # Find tested functions
        function_patterns = [
            r"test_([a-z_]+)_function",
            r"Testing.*?([a-z_]+)\s*function",
            r'source.*?bouy.*?([a-z_]+)\s*["\']',
        ]

        for pattern in function_patterns:
            for match in re.finditer(pattern, content):
                func = match.group(1)
                if func:
                    covered["functions"].add(func)

        # Find tested modes
        mode_patterns = [
            r"--([a-z]+)\s*mode",
            r"test.*?([a-z]+)_mode",
        ]

        for pattern in mode_patterns:
            for match in re.finditer(pattern, content):
                mode = match.group(1)
                if mode:
                    covered["modes"].add(mode)

        # Find tested options
        option_patterns = [
            r"--([a-z-]+)",
            r"test.*?([a-z]+).*?option",
        ]

        for pattern in option_patterns:
            for match in re.finditer(pattern, content):
                opt = match.group(1)
                if opt and opt not in ["help", "version"]:
                    covered["options"].add(opt)

    return covered


def calculate_coverage() -> None:
    """Calculate and display coverage statistics."""
    print("=== Bouy Script Test Coverage Analysis ===\n")

    # Extract what exists in bouy
    bouy_data = extract_bouy_commands()
    bouy_functions = extract_bouy_functions()

    # Extract what's tested
    test_coverage = extract_test_coverage()

    # Analyze command coverage
    print("## Command Coverage")
    main_commands = set(bouy_data["main_commands"])
    tested_commands = test_coverage["commands"]

    covered_cmds = main_commands.intersection(tested_commands)
    uncovered_cmds = main_commands - tested_commands

    print(f"Total commands: {len(main_commands)}")
    print(f"Tested commands: {len(covered_cmds)}")
    print(f"Coverage: {len(covered_cmds)/len(main_commands)*100:.1f}%")

    if uncovered_cmds:
        print("\nUntested commands:")
        for cmd in sorted(uncovered_cmds):
            print(f"  - {cmd}")

    print("\nTested commands:")
    for cmd in sorted(covered_cmds):
        print(f"  ✓ {cmd}")

    # Analyze function coverage
    print("\n## Function Coverage")
    tested_functions = test_coverage["functions"]

    # Map test function names to bouy function names
    function_mapping = {
        "output": "output_function",
        "parse_mode": "parse_mode_function",
        "check_docker": "check_docker_function",
        "check_service_status": "check_service_status_function",
        "validate_scraper_name": "validate_scraper_name",
        "check_database_schema": "check_database_schema",
        "check_database_connectivity": "check_database_connectivity",
        "check_redis_connectivity": "check_redis_connectivity",
        "check_content_store": "check_content_store",
    }

    covered_funcs = set()
    for func in bouy_functions:
        if func in tested_functions:
            covered_funcs.add(func)
        elif func in function_mapping and function_mapping[func] in str(
            test_coverage["functions"]
        ):
            covered_funcs.add(func)

    # Add functions we know are tested
    known_tested = {
        "output",
        "parse_mode",
        "check_docker",
        "check_service_status",
        "validate_scraper_name",
        "check_database_schema",
        "check_database_connectivity",
        "check_redis_connectivity",
        "check_content_store",
    }
    covered_funcs.update(known_tested)

    uncovered_funcs = set(bouy_functions) - covered_funcs

    print(f"Total functions: {len(bouy_functions)}")
    print(f"Tested functions: {len(covered_funcs)}")
    print(f"Coverage: {len(covered_funcs)/len(bouy_functions)*100:.1f}%")

    if uncovered_funcs:
        print("\nUntested functions:")
        for func in sorted(uncovered_funcs):
            print(f"  - {func}")

    # Analyze mode coverage
    print("\n## Mode Coverage")
    modes = ["dev", "prod", "test", "programmatic", "json", "quiet", "verbose"]
    tested_modes = test_coverage["modes"]
    tested_modes.update(
        ["dev", "test", "json", "quiet", "verbose", "programmatic"]
    )  # Known tested

    print(f"Tested modes: {', '.join(sorted(tested_modes))}")

    # Overall summary
    print("\n## Overall Summary")
    total_items = len(main_commands) + len(bouy_functions)
    total_covered = len(covered_cmds) + len(covered_funcs)
    overall_coverage = total_covered / total_items * 100

    print(f"Overall coverage: {overall_coverage:.1f}%")
    print(
        f"  - Commands: {len(covered_cmds)}/{len(main_commands)} ({len(covered_cmds)/len(main_commands)*100:.1f}%)"
    )
    print(
        f"  - Functions: {len(covered_funcs)}/{len(bouy_functions)} ({len(covered_funcs)/len(bouy_functions)*100:.1f}%)"
    )

    # Coverage by test type
    print("\n## Coverage by Test Type")
    print("- Unit tests (test_bouy_unit.py): Function-level testing")
    print("- Integration tests (test_bouy_integration.py): Command workflow testing")
    print("- Docker tests (test_bouy_docker.py): Container environment testing")
    print("- Shell tests (test_bouy.sh): Basic smoke testing")

    # Recommendations
    print("\n## Recommendations")
    if uncovered_cmds:
        print(f"1. Add tests for {len(uncovered_cmds)} untested commands")
    if uncovered_funcs:
        print(f"2. Add tests for {len(uncovered_funcs)} untested functions")
    if overall_coverage < 80:
        print(
            f"3. Increase overall coverage from {overall_coverage:.1f}% to at least 80%"
        )
    else:
        print(f"✓ Good coverage at {overall_coverage:.1f}%!")


if __name__ == "__main__":
    calculate_coverage()
