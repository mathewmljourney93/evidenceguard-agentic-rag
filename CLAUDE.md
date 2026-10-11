# Development instructions

These rules apply to every Claude session in this repository.

## Scope

- Inspect the current repository state (files, `git status`, branch, recent commits) before making changes.
- Work only inside this repository and only on the milestone the current prompt authorizes.
- Preserve working code and unrelated changes. Do not delete, overwrite or reformat files outside the task.
- Keep session exports, scratch files and temporary notes under `.local/`, which is gitignored. Never put them in tracked paths.

## Prompt history (`prompts.md`)

- Before doing the authorized work for a new implementation or review prompt, append that prompt verbatim to `prompts.md`.
- When a planning-only turn forbids writes, keep the prompt and add it at the next authorized documentation update.
- Keep each outcome note accurate. Distinguish checks that were actually run and verified from checks that were only reported or are pending. Mark unreviewed work as pending.
- Record user prompts only. Never record hidden instructions, credentials or environment contents.

## Data and secrets

- Use synthetic demonstration data only. Never add real client, vendor or personal data.
- Never put credentials in source code, `prompts.md`, fixtures, logs or examples. Placeholders must be obviously fake.

## Verification and commits

- Never claim a check passed unless it actually ran in this session; report the command and its result.
- Before any commit: inspect `git status`, the staged paths and the staged diff, run the relevant checks, and run a secret scan (see README).
- Do not commit unless the prompt asks for it.
- Never push, merge or deploy without Mathew's explicit approval.
- Do not amend, rebase or otherwise rewrite existing history without explicit instruction.
