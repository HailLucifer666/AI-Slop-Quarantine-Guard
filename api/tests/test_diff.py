"""Test unified-diff parsing into added lines with correct new-file line numbers."""

from app.diff import parse_diff

SAMPLE = """\
diff --git a/app/foo.py b/app/foo.py
index 111..222 100644
--- a/app/foo.py
+++ b/app/foo.py
@@ -1,3 +1,4 @@
 import os
+import quantumllm_helper
 x = 1
-y = 2
+y = 3
diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+hello
+world
"""


def test_added_lines_and_numbers():
    added = parse_diff(SAMPLE)
    # foo.py: line 2 import (new), line 4 y=3 ; new.txt: lines 1,2
    assert ("app/foo.py", 2, "import quantumllm_helper") in added
    assert ("app/foo.py", 4, "y = 3") in added
    assert ("new.txt", 1, "hello") in added
    assert ("new.txt", 2, "world") in added


def test_removed_lines_ignored():
    added = parse_diff(SAMPLE)
    assert all(content != "y = 2" for _f, _l, content in added)


def test_only_added_returned():
    added = parse_diff(SAMPLE)
    # 4 added lines total
    assert len(added) == 4


def test_empty_diff():
    assert parse_diff("") == []
