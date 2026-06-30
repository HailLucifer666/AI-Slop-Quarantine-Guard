"""Single-line lexer used by SQG003/SQG006 to skip strings and inline comments."""

from app.analyzers.textctx import comment_start, inside_string_literal, lang_for


# --- lang_for --------------------------------------------------------------

def test_lang_for_maps_extensions():
    assert lang_for("app/x.py") == "python"
    assert lang_for("src/c.tsx") == "js"
    assert lang_for("server.mjs") == "js"
    assert lang_for("config.yaml") == "generic"


# --- inside_string_literal -------------------------------------------------

def test_offset_inside_double_quote():
    line = 'msg = "TODO: later"'
    assert inside_string_literal(line, line.index("TODO"))


def test_offset_inside_single_quote():
    line = "x = 'FIXME here'"
    assert inside_string_literal(line, line.index("FIXME"))


def test_offset_outside_string():
    line = "result = eval(user_input)"
    assert not inside_string_literal(line, line.index("eval"))


def test_js_backtick_is_string_only_for_js():
    line = "const s = `eval(x)`"
    assert inside_string_literal(line, line.index("eval"), "js")
    # In python dialect a backtick is not a string delimiter, so the same offset
    # reads as code (python has no backtick strings).
    assert not inside_string_literal(line, line.index("eval"), "python")


def test_escaped_quote_keeps_one_string():
    # The escaped \" must not close the string early, so the tail stays inside it.
    line = 'k = "a\\"b TODO"'
    assert inside_string_literal(line, line.index("TODO"))


# --- comment_start ---------------------------------------------------------

def test_comment_start_python():
    line = "x = 1  # eval(y) is unsafe"
    assert comment_start(line, "python") == line.index("#")


def test_comment_start_js():
    line = "let x = 1; // eval(y)"
    assert comment_start(line, "js") == line.index("//")


def test_hash_inside_string_is_not_a_comment():
    line = 'color = "#ffffff"  # real comment'
    # The first # is inside the string; the returned index must be the trailing one.
    assert comment_start(line, "python") == line.rindex("#")


def test_no_comment_returns_minus_one():
    assert comment_start("os.system(cmd)", "python") == -1
