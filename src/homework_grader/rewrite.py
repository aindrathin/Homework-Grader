"""Rewrite a temporary copy of student code so random numbers come from one seeded generator.

Every ``Math.random()`` call, every ``new Random(...)``, and every one-argument
``Collections.shuffle(list)`` is pointed at a single shared ``java.util.Random``
created by the helper class below. The grader passes the test's seed with
``-Dgrader.seed=N``, so for seed 7 the program behaves exactly as if the student
had written ``Random r = new Random(7);`` and used ``r`` everywhere.

``Math.random()`` itself is ``nextDouble()`` on a hidden ``Random``, so
``(int)(Math.random() * 6)`` and ``(int)(r.nextDouble() * 6)`` give the same values.

Package declarations are also removed so every class lives in the default
package and can be run as ``java -cp classes MainClass``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .javasource import split_segments

HELPER_CLASS = "GraderRandom__"
HELPER_SOURCE = f"""\
// Added by Homework Grader. Not part of the student's submission.
public final class {HELPER_CLASS} {{
    private {HELPER_CLASS}() {{}}

    public static final java.util.Random R = create();

    private static java.util.Random create() {{
        String seed = System.getProperty("grader.seed");
        return seed == null ? new java.util.Random() : new java.util.Random(Long.parseLong(seed));
    }}
}}
"""

SHARED = f"{HELPER_CLASS}.R"

# Arguments with at most one level of nested parentheses, e.g. (System.nanoTime()).
_ARGS = r"(?:[^()]|\([^()]*\))*"
_MATH_RANDOM = re.compile(r"\b(?:java\s*\.\s*lang\s*\.\s*)?Math\s*\.\s*random\s*\(\s*\)")
_NEW_RANDOM = re.compile(rf"\bnew\s+(?:java\s*\.\s*util\s*\.\s*)?Random\s*\({_ARGS}\)")
_SHUFFLE_ONE_ARG = re.compile(
    r"(\b(?:java\s*\.\s*util\s*\.\s*)?Collections\s*\.\s*shuffle\s*\()"
    r"((?:[^(),]|\([^()]*\))*)\)"
)
_PACKAGE = re.compile(r"\bpackage\s+([\w.]+)\s*;")
_UNSEEDABLE = {
    "ThreadLocalRandom": "ThreadLocalRandom",
    "SecureRandom": "SecureRandom",
    "SplittableRandom": "SplittableRandom",
}
_NOT_NEWLINE = re.compile(r"[^\n]")


@dataclass
class RewriteResult:
    source: str
    notes: list[str] = field(default_factory=list)


def rewrite_source(src: str, *, seed_random_class: bool = True) -> RewriteResult:
    """Return a seeded, package-free copy of one Java source file.

    ``seed_random_class`` should be False when the student wrote their own class
    named ``Random``, because then ``new Random()`` is not ``java.util.Random``.
    Line numbers are preserved so compiler errors still point at the right line.
    """
    segments = split_segments(src)
    notes: list[str] = []

    package = None
    for is_code, text in segments:
        if is_code and (m := _PACKAGE.search(text)):
            package = m.group(1)
            break

    counts = {"math": 0, "new": 0, "shuffle": 0}

    def count(key: str, replacement: str):
        def _sub(_m: re.Match[str]) -> str:
            counts[key] += 1
            return replacement

        return _sub

    def shuffle_sub(m: re.Match[str]) -> str:
        counts["shuffle"] += 1
        return f"{m.group(1)}{m.group(2)}, {SHARED})"

    blank = lambda m: _NOT_NEWLINE.sub("", m.group(0))  # noqa: E731 - keep newlines only

    out: list[str] = []
    for is_code, text in segments:
        if is_code:
            if package:
                text = _PACKAGE.sub(blank, text)
                own_import = rf"\bimport\s+{re.escape(package)}\s*\.\s*(?:\w+|\*)\s*;"
                text = re.sub(own_import, blank, text)
            text = _MATH_RANDOM.sub(count("math", f"{SHARED}.nextDouble()"), text)
            if seed_random_class:
                text = _NEW_RANDOM.sub(count("new", SHARED), text)
            text = _SHUFFLE_ONE_ARG.sub(shuffle_sub, text)
            for word, label in _UNSEEDABLE.items():
                if re.search(rf"\b{word}\b", text) and not any(label in n for n in notes):
                    notes.append(f"Uses {label}, which the grader cannot seed; output may vary.")
        out.append(text)

    if package:
        notes.append(f"Removed 'package {package};' so the code runs from the default package.")
    seeded = []
    if counts["math"]:
        seeded.append(f"{counts['math']} Math.random()")
    if counts["new"]:
        seeded.append(f"{counts['new']} new Random(...)")
    if counts["shuffle"]:
        seeded.append(f"{counts['shuffle']} Collections.shuffle(...)")
    if seeded:
        notes.append("Seeded randomness: " + ", ".join(seeded) + ".")
    if not seed_random_class and _NEW_RANDOM.search(src):
        notes.append("Student defines a class named Random, so 'new Random()' was not changed.")
    return RewriteResult("".join(out), notes)
