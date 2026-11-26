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

[budget]
constants = 40
features = 3

[allow]
environment = ["NO_COLOR"]
```

An entry under `allow` is a regular expression for one check. A finding of that check is not
reported if the expression matches its path followed by its source line, for example
`src/sinks.rs: let color = std::env::var_os("NO_COLOR");`. Exceptions belong in this file and not
in the code, so that the owner of the file decides about them.

negentropy can run in three places:

- In CI before a merge: add the step `uses: milanofthe/negentropy@v1.4.1` after a checkout with
  `fetch-depth: 0`.
- At every commit: run `git config --global core.hooksPath <clone>/hooks` once per machine. The hook
  runs `negentropy check --against HEAD`, which accepts a commit if no check has more findings than
  at `HEAD`, so that a cleanup can be committed in steps.
- After every edit by a coding agent: register `sh <clone>/hooks/agent` as a hook of the agent.

negentropy is released under the MIT license.
