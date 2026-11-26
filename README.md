# negentropy

Checks that keep a codebase from decaying while agents and people change it.

A codebase is the largest input of the agent that works in it: what is there gets copied. A stale
comment, a number without a name or a test that froze yesterday's behaviour is read as the established
pattern and spreads. A rule in prose holds as long as whoever reads it follows it. A check fails the
change instead, and its message says what to do. negentropy is those checks: one command over the
whole codebase, the same after an edit, at a commit and before a merge.

```
$ negentropy
negentropy: 3 findings (comment 2, test-bound 1)

## comment (2)
A comment in code. Nothing checks a comment, so it goes stale and the next reader trusts it. ...

- [ ] src/solve.rs:41-43
- [ ] web/Modal.svelte:7

## test-bound (1)
A test bound written as a number. ...

- [ ] tests/solve.rs:88
```

The report is a checklist: one section per check with what to do, one line per place. A clean
codebase prints `negentropy: clean` and exits 0.

## Checks

| Check | Fails on |
|---|---|
| `comment` | a comment in code, except a tool directive, a license header, or one with a link to the source of an outside constraint |
| `doc-comment` | a doc comment on an internal item, or outside the paths listed as public API |
| `markdown` | a markdown file that is not a README |
| `characters` | a character outside ASCII and outside the letters the project lists |
| `literal` | a number with a negative exponent in library code outside the constants module: a tolerance or a threshold without a name |
| `test-bound` | such a number inside an assertion: a bound without a name and a source |
| `pinned-value` | a number with more than 7 significant digits in a test: copied from a program's output |
| `snapshot` | a snapshot library, a snapshot assertion or a `.snap` file |
| `unwrap` | `unwrap` or `expect` in Rust library code |
| `print` | `println!`, `eprintln!` or `dbg!` in Rust library code |
| `environment` | an environment variable read in Rust or Python library code |
| `dead-code` | `allow(dead_code)` or `allow(unused...)` outside tests |
| `duplicate` | a function of 25 tokens or more that is another one with its variables renamed |
| `budget` | a count that differs from the one the repository declares: constants in the constants modules, Cargo features |
| `commit-message` | a commit message with more than one line |
| `attribution` | a commit or pull request that names an AI tool as author |

Comments and numbers are found on the syntax tree with [ast-grep](https://ast-grep.github.io), in
Rust, Python, JavaScript, TypeScript, Svelte, CSS, shell and YAML. Tests are found by their path and,
in Rust, by `#[cfg(test)]`.

The 7 digits of `pinned-value` are measured on about 6000 float literals in the tests of three
numerical libraries, counted by significant digits: 56 have 5 to 7, 8 have 8 or 9, and 194 have 10 or
more, most of them 15 to 17, the length of printed output.

The 25 tokens of `duplicate` are measured on the same three libraries (about 10000 functions): 145
surplus copies at 25 tokens, 77 at 40 and 44 at 60. The copies between 25 and 39 tokens were read: helpers
defined twice and the same method on several types.

## Install

```
pipx install git+https://github.com/milanofthe/negentropy
```

## Configure

`negentropy.toml` at the root of a repository. Every key is optional:

```toml
public = ["src/api/**"]
constants = ["**/constants.rs", "**/tuning.rs"]
library = ["**/src/**"]
markdown = ["docs/**"]
exempt = ["vendor/**", "data/**"]
characters = "\u00e4\u00f6\u00fc\u00df"
off = ["attribution"]

[budget]
constants = 40
features = 3
```

- `public`: where doc comments are API documentation. Without it they stay on every item the
  language exports; `[]` says the repository has no public API.
- `constants`: the constants modules (default `**/constants.rs`, `**/constants/**`, `**/constants.py`).
- `library`: the library code (default `**/src/**`).
- `markdown`: markdown that is content.
- `exempt`: what no check reads.
- `characters`: letters allowed besides ASCII.
- `off`: checks the repository does not use.
- `rules`: directories with the repository's own checks.
- `budget`: what the codebase has of a countable thing. No check can say whether one more tuning
  constant is needed, so the count is declared here and a change of it is a change of this file.
  With the repository's owner as code owner of `negentropy.toml`, an agent cannot raise it alone.

## Run

After every edit of a coding agent, so the finding arrives while the change is in its context. For
Claude Code, in `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "sh <clone>/hooks/agent" }] }
    ]
  }
}
```

At every commit, on a machine, for each repository with a `negentropy.toml`:

```
git config --global core.hooksPath <clone>/hooks
```

Before a merge, in CI:

```yaml
jobs:
  negentropy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: milanofthe/negentropy@main
```

## Rules are data

A check is a YAML file: what it selects, where it applies, and the message that says what to do.

```yaml
name: literal
message: >-
  A tolerance or a threshold written as a number in library code. ...
matches: '[eE]-\d'
in: [library]
not_in: [test, constants]
select:
  - language: rust
    rule:
      kind: float_literal
  - language: python
    rule:
      kind: float
```

A selector picks by one of four things: `rule`, an [ast-grep rule](https://ast-grep.github.io/guide/rule-config.html)
for one or more languages; `line`, a regular expression over the lines of the files; `file`, a path
pattern; `keys`, the keys of a TOML table. `matches`, `unless`, `digits_over` and `digits_up_to`
narrow by the selected text, `in` and `not_in` by scope. The scopes (`test`, `assertion`, `library`,
`constants`, `public`, `binary`, `manifest`, `readme`, `content`) are data as well, in
`src/negentropy/base.yml`.

A check has one of three kinds. `each`: every selected place is a finding. `unique`: a selected
place that repeats another one is a finding (`duplicate`). `count`: the number of selected places
equals the number the repository declares (`budget`).

The built-in checks are the files in `src/negentropy/checks`. A repository adds its own in the same
form and lists the directory in `negentropy.toml`:

```toml
rules = ["tools/checks"]
```

```yaml
name: no-effect
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
```

A language ast-grep parses is added to a check as one more entry under `select`.

## A new check

The order is: make the mistake impossible by structure, then by a type, then by a check whose
message names what to do, then by a test. A check is one file, and a test in `tests` shows it
failing on the mistake it is for. `skills/correct` is the procedure for an agent: from a correction
that came twice to a check.

negentropy checks its own repository.
