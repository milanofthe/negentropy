---
name: correct
description: Turns a mistake that was corrected twice into a negentropy check, so that the next change with this mistake fails. Use this skill when the same kind of mistake has been corrected a second time, or when you are asked to add a check.
---

# Correct

When the same correction has been given twice, treat the mistake as a class of mistakes. Change the
repository so that the next change cannot make this mistake.

Assume that the next contributor reads only the files it opens, copies the nearest example and takes
the shortest path that passes. A change that looks correct from one file must be correct for the
whole repository.

## Fix the class at the highest level that works

Try these levels in order and stop at the first one that prevents the mistake.

1. Structure. Give each piece of state one owner and each task one supported way. Hide internals so
   that they cannot be imported. Delete the old way so that it cannot be copied.
2. Types. Change the types so that the wrong state cannot be written.
3. A check. If wrong code still compiles, add a negentropy check whose message says what to do
   instead.
4. A test. Test the behaviour if you can state the contract, for example a reference solution, an
   invariant or the API.
5. Prose. Add a rule to the agent instructions only if the rule needs judgment, because nothing
   fails when an agent skips it.

Do not repeat a fix at a lower level once a higher level prevents the mistake.

## Add a check

1. Find the mistake in the history, for example in commits, review comments and corrections. Keep
   two real instances of it.
2. Decide which feature of the text or of the syntax tree identifies the mistake. If applying this
   feature needs judgment, the check will produce many false findings. In that case, go back to the
   levels above.
3. Run the candidate check on the codebases that will use it and read the findings. Keep the check
   only if the findings are the mistake.
4. Write the check as one YAML file with a name, a message and selectors. The message must say what
   is wrong, why it is a problem and what to do instead, in this order. If the check applies to every
   codebase, put it into `src/negentropy/checks` and add it to the list in `base.yml`. If it applies
   only to this repository, put it into the directory that `negentropy.toml` lists under `rules`.
5. Write a test from the two real instances and add one case that must pass.

## Report

Report the class of mistake with its two instances, the level that you chose, the reason why no
higher level worked, and the findings of the candidate check on real code.
