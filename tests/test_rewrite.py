from homework_grader.javasource import code_only, split_segments
from homework_grader.rewrite import SHARED, rewrite_source


def test_segments_round_trip():
    src = (
        'int x = 1; // Math.random()\nString s = "a\\"b"; char c = \'"\';'
        ' /* x */ String t = """\nhi\n""";'
    )
    assert "".join(text for _, text in split_segments(src)) == src


def test_code_only_blanks_comments_and_strings():
    out = code_only('a // c\n"Math.random()" b')
    assert "Math" not in out
    assert out.count("\n") == 1


def test_math_random_replaced():
    out = rewrite_source("double d = Math.random() * 6;").source
    assert out == f"double d = {SHARED}.nextDouble() * 6;"


def test_fully_qualified_math_random():
    out = rewrite_source("double d = java.lang.Math.random();").source
    assert out == f"double d = {SHARED}.nextDouble();"


def test_strings_and_comments_untouched():
    src = 'System.out.println("Math.random()"); // new Random()\n'
    assert rewrite_source(src).source == src


def test_new_random_with_and_without_seed():
    src = (
        "Random a = new Random(); Random b = new Random(7);"
        " Random c = new java.util.Random(System.nanoTime());"
    )
    out = rewrite_source(src).source
    assert out == f"Random a = {SHARED}; Random b = {SHARED}; Random c = {SHARED};"


def test_secure_random_not_rewritten_but_noted():
    result = rewrite_source("Random r = new SecureRandom();")
    assert "SecureRandom()" in result.source
    assert any("SecureRandom" in n for n in result.notes)


def test_shuffle_one_arg_gets_shared_random():
    out = rewrite_source("Collections.shuffle(list); Collections.shuffle(list, r);").source
    assert out == f"Collections.shuffle(list, {SHARED}); Collections.shuffle(list, r);"


def test_package_and_own_imports_removed_keeping_lines():
    src = "package a.b;\nimport a.b.Helper;\nimport java.util.*;\nclass X {}\n"
    result = rewrite_source(src)
    assert "package" not in result.source
    assert "a.b.Helper" not in result.source
    assert "import java.util.*;" in result.source
    assert result.source.count("\n") == src.count("\n")


def test_student_random_class_left_alone():
    out = rewrite_source("Random r = new Random();", seed_random_class=False).source
    assert out == "Random r = new Random();"
