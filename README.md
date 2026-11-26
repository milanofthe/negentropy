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
```

negentropy can run in three places:

- In CI before a merge: add the step `uses: milanofthe/negentropy@v1.0.0` after a checkout with
  `fetch-depth: 0`.
- At every commit: run `git config --global core.hooksPath <clone>/hooks` once per machine.
- After every edit by a coding agent: register `sh <clone>/hooks/agent` as a hook of the agent.

negentropy is released under the MIT license.
