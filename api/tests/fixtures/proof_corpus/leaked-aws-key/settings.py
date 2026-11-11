"""Positive fixture: a format-valid AWS access key id committed in source.

Not a real credential — the id is syntactically valid and checksum-shaped so the
detector's format validation fires, but it belongs to no account.
"""

AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7REALKEY"
REGION = "eu-west-1"
