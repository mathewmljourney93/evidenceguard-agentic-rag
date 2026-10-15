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
- Leave implementation and correction work staged and uncommitted until it has been reviewed. Commit only when a prompt explicitly authorizes it.
- Never push, merge or deploy without Mathew's explicit approval.
- Do not amend, rebase or otherwise rewrite existing history without explicit instruction.

## Review handoffs

- An implementation handoff exports the complete staged diff, excluding `prompts.md`, to a UTF-8 `.diff` file under the gitignored `.local/`, written directly from Git output.
- A correction handoff exports the complete incremental diff against the explicitly recorded, previously reviewed tree or commit, excluding `prompts.md`.
- Never truncate an exported diff or omit source, tests, migrations or configuration from it.
- Do not print complete diffs in chat unless Mathew explicitly asks for it.
- For each exported diff, report the exact file path, the baseline tree or commit, the final tree or commit, the byte size and the SHA-256.
- Keep the response concise: changes, actual verification, Git state and remaining limitations.
- End every handoff with an explicit instruction: Mathew returns either "output only" or "output plus the diff file", naming that file. Implementation and correction reviews require output plus the appropriate diff file.
- If nothing outside `prompts.md` changed, say so; no empty diff file is needed.

## Session management

- Keep the current session through implementation and its immediate reviews and corrections. A milestone boundary alone is not a reason to restart.
- Consider recommending a fresh session after roughly 20 substantial prompts. This is a guideline, not a hard cutoff.
- Recommend an earlier switch only when concrete context or usage evidence, or a large expired-cache warning from Claude Code, makes it worthwhile. Never invent a token count or claim a measured saving.
- When recommending a switch, state it explicitly ("Start a new Claude session before the next task") with the reason.
- Before a necessary switch during unfinished work, give a complete recovery handoff: branch, HEAD, staged and working-tree state, completed work, outstanding work and the next prompt.
- This is guidance, not an interruption: finish the authorized task and its handoff unless a real limit prevents it.
- A new session never authorizes discarding changes or rewriting Git history.
- In a fresh session, read the project instructions and only the relevant files; do not load the whole prompt archive by default.
