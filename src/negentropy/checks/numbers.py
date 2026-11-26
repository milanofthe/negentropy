from __future__ import annotations

import re

from negentropy.codebase import Codebase
from negentropy.config import matches
from negentropy.finding import Check, Finding

NEGATIVE_EXPONENT = re.compile(r"[eE]-\d")
HAND_TYPED_DIGITS = 7


def significant_digits(literal: str) -> int:
    mantissa = re.split(r"[eE]", re.sub(r"_|f32$|f64$|[jJ]$", "", literal))[0]
    return len(mantissa.replace(".", "").lstrip("0").rstrip("0"))


def floats(codebase: Codebase):
    return [match for match in codebase.syntax.of_kind("float") if not matches(match.path, codebase.config.constants)]


def literals(codebase: Codebase):
    for match in floats(codebase):
        if NEGATIVE_EXPONENT.search(match.text) and codebase.in_library(match):
            yield Finding("literal", match.path, match.lines[0])


def test_bounds(codebase: Codebase):
    for match in floats(codebase):
        bound = NEGATIVE_EXPONENT.search(match.text) and codebase.syntax.within("assert", match)
        if bound and codebase.in_test(match) and significant_digits(match.text) <= HAND_TYPED_DIGITS:
            yield Finding("test-bound", match.path, match.lines[0])


def pinned_values(codebase: Codebase):
    for match in floats(codebase):
        if significant_digits(match.text) > HAND_TYPED_DIGITS and codebase.in_test(match):
            yield Finding("pinned-value", match.path, match.lines[0])


CHECKS = [
    Check(
        "literal",
        "A tolerance or a threshold written as a number in library code. It has a name in the constants module, "
        "next to where it comes from: a derivation, a measurement, a reference's stated error. "
        "Move it there and use the name.",
        literals,
    ),
    Check(
        "test-bound",
        "A test bound written as a number. A bound comes from the reference's own error or from a derivation "
        "(conditioning, discretisation order, machine epsilon) and has a name in the constants module that says "
        "which. A bound chosen so that the test passes pins what the code does today.",
        test_bounds,
    ),
    Check(
        "pinned-value",
        f"A number with more than {HAND_TYPED_DIGITS} significant digits in a test: it was copied from a program's "
        "output. A reference value is a named constant with its source in the constants module. The code's own "
        "output is no reference: test the contract (a reference, an invariant, the API) or drop the test. "
        "Input data does not need the digits: generate it from a seed or round it.",
        pinned_values,
    ),
]
