---
name: correct
description: Turn a correction that came twice into a negentropy check, so the mistake fails the next change instead of being corrected again. Use when the same kind of mistake was corrected a second time, or when asked to add a check.
---

# Correct

A correction given twice is a class of mistake. Change the repository so the next change cannot make it.

Assume the next contributor sees only the files it opened, copies the nearest example and takes the
shortest path that passes. A change that looks right from one file has to be right for the whole
repository.

## Fix the class at the highest level that holds

1. Structure: one owner per piece of state, one supported way per task, internals that cannot be
   imported, the old way deleted so it cannot be copied.
2. Types: the wrong state cannot be written.
3. A check: where wrong code still compiles, a negentropy check whose message names what to do
   instead.
4. A test of the behaviour, where the contract can be stated: a reference, an invariant, the API.
5. Prose in the agent instructions, only for what needs judgment. Nothing fails when it is skipped.

A fix at one level is not repeated at a lower one.

## Add a check

1. Find the mistake in the history: the commits, the review comments, the corrections. Keep two real
   instances.
2. Decide what marks it in the text or on the syntax tree. If the mark needs judgment to apply, the
   check will be wrong half of the time: go back to the levels above.
3. Run the candidate over the codebases it will guard and read what it hits. Keep it only if what it
   hits is the mistake.
4. Write the module in `src/negentropy/checks`: the name, the message, the function. The message
   says what is wrong, why, and what to do instead, in that order. For a structural check, add the
   ast-grep rule in `src/negentropy/rules`.
5. Write the test in `tests` from the two real instances, and one case that must pass.
6. Add the row to the table in the README.

## Report

The class with its two instances, the level chosen, why no higher level held, and what the candidate
hit on real code.
