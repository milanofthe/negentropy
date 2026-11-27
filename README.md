# negentropy

negentropy is a set of checks that keep a codebase from decaying while agents and people change it.

![negentropy runs its checks on a codebase and returns the findings as a checklist](docs/negentropy.svg)

```
pipx install git+https://github.com/milanofthe/negentropy
negentropy
```

The command checks the whole codebase and prints the findings as a checklist. Each check is defined
in a YAML file, which also contains the message that explains how to fix a finding. The built-in
checks are in [src/negentropy/checks](src/negentropy/checks). A repository can add its own checks in
the same format.

The report lists the findings in the order in which they are best fixed, in phases from removing
code to cleaning up comments. For a codebase with many findings, `negentropy next` shows only the
phase to fix next.

Every report of the codebase starts with the terms of the work. A finding is resolved by the change
that its message describes. A change that only hides the code from the check does not resolve it,
and a finding that cannot be resolved is left in place and reported to the owner of the repository.

negentropy reads its configuration from `negentropy.toml` at the root of the repository. All keys are
optional.

```toml
public = ["src/api/**"]
constants = ["**/constants.rs"]
library = ["**/src/**"]
markdown = ["docs/**"]
exempt = ["vendor/**"]
rules = ["tools/checks"]
off = ["attribution"]
characters = "\u00e4\u00f6\u00fc\u00df"

[allow]
environment = ["NO_COLOR"]

[[reported]]
check = "unwrap"
match = '^src/pool\.rs: .*unreachable!'
reason = "The trait erases the result type, so the fix belongs in the crate that defines it."
```

The files under `constants` are the constants modules of the codebase. Without the key, these are
the files `constants.rs` and `constants.py` and the files in a directory `constants`. In a constants
module a doc comment may stay on a constant, a static or a function, also outside the paths under
`public`, so that the measurement or the derivation stands next to the value.

An entry under `allow` is a regular expression for one check. A finding of that check is not
reported if the expression matches its path followed by its source line, for example
`src/sinks.rs: let color = std::env::var_os("NO_COLOR");`. Exceptions belong in this file and not
in the code, so that the owner of the file decides about them.

An entry `[[reported]]` is the answer to a finding that cannot be resolved as its message describes,
or to a check that is wrong about the code. The expression under `match` is read like an entry
under `allow`. A reported finding does not fail the check, and every report lists it with its
reason until the owner has it fixed, corrects the check or moves the entry to `allow`. An entry
that matches no finding is itself a finding. Whoever works on the code may add an entry under
`reported`, while entries under `allow` and `exempt` are the decision of the owner.

`negentropy changes REVISION` lists the changes since a revision that pass every check and can still
hide a problem: tests that were removed, bounds and tolerances of tests that changed, new functions
that resemble an existing one, new
suppressions of lints and tests, more code inside macro definitions, more unsafe code and new
exceptions in negentropy.toml. The command never fails. Its list is for the review of a pull request,
where each of these changes needs a reason.

negentropy runs in two places. It installs no hooks and never runs by itself.

- In CI before a merge: add the step `uses: milanofthe/negentropy@v1.14.0` after a checkout with
  `fetch-depth: 0`. The step writes the report and the list of `negentropy changes` to the summary of
  the run.
- By hand in a checkout: `negentropy check` reports the whole codebase. `negentropy check --against
  origin/main` passes if no check has more findings than at that revision, so that a cleanup can
  proceed in steps. `negentropy commits origin/main..HEAD` checks the commit messages of a branch
  before it is pushed.

negentropy is released under the MIT license.
