---
name: repo-git
description: Handle safe Git workflows for this repository. Use when Codex needs to inspect status, create or switch branches, stage changes intentionally, make scoped commits, compare diffs, push branches, or otherwise perform Git work while avoiding accidental inclusion of unrelated dirty files.
---

# Repo Git

## Overview

Use this skill for Git work in `SortingMachineArray`. The key repo-specific rule is that the working tree may already contain unrelated changes, so scope every branch, staging, and commit action deliberately.

## Default workflow

1. Start by reading the current branch and working tree:
   - `git branch --show-current`
   - `git status --short`
2. Separate the user's requested work from unrelated pre-existing changes before editing or committing.
3. Before creating a branch or commit, briefly tell the user what will be included and what will be left out when the tree is not clean.
4. Stage explicit paths instead of `git add .` whenever unrelated files exist.
5. Verify the staged set before committing:
   - `git diff --staged --stat`
   - `git diff --staged`
6. After committing, report:
   - branch name
   - short commit SHA
   - commit message
   - any remaining unstaged/uncommitted changes

## Task guidance

### Inspecting

- Prefer `git status --short`, `git diff --stat`, and targeted `git diff -- <path>` when orienting.
- If the repo has submodule changes, call that out explicitly; do not silently absorb them into an unrelated commit.

### Branching

- Create a new branch only when it helps isolate work or the user asks for it.
- Use descriptive branch names such as `feature/...`, `fix/...`, or `chore/...`.
- If the current tree is dirty, mention that branch creation does not clean or isolate existing modifications.

### Committing

- Do not collapse all modified files into one commit by default.
- Prefer path-specific staging, then inspect staged diff before commit.
- Use concise commit messages that describe the user-visible change.
- If unrelated files are modified, leave them unstaged and mention them after the commit.

### Pushing

- Push only when the user asks or when a publishing workflow clearly requires it.
- If the branch has no upstream, use `git push -u origin <branch>`.
- If push fails because of auth, remote state, or rejected updates, report the exact reason before attempting anything more invasive.

## Safety rules

- Never run destructive commands such as `git reset --hard`, `git clean -fd`, or force-push unless the user explicitly asks and the consequence is clear.
- Never assume a modified file belongs to the current task just because it is dirty.
- When in doubt about whether a file belongs in the commit, inspect the diff or ask the user before staging it.
- Keep the user oriented: after any non-trivial Git action, say what changed and what remains.

## Typical user requests

- "Create a branch and commit this work."
- "Show me what changed."
- "Commit only the web UI files."
- "Push this branch."
- "What branch am I on, and what is dirty?"
