import subprocess

import pytest

from negentropy import checks
from negentropy.checks import commits
from negentropy.cli import main
from negentropy.codebase import Codebase

EM_DASH = chr(0x2014)
SHARP_S = chr(0xDF)

COMMENTED = {
    "report.py": (
        "import os\n"
        "for key in READING:\n"
        "    # A run with more than one container is the sum of them.\n"
        "    into[key] += reading[key]\n"
        "value = compute()  # type: ignore[arg-type]\n"
        "# https://example.org/issues/1 names the container this way\n"
    ),
    "Dialog.svelte": (
        "<script lang=\"ts\">\n"
        "  // the panel never grows past the window\n"
        "  export let open = false;\n"
        "</script>\n"
        "<!-- body -->\n"
        "<style>\n"
        "  /* Wrapped rather than scrolled: a scrolled line hides its end. */\n"
        "  pre { white-space: pre-wrap; }\n"
        "</style>\n"
    ),
    "ci.yml": "# Only when the package or this file changed.\nname: CI\n",
    "join.sh": "#!/bin/sh\n# the address may have been another machine's\necho joining\n",
    "solver.rs": (
        "// SAFETY: the pointer is checked above\n"
        "/// Solves the system.\n"
        "pub fn solve() {}\n"
        "/// Picks the pivot.\n"
        "fn pivot() {} // partial pivoting\n"
    ),
    "api.py": (
        "\"\"\"The public module.\"\"\"\n"
        "def run():\n"
        "    \"\"\"Runs it.\"\"\"\n"
        "def _helper():\n"
        "    \"\"\"Helps.\"\"\"\n"
    ),
}

SOLVER = (
    "const TOL: f64 = 1e-9;\n"
    "fn lib(x: f64) -> f64 {\n"
    "    let v: Option<f64> = None;\n"
    "    println!(\"x\");\n"
    "    if x == 0.0 || x < 1e-12 { return v.unwrap(); }\n"
    "    v.expect(\"set\") * 1e3 * 0.25\n"
    "}\n"
    "#[cfg(test)]\n"
    "mod tests {\n"
    "    #[test]\n"
    "    fn the_solution_matches_the_stored_one() {\n"
    "        let expected = 0.482917345123;\n"
    "        let load = 1e-9;\n"
    "        assert!((super::lib(load) - expected).abs() < 1e-6);\n"
    "        assert_eq!(super::lib(2.0), 2.0);\n"
    "        println!(\"{}\", Some(1).unwrap());\n"
    "    }\n"
    "}\n"
)

PYTHON_TEST = (
    "import pytest\n"
    "def test_the_solution_matches_the_stored_one():\n"
    "    assert abs(f(1.0) - 0.482917345123) < 1e-6\n"
    "def test_reciprocity():\n"
    "    load = 1e-9\n"
    "    assert f(load) == pytest.approx(2.0, rel=TOLERANCE)\n"
)


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


def write(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    return tmp_path


def found(root):
    return {(f.path, f.line, f.check) for f in checks.codebase_findings(Codebase(root))}


def test_a_comment_fails_and_what_a_tool_or_a_source_needs_stays(repo):
    write(repo, COMMENTED)
    assert found(repo) == {
        ("report.py", 3, "comment"),
        ("Dialog.svelte", 2, "comment"),
        ("Dialog.svelte", 5, "comment"),
        ("Dialog.svelte", 7, "comment"),
        ("ci.yml", 1, "comment"),
        ("join.sh", 2, "comment"),
        ("solver.rs", 4, "doc-comment"),
        ("solver.rs", 5, "comment"),
        ("api.py", 5, "doc-comment"),
    }


def test_doc_comments_stay_only_where_the_repository_says_its_api_is(repo):
    write(repo, {"api.py": COMMENTED["api.py"], "internal.py": COMMENTED["api.py"],
                 "negentropy.toml": 'public = ["api.py"]\n'})
    assert found(repo) == {
        ("api.py", 5, "doc-comment"),
        ("internal.py", 1, "doc-comment"),
        ("internal.py", 3, "doc-comment"),
        ("internal.py", 5, "doc-comment"),
    }


def test_a_markdown_file_fails_unless_it_is_a_readme_or_listed_content(repo):
    write(repo, {"PLAN.md": "plan\n", "docs/notes.md": "notes\n", "pkg/README.md": "readme\n", "site/page.md": "page\n",
                 "negentropy.toml": 'markdown = ["site/**"]\n'})
    assert found(repo) == {("PLAN.md", 1, "markdown"), ("docs/notes.md", 1, "markdown")}


def test_a_character_outside_ascii_fails_unless_the_project_lists_it(repo):
    write(repo, {"text.txt": f"a dash {EM_DASH} here\nGru{SHARP_S}\n", "data/raw.txt": f"{EM_DASH}\n",
                 "negentropy.toml": f'exempt = ["data/**"]\ncharacters = "\\u00df"\n'})
    assert found(repo) == {("text.txt", 1, "characters")}


def test_a_tolerance_has_a_name_and_library_code_does_not_panic_or_print(repo):
    write(repo, {"src/lib.rs": SOLVER, "src/constants.rs": "pub const TOL: f64 = 1e-9;\n",
                 "src/main.rs": "fn main() { println!(\"x\"); }\n", "scripts/deck.py": "WIDTH = 10e-6\n"})
    assert {entry for entry in found(repo) if entry[1] <= 7} == {
        ("src/lib.rs", 1, "literal"),
        ("src/lib.rs", 4, "print"),
        ("src/lib.rs", 5, "literal"),
        ("src/lib.rs", 5, "unwrap"),
        ("src/lib.rs", 6, "unwrap"),
    }


def test_a_test_that_pins_what_the_code_does_fails(repo):
    snapshot_call = "assert_" + "snapshot!(value);\n"
    write(repo, {"src/lib.rs": SOLVER, "tests/test_solver.py": PYTHON_TEST, "tests/snap.rs": snapshot_call,
                 "Cargo.toml": "[dev-dependencies]\ninsta = \"1\"\n"})
    assert {entry for entry in found(repo) if entry[0] != "src/lib.rs" or entry[1] > 7} == {
        ("src/lib.rs", 12, "pinned-value"),
        ("src/lib.rs", 14, "test-bound"),
        ("tests/test_solver.py", 3, "pinned-value"),
        ("tests/test_solver.py", 3, "test-bound"),
        ("tests/snap.rs", 1, "snapshot"),
        ("Cargo.toml", 2, "snapshot"),
    }


def test_a_check_the_repository_turned_off_reports_nothing(repo):
    write(repo, {"PLAN.md": "plan\n", "a.py": "x = 1  # why\n", "negentropy.toml": 'off = ["markdown"]\n'})
    assert found(repo) == {("a.py", 1, "comment")}


def test_a_commit_message_is_one_line_and_names_no_tool_as_author(repo):
    def named(message):
        return [finding.check for finding in commits.message_findings("commit message", message)]

    assert named("Name the tolerances of the eigenvalue tests") == []
    assert named("Revert \"x\"\n\nThis reverts commit 0123abc.") == []
    assert named("Fix overflow\n\nThe dialog was too tall.") == ["commit-message"]
    assert named("Fix overflow\n\nCo-Authored-By: Claude <noreply@anthropic.com>") == ["commit-message", "attribution"]

    write(repo, {"a.txt": "a\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "One line")
    git(repo, "checkout", "-q", "-b", "work")
    write(repo, {"b.txt": "b\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Two lines\n\nwith a body")
    assert [f.check for f in commits.commit_findings(repo, "main..HEAD")] == ["commit-message"]


def test_the_report_is_a_checklist_with_one_section_per_check(repo, monkeypatch, capsys):
    write(repo, {"a.py": "x = 1  # why\n# and\n# more\ny = 2\n# again\n", "PLAN.md": "plan\n"})
    monkeypatch.chdir(repo)
    assert main([]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("negentropy: 3 to fix (comment 2, markdown 1)\n\n## comment (2)\n")
    assert "\n- [ ] a.py:1-3\n- [ ] a.py:5\n" in printed
    assert "\n## markdown (1)\n" in printed and "\n- [ ] PLAN.md:1" in printed

    write(repo, {"a.py": "x = 1\n"})
    (repo / "PLAN.md").unlink()
    assert main([]) == 0
    assert capsys.readouterr().out == "negentropy: clean\n"
