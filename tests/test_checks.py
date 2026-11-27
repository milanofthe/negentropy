import re
import subprocess

import pytest

from negentropy import engine, messages
from negentropy.cli import main
from negentropy.codebase import Codebase, export
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
    assert printed.startswith("negentropy: 3 findings (markdown 1, comment 2)\n\nA finding is resolved by the change")
    assert "add an entry `[[reported]]` to negentropy.toml" in printed.split("# 1. Remove")[0]
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

    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Two lines\n\nwith a body")
    assert main(["commits", "HEAD"]) == 1
    assert "A finding is resolved" not in capsys.readouterr().out


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


def test_a_reported_finding_stays_listed_and_does_not_fail(repo, monkeypatch, capsys):
    color = "pub fn color() -> bool { std::env::var_os(\"NO_COLOR\").is_none() }\n"
    mode = "pub fn mode() -> bool { std::env::var_os(\"SOLVER_MODE\").is_some() }\n"
    entry = "[[reported]]\ncheck = \"environment\"\nmatch = 'SOLVER_MODE'\nreason = \"The host sets the variable.\"\n"
    write(repo, {"src/lib.rs": mode})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Start")
    write(repo, {"src/lib.rs": color + mode, "negentropy.toml": entry})
    monkeypatch.chdir(repo)
    assert main([]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("negentropy: 1 findings (environment 1)\n")
    assert "\n- [ ] src/lib.rs:1\n\n# Reported (1)\nThese findings are reported and not resolved." in printed
    assert printed.endswith("\n\n- [ ] src/lib.rs:2  environment: The host sets the variable.\n")

    write(repo, {"src/lib.rs": mode})
    assert main([]) == 0
    assert capsys.readouterr().out.startswith("negentropy: clean\n\n# Reported (1)\n")

    write(repo, {"src/lib.rs": mode + mode})
    assert main(["check", "--against", "HEAD"]) == 0
    assert "\n- [ ] src/lib.rs:1-2  environment: The host sets the variable.\n" in capsys.readouterr().out

    write(repo, {"src/lib.rs": "pub fn mode() -> bool { true }\n"})
    assert main(["check", "--against", "HEAD"]) == 1
    printed = capsys.readouterr().out
    assert "## reported (1)\nThis entry under `reported` in negentropy.toml matches no finding" in printed
    assert printed.endswith("\n- [ ] negentropy.toml:1  environment: SOLVER_MODE\n")

    write(repo, {"negentropy.toml": "[[reported]]\ncheck = \"environment\"\nmatch = 'SOLVER_MODE'\n"})
    assert main([]) == 2


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


def test_the_export_of_a_revision_reads_the_archive_to_its_end(repo, tmp_path_factory):
    record_boundary_sizes = (8192, 18432)
    for size in record_boundary_sizes:
        write(repo, {"wide.txt": "x" * size})
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Start")
        assert export(repo, "HEAD", tmp_path_factory.mktemp("exported")) == ["wide.txt"]


def test_a_constant_keeps_the_doc_that_states_where_its_value_comes_from(repo):
    documented = (
        "/// Measured on the reference machine: a block of 16 runs in 0.15 of the time one by one.\n"
        "const LANES_WIDE: usize = 16;\n"
    )
    write(repo, {"src/constants.rs": documented, "src/tape.rs": documented})
    assert found(repo) == {("src/tape.rs", 1, "doc-comment")}


def test_a_panic_on_a_missing_value_is_an_unwrap_in_another_form(repo):
    write(repo, {"src/lib.rs": (
        "enum Shape { Round, Square }\n"
        "fn first(values: &[u8], found: Option<u8>, parsed: Result<u8, String>, shape: Shape) -> u8 {\n"
        "    let a = match found {\n"
        "        Some(value) => value,\n"
        "        None => unreachable!(\"every item is mapped\"),\n"
        "    };\n"
        "    let b = match parsed {\n"
        "        Ok(value) => value,\n"
        "        Err(error) => panic!(\"invalid: {error}\"),\n"
        "    };\n"
        "    let c = values.first().copied().unwrap_or_else(|| unreachable!(\"not empty\"));\n"
        "    let d = match shape {\n"
        "        Shape::Round => 1,\n"
        "        Shape::Square => unreachable!(\"squares are lowered before\"),\n"
        "    };\n"
        "    let Some(e) = found else { unreachable!() };\n"
        "    assert!(a > 0);\n"
        "    a + b + c + d + e\n"
        "}\n"
    )})
    assert found(repo) == {
        ("src/lib.rs", 5, "unwrap"),
        ("src/lib.rs", 9, "unwrap"),
        ("src/lib.rs", 11, "unwrap"),
        ("src/lib.rs", 16, "unwrap"),
    }


def test_a_name_that_is_a_sentence_fails_unless_it_names_a_test(repo):
    write(repo, {
        "src/solve.rs": (
            "fn solve(depth_keeps_primal_and_derivative_solves_apart: usize) -> usize {\n"
            "    let acc_independent_of_the_kernel_it_folds = depth_keeps_primal_and_derivative_solves_apart;\n"
            "    let single_live_consumer = acc_independent_of_the_kernel_it_folds;\n"
            "    single_live_consumer\n"
            "}\n"
            "#[test]\n"
            "fn a_section_runs_on_its_width_whether_the_workers_spin_or_sleep() {}\n"
        ),
        "tools/device.py": (
            "def device_with_an_expensive_prolog_over_its_parameter(card):\n"
            "    return card\n"
            "def test_the_solution_matches_the_reference_on_every_pool_width():\n"
            "    regions_that_decide_half_of_the_tape_and_more = 1\n"
            "    return regions_that_decide_half_of_the_tape_and_more\n"
        ),
    })
    assert found(repo) == {
        ("src/solve.rs", 1, "long-name"),
        ("src/solve.rs", 2, "long-name"),
        ("tools/device.py", 1, "long-name"),
        ("tools/device.py", 4, "long-name"),
    }


def test_an_item_exported_to_another_language_keeps_its_doc(repo):
    write(repo, {"src/binding.rs": (
        "/// Factors the matrix.\n"
        "#[pyfunction]\n"
        "fn factor(n: usize) -> usize { n }\n"
        "#[pyclass]\n"
        "/// A factorization.\n"
        "struct Factor { n: usize }\n"
        "#[pymethods]\n"
        "impl Factor {\n"
        "    /// The order of the matrix.\n"
        "    #[getter]\n"
        "    fn order(&self) -> usize { self.n }\n"
        "    /// Solves with the factors.\n"
        "    fn solve(&self) -> usize { self.n }\n"
        "}\n"
        "impl Factor {\n"
        "    /// Counts the pivots.\n"
        "    fn pivots(&self) -> usize { self.n }\n"
        "}\n"
        "/// The entry point of the C interface.\n"
        "#[unsafe(no_mangle)]\n"
        "extern \"C\" fn rslab_order(n: usize) -> usize { n }\n"
    )})
    assert found(repo) == {("src/binding.rs", 16, "doc-comment")}


def test_two_stubs_with_one_signature_are_not_a_duplicate(repo):
    write(repo, {"stubs/solver.pyi": (
        "class Lu:\n"
        "    def solve(self, b: object, transpose: bool = False, conjugate: bool = False) -> object: ...\n"
        "class Ldlt:\n"
        "    def solve(self, b: object, transpose: bool = False, conjugate: bool = False) -> object: ...\n"
    )})
    assert found(repo) == set()


def test_a_thin_forwarder_is_no_duplicate_and_a_gated_test_module_is_test_code(repo):
    write(repo, {"src/solvers.rs": (
        "struct Lu { works: usize }\n"
        "struct Ldlt { works: usize }\n"
        "impl Lu {\n"
        "    fn works(&self, first: usize, second: usize, third: usize, fourth: usize) -> usize { self.count(first, second, third, fourth) }\n"
        "    fn count(&self, first: usize, second: usize, third: usize, fourth: usize) -> usize {\n"
        "        let total = first + second + third + fourth;\n"
        "        total + self.works\n"
        "    }\n"
        "}\n"
        "impl Ldlt {\n"
        "    fn works(&self, first: usize, second: usize, third: usize, fourth: usize) -> usize { self.count(first, second, third, fourth) }\n"
        "    fn count(&self, first: usize, second: usize, third: usize, fourth: usize) -> usize {\n"
        "        let total = first + second + third + fourth;\n"
        "        total + self.works\n"
        "    }\n"
        "}\n"
        "#[cfg(all(test, feature = \"matgen\"))]\n"
        "mod generated {\n"
        "    #[test]\n"
        "    fn the_factor_solves() { assert!((Some(1.0f64).unwrap() - 1.0).abs() < 1e-13); }\n"
        "}\n"
    )})
    assert found(repo) == {
        ("src/solvers.rs", 12, "duplicate"),
        ("src/solvers.rs", 20, "test-bound"),
    }


def test_the_changes_that_can_hide_a_problem_are_listed_for_the_owner(repo, monkeypatch, capsys):
    write(repo, {
        "tests/constants.py": "RESIDUAL = 1e-8\nSIZE = 40\n",
        "tests/test_solve.py": (
            "def test_the_residual_is_small():\n    assert residual() < 1e-6\n"
            "def test_the_work_is_linear():\n    assert work(2 * n) < 3 * work(n)\n"
            "def test_the_names_differ():\n    assert solve(first) == solve(second)\n"
            "def test_the_literal_gets_a_name():\n    assert error() < 1e-8\n"
        ),
        "src/lib.rs": "pub fn first(values: &[f64]) -> f64 { values[0] }\n",
    })
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Start")
    monkeypatch.chdir(repo)
    assert main(["changes", "HEAD"]) == 0
    assert capsys.readouterr().out == "negentropy: no changes since HEAD that the owner needs to review\n"

    write(repo, {
        "tests/constants.py": "RESIDUAL = 1e-4\nSIZE = 40\nLOOSE = 1.25e-1\n",
        "tests/test_solve.py": (
            "from constants import LOOSE, RESIDUAL\n"
            "def test_the_residual_is_small():\n    assert residual() < LOOSE\n"
            "def test_other_names_same_body():\n    assert solve(a) == solve(b)\n"
            "def test_the_literal_gets_a_name():\n    assert error() < RESIDUAL\n"
        ),
        "src/lib.rs": (
            "#[allow(clippy::missing_safety_doc)]\n"
            "pub fn first(values: &[f64]) -> f64 { unsafe { *values.get_unchecked(0) } }\n"
            "macro_rules! hidden {\n    () => {\n        fn copy() {}\n    };\n}\n"
        ),
        "negentropy.toml": "exempt = [\"vendor/**\"]\n[allow]\nprint = ['^src/log\\.rs: ']\n",
    })
    assert main(["changes", "HEAD"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith(
        "negentropy: changes since HEAD for the owner to review (removed-test 1, changed-bound 1, "
        "changed-tolerance 2, suppression 1, macro-code 1, unsafe-code 1, exception 2)\n\n"
        "The following changes do not fail a check"
    )
    listed = {line for line in printed.splitlines() if line.startswith("- ")}
    assert listed == {
        "- tests/test_solve.py:3  test_the_work_is_linear",
        "- tests/constants.py:1  RESIDUAL: RESIDUAL = 1e-8 -> RESIDUAL = 1e-4",
        "- tests/test_solve.py:2  test_the_residual_is_small: 1e-6 -> 1.25e-1",
        "- tests/test_solve.py:6  test_the_literal_gets_a_name: 1e-8 -> 1e-4",
        "- src/lib.rs  0 -> 1",
        "- src/lib.rs  0 -> 5 lines",
        "- allow print: ^src/log\\.rs: ",
        "- exempt: vendor/**",
    }


ELIMINATION = (
    "    let mut largest = 0.0;\n"
    "    for (index, &row) in rows.iter().enumerate() {\n"
    "        let pivot = values[index];\n"
    "        let scaled = rhs[row] / pivot;\n"
    "        rhs[row] = scaled;\n"
    "        if scaled.abs() > largest {\n"
    "            largest = scaled.abs();\n"
    "        }\n"
    "        for later in index + 1..rows.len() {\n"
    "            rhs[rows[later]] -= values[later] * scaled;\n"
    "        }\n"
    "    }\n"
)
LOWER = "pub fn lower_solve(rows: &[usize], values: &[f64], rhs: &mut [f64]) -> f64 {\n" + ELIMINATION + "    largest\n}\n"
UPPER = LOWER.replace("lower_solve", "upper_solve").replace("-=", "+=")


def test_a_copy_with_one_difference_is_a_duplicate_unless_it_is_a_test(repo):
    case = "#[test]\nfn lower() {\n    let (rows, values, mut rhs) = system();\n" + ELIMINATION + "    assert!(largest > 0.0);\n}\n"
    write(repo, {
        "src/solve.rs": LOWER + UPPER,
        "tests/solve.rs": case + case.replace("fn lower", "fn upper").replace("-=", "+="),
    })
    findings = engine.findings(Codebase(repo))
    assert [(f.path, f.line, f.check) for f in findings] == [("src/solve.rs", 16, "duplicate")]
    assert re.fullmatch(r"9\d percent identical to src/solve\.rs:1", findings[0].detail)

    short = "pub fn double(values: &mut [f64]) {\n    for value in values.iter_mut() {\n        *value *= 2.0;\n    }\n}\n"
    write(repo, {"src/solve.rs": short + short.replace("double", "halve").replace("2.0", "0.5")})
    assert found(repo) == set()


def test_a_new_function_that_resembles_an_existing_one_is_listed(repo, monkeypatch, capsys):
    write(repo, {"src/lower.rs": LOWER})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Start")
    monkeypatch.chdir(repo)
    write(repo, {"src/upper.rs": UPPER.replace("largest", "greatest").replace("scaled.abs() >", "scaled.norm() >=")})
    assert main(["changes", "HEAD"]) == 0
    listed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("- ")]
    assert len(listed) == 1
    assert re.fullmatch(r"- src/upper\.rs:1  upper_solve: [89]\d percent like lower_solve at src/lower\.rs:1", listed[0])


def test_a_constants_module_keeps_the_derivation_of_its_values_outside_the_public_api(repo):
    write(repo, {
        "src/constants.rs": (
            "//! The bounds of the solver.\n"
            "/// Measured on the reference machine: a block of 16 runs in 0.15 of the time one by one.\n"
            "pub const LANES_WIDE: usize = 16;\n"
            "/// The unit roundoff of f64 in round to nearest, from IEEE 754.\n"
            "static UNIT_ROUNDOFF: f64 = f64::EPSILON / 2.0;\n"
            "/// Higham, Accuracy and Stability, Lemma 3.1: the bound of k rounding errors.\n"
            "pub fn gamma(k: usize) -> f64 {\n"
            "    k as f64 * UNIT_ROUNDOFF / (1.0 - k as f64 * UNIT_ROUNDOFF)\n"
            "}\n"
            "/// A pair of bounds.\n"
            "struct Bounds;\n"
        ),
        "tests/constants.py": (
            "\"\"\"The bounds of the tests.\"\"\"\n"
            "def gamma(k):\n"
            "    \"\"\"Higham, Accuracy and Stability, Lemma 3.1: the bound of k rounding errors.\"\"\"\n"
            "    return k * UNIT_ROUNDOFF / (1 - k * UNIT_ROUNDOFF)\n"
            "class Bounds:\n"
            "    \"\"\"A pair of bounds.\"\"\"\n"
        ),
        "src/tape.rs": "/// Measured on the reference machine.\nconst LANES_WIDE: usize = 16;\n",
        "negentropy.toml": 'public = ["src/api/**"]\n',
    })
    assert {entry for entry in found(repo) if entry[2] == "doc-comment"} == {
        ("src/constants.rs", 1, "doc-comment"),
        ("src/constants.rs", 10, "doc-comment"),
        ("tests/constants.py", 1, "doc-comment"),
        ("tests/constants.py", 6, "doc-comment"),
        ("src/tape.rs", 1, "doc-comment"),
    }


def test_a_method_of_its_own_named_expect_whose_result_is_passed_on_is_no_unwrap(repo):
    write(repo, {"src/parser.rs": (
        "impl Parser {\n"
        "    fn group(&mut self) -> PResult<Expr> {\n"
        "        self.expect(Tok::LParen)?;\n"
        "        let inner = self.expr()?;\n"
        "        self.expect(Tok::RParen)?;\n"
        "        let line = self.lines.next().unwrap()?;\n"
        "        let name = self.names.pop().expect(\"a name is pushed before\")?;\n"
        "        self.expect(Tok::Comma);\n"
        "        Ok(inner)\n"
        "    }\n"
        "}\n"
    )})
    assert found(repo) == {
        ("src/parser.rs", 6, "unwrap"),
        ("src/parser.rs", 7, "unwrap"),
        ("src/parser.rs", 8, "unwrap"),
    }
