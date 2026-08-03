"""Positive fixture: two distinct dangerous sinks on real code lines."""

import subprocess


def run_expression(user_input):
    return eval(user_input)


def run_command(user_input):
    return subprocess.run(user_input, shell=True, capture_output=True)
