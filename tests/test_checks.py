import subprocess

import pytest

from negentropy import engine, messages
from negentropy.cli import main
from negentropy.codebase import Codebase
from negentropy.config import Config
from negentropy.rules import Rulebook

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
    return {(f.path, f.line, f.check) for f in engine.findings(Codebase(root))}


def test_a_comment_fails_and_what_a_tool_or_a_source_needs_stays(repo):
    write(repo, COMMENTED)
    assert found(repo) == {
        ("report.py", 3, "comment"),
        ("Dialog.svelte", 2, "comment"),
        ("Dialog.svelte", 5, "comment"),
        ("Dialog.svelte", 7, "comment"),
        ("ci.yml", 1, "comment"),
        ("join.sh", 2, "comment"),
        ("solver.rs", 3, "doc-comment"),
        ("solver.rs", 4, "comment"),
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
        return [finding.check for finding in messages.of_text(book, "commit", "commit message", message)]

    book = Rulebook.load(repo, Config())

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
    assert [f.check for f in messages.of_history(book, repo, "main..HEAD")] == ["commit-message"]


def test_the_report_is_a_checklist_in_the_order_to_fix(repo, monkeypatch, capsys):
    write(repo, {"a.py": "x = 1  # why\n# and\n# more\ny = 2\n# again\n", "PLAN.md": "plan\n"})
    monkeypatch.chdir(repo)
    assert main([]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("negentropy: 3 findings (markdown 1, comment 2)\n\n# 1. Remove\n")
    assert "\n## markdown (1)\n" in printed and "\n- [ ] PLAN.md:1\n" in printed
    assert printed.index("# 1. Remove") < printed.index("# 5. Text") < printed.index("## comment (2)")
    assert printed.endswith("\n- [ ] a.py:1-3\n- [ ] a.py:5\n")

    assert main(["next"]) == 1
    first = capsys.readouterr().out
    assert "## markdown (1)" in first and "## comment" not in first
    assert first.endswith("The later phases have 2 more findings. Run `negentropy next` again when this phase is clean.\n")

    write(repo, {"a.py": "x = 1\n"})
    (repo / "PLAN.md").unlink()
    assert main([]) == 0
    assert capsys.readouterr().out == "negentropy: clean\n"


SWITCHES = (
    "#![allow(unused_variables)]\n"
    "pub const A: f64 = 1.0;\n"
    "#[allow(dead_code)]\n"
    "fn old_path() {}\n"
    "#[allow(clippy::too_many_arguments)]\n"
    "fn lib() -> bool { std::env::var(\"SOLVER_PATH\").is_ok() }\n"
)


def test_library_code_reads_no_environment_and_keeps_no_dead_code(repo):
    write(repo, {"src/lib.rs": SWITCHES, "src/main.rs": "fn main() { let _ = std::env::var(\"X\"); }\n",
                 "src/settings.py": "import os\nMODE = os.environ.get(\"MODE\")\n"})
    assert found(repo) == {
        ("src/lib.rs", 1, "dead-code"),
        ("src/lib.rs", 3, "dead-code"),
        ("src/lib.rs", 6, "environment"),
        ("src/settings.py", 2, "environment"),
    }


def test_a_count_is_the_one_the_repository_declares(repo):
    files = {
        "src/constants.rs": "pub const A: f64 = 1.0;\npub const B: f64 = 2.0;\nstatic C: u32 = 3;\n",
        "src/constants.py": "TOL = 1.0\nlower = 2\n",
        "src/lib.rs": "const ELSEWHERE: u32 = 1;\n",
        "Cargo.toml": "[features]\ndefault = [\"fast\"]\nfast = []\nslow = []\n",
    }
    write(repo, {**files, "negentropy.toml": "[budget]\nconstants = 4\nfeatures = 2\n"})
    assert found(repo) == set()
    write(repo, {"negentropy.toml": "[budget]\nconstants = 3\nfeatures = 3\n"})
    findings = engine.findings(Codebase(repo))
    assert {(f.path, f.line, f.detail) for f in findings} == {
        ("negentropy.toml", 2, "constants: 4 in the codebase, 3 declared"),
        ("negentropy.toml", 3, "features: 2 in the codebase, 3 declared"),
    }


NORM = (
    "pub fn norm(values: &[f64]) -> f64 {\n"
    "    let mut sum = 0.0;\n"
    "    for value in values {\n"
    "        sum += value * value;\n"
    "    }\n"
    "    sum.sqrt()\n"
    "}\n"
)
NORM_AGAIN = (
    "fn length(xs: &[f64]) -> f64 {\n"
    "    let mut acc = 0.0;\n"
    "    for x in xs {\n"
    "        acc += x * x;\n"
    "    }\n"
    "    acc.sqrt()\n"
    "}\n"
)
MEAN = (
    "fn mean(xs: &[f64]) -> f64 {\n"
    "    let mut acc = 0.0;\n"
    "    for x in xs {\n"
    "        acc += x;\n"
    "    }\n"
    "    acc / xs.len() as f64\n"
    "}\n"
)


def test_a_function_written_a_second_time_points_at_the_first(repo):
    write(repo, {"src/dense.rs": NORM, "tests/refine.rs": NORM_AGAIN + MEAN, "src/short.rs": "fn a() -> u8 { 1 }\nfn b() -> u8 { 1 }\n"})
    findings = [f for f in engine.findings(Codebase(repo)) if f.check == "duplicate"]
    assert [(f.path, f.line, f.detail) for f in findings] == [("tests/refine.rs", 1, "identical to src/dense.rs:1")]


OWN_RULE = """name: no-effect
message: >-
  useEffect in product code. Derive the value while rendering, or use the data layer.
not_in: [test]
select:
  - language: [typescript, tsx]
    rule:
      kind: identifier
      regex: '^useEffect$'
      inside:
        kind: call_expression
"""


def test_a_repository_adds_a_check_of_its_own_as_a_file(repo):
    write(repo, {"tools/checks/no-effect.yml": OWN_RULE, "negentropy.toml": 'rules = ["tools/checks"]\n',
                 "web/App.tsx": "export function App() {\n  useEffect(() => {}, []);\n  return null;\n}\n",
                 "web/App.test.tsx": "useEffect(() => {}, []);\n"})
    assert found(repo) == {("web/App.tsx", 2, "no-effect")}


def test_the_repository_allows_an_exception_in_its_configuration(repo):
    library = (
        "pub fn color() -> bool { std::env::var_os(\"NO_COLOR\").is_none() }\n"
        "pub fn mode() -> bool { std::env::var_os(\"SOLVER_MODE\").is_some() }\n"
    )
    write(repo, {"src/lib.rs": library, "negentropy.toml": "[allow]\nenvironment = [\"NO_COLOR\"]\n"})
    assert found(repo) == {("src/lib.rs", 2, "environment")}


INTERNAL_DOCS = (
    "enum State {\n"
    "    /// Not decided yet.\n"
    "    Undecided,\n"
    "}\n"
    "pub enum Level {\n"
    "    /// Shown to everybody.\n"
    "    Info,\n"
    "}\n"
    "thread_local! {\n"
    "    /// The counts of this thread.\n"
    "    static COUNTS: u32 = 0;\n"
    "}\n"
)


def test_a_doc_comment_inside_a_private_enum_or_a_thread_local_is_internal(repo):
    write(repo, {"src/lib.rs": INTERNAL_DOCS})
    assert found(repo) == {("src/lib.rs", 2, "doc-comment"), ("src/lib.rs", 10, "doc-comment")}


def test_a_poisoned_lock_may_panic_and_a_test_file_beside_the_code_is_a_test(repo):
    write(repo, {
        "src/cache.rs": (
            "fn held(cache: &std::sync::Mutex<Vec<u8>>, table: &std::sync::RwLock<Vec<u8>>) -> usize {\n"
            "    let stored = cache.lock().unwrap().len();\n"
            "    let read = table\n"
            "        .read()\n"
            "        .unwrap()\n"
            "        .len();\n"
            "    stored + read + table.write().expect(\"not poisoned\").pop().unwrap() as usize\n"
            "}\n"
        ),
        "src/cache_tests.rs": "fn check() { assert_eq!(Some(1).unwrap(), 1); }\n",
    })
    assert found(repo) == {("src/cache.rs", 7, "unwrap")}


def test_a_safety_comment_stays_only_directly_before_unsafe_code(repo):
    write(repo, {"src/bytes.rs": (
        "fn read(p: *const u8) -> u8 {\n"
        "    // SAFETY: the caller passes a pointer\n"
        "    // that stays valid for the whole call.\n"
        "    let first = unsafe { *p };\n"
        "    // SAFETY: nothing of that kind follows this line.\n"
        "    let second = first;\n"
        "    // SAFETY: the pointer is still valid.\n"
        "    // The unsafe keyword appears only in this comment.\n"
        "    second\n"
        "}\n"
        "// SAFETY: the bytes are plain data.\n"
        "unsafe impl Send for Bytes {}\n"
    )})
    assert found(repo) == {
        ("src/bytes.rs", 5, "comment"),
        ("src/bytes.rs", 7, "comment"),
        ("src/bytes.rs", 8, "comment"),
    }


def test_a_commit_may_keep_the_findings_of_its_parent_but_not_add_one(repo, monkeypatch, capsys):
    write(repo, {"a.py": "x = 1  # why\n", "b.py": "y = 2\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Start")
    monkeypatch.chdir(repo)
    assert main(["check", "--against", "HEAD"]) == 0
    assert capsys.readouterr().out == "negentropy: no check has more findings than at HEAD (comment 1)\n"

    write(repo, {"b.py": "y = 2  # because\n"})
    assert main(["check", "--against", "HEAD"]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("negentropy: these checks have more findings than at HEAD: comment 2 (1 at HEAD). ")
    assert "- [ ] b.py:1" in printed and "a.py" not in printed

    write(repo, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    assert main(["check", "--against", "HEAD"]) == 0
    assert capsys.readouterr().out == "negentropy: clean\n"
