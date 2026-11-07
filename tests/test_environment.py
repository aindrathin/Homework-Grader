"""Smoke tests that the development environment can compile and run Java."""

import shutil
import subprocess
from pathlib import Path

import homework_grader


def test_package_imports():
    assert homework_grader.__version__


def test_java_tools_on_path():
    assert shutil.which("javac"), "javac not found; install a JDK and add it to PATH"
    assert shutil.which("java"), "java not found; install a JDK and add it to PATH"


def test_compile_and_run_java(tmp_path: Path):
    source = tmp_path / "Hello.java"
    source.write_text(
        'public class Hello { public static void main(String[] a) { System.out.println("hi"); } }'
    )
    subprocess.run(["javac", str(source)], check=True, cwd=tmp_path)
    result = subprocess.run(
        ["java", "-cp", str(tmp_path), "Hello"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "hi"
