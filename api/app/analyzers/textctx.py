"""Single-line lexical context for the regex analyzers.

Answers two questions about a position on one added line: is the offset inside a
string literal, and where (if anywhere) does an inline comment begin? The regex
analyzers (SQG003 placeholders, SQG006 SAST) use this to avoid firing on a marker
or sink that lives inside string data or a commented-out mention rather than in
real code.

MVP scope, deliberately: single-line only. No triple-quoted / multi-line string
state is tracked — the same boundary the diff-line analyzers already work within.
"""

_PY_EXT = (".py",)
_JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def lang_for(path: str) -> str:
    """Map a file path to a lexer dialect: 'python', 'js', or 'generic'."""
    low = path.lower()
    if low.endswith(_PY_EXT):
        return "python"
    if low.endswith(_JS_EXT):
        return "js"
    return "generic"


def inside_string_literal(line: str, index: int, lang: str = "generic") -> bool:
    """True if ``index`` sits inside a '...' / "..." (or `...` for js) string literal.

    Scans the line up to ``index``, toggling string state on unescaped quotes. A
    backslash escapes the next character (so ``"a\\"b"`` stays one string).
    """
    quote = None
    backtick = lang == "js"
    i = 0
    while i < index and i < len(line):
        c = line[i]
        if quote is None:
            if c in ('"', "'") or (backtick and c == "`"):
                quote = c
        elif c == "\\":
            i += 1  # skip the escaped character
        elif c == quote:
            quote = None
        i += 1
    return quote is not None


def inside_block_comment(line: str, index: int, lang: str = "generic") -> bool:
    """True if ``index`` sits inside a ``/* ... */`` span that starts AND ends on
    this line (single-line MVP scope, like the rest of this module — a block
    comment spanning multiple lines isn't tracked). Without this, a sink
    mentioned in a self-contained one-line block comment (e.g. an old approach
    left as documentation) reads as a live call site.

    Only meaningful for ``lang in ("js", "generic")`` — Python has no ``/* */``.
    """
    if lang == "python":
        return False
    quote = None
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        if quote is not None:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in ('"', "'") or (lang == "js" and c == "`"):
            quote = c
        elif c == "/" and i + 1 < n and line[i + 1] == "*":
            end = line.find("*/", i + 2)
            if end == -1:
                return False  # unterminated on this line — not self-contained, don't guess
            if i <= index < end + 2:
                return True
            i = end + 1
        i += 1
    return False


def comment_start(line: str, lang: str = "generic") -> int:
    """Index where an inline comment begins (``#`` for python, ``//`` for js), or -1.

    Quote-aware, so a ``#`` or ``//`` appearing inside a string literal is not
    mistaken for the start of a comment.
    """
    quote = None
    backtick = lang == "js"
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        if quote is None:
            if c in ('"', "'") or (backtick and c == "`"):
                quote = c
            elif lang == "python" and c == "#":
                return i
            elif lang == "js" and c == "/" and i + 1 < n and line[i + 1] == "/":
                return i
        elif c == "\\":
            i += 1  # skip the escaped character
        elif c == quote:
            quote = None
        i += 1
    return -1
