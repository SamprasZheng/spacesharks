---
name: spacesharks-push
description: >
  Auto stage + commit + push for the Spacesharks repo. Forces the origin
  remote to SSH (HTTPS hangs on this machine via credential helper), runs
  `git add -A`, generates a smart commit message, and pushes over SSH
  with a 60s hard timeout. Use whenever the user says commit & push,
  sync, push everything, etc. Trigger phrases: "commit and push",
  "push to remote", "spacesharks push", "git push", "sync spacesharks",
  "提交並推送", "推到 github".
---

# /spacesharks-push

The HTTPS git remote hangs on this machine waiting for credential helper
input (we hit this multiple times). This skill forces the SSH remote and
pushes through it cleanly with a hard 60s timeout.

## How to invoke

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-push.ps1
```

With a custom commit message:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-push.ps1 -Message "fix: dashboard layout regression"
```

Dry-run (no commit, no push):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/DOT/spacesharks/scripts/spacesharks-push.ps1 -DryRun
```

## What it does

1. Reads `git remote get-url origin`
2. If it's HTTPS, switches it to `git@github.com:SamprasZheng/spacesharks.git`
3. Runs `git status --short` and shows what'll be staged
4. Runs `git add -A` to stage everything (including new docs / new screenshots
   that aren't gitignored)
5. Builds a commit message — uses `-Message` if supplied, else
   `"chore: sync N file(s) — auto-commit from spacesharks-push.ps1"`
6. Runs `git commit -m "<msg>" --signoff`
7. Spawns `git push origin main` with a 60s hard timeout (kills if it
   hangs — happens occasionally on first push of a session)

## Why SSH not HTTPS

On this machine, `git push` over `https://github.com/...` opens the Git
credential helper and waits for input. There's no auth UI surface from a
non-interactive PowerShell, so the push hangs forever. SSH works because
the user's `~/.ssh/` keys are loaded into the agent and GitHub accepts
them ("Hi SamprasZheng!" on `ssh -T git@github.com`).

We don't paper over auth issues — per the user's memory rules, this script
just uses the path that works and tells you when it doesn't.

## When to use a different approach

- To bypass the script and do it manually:
  `cd D:/DOT/spacesharks && git remote set-url origin git@github.com:SamprasZheng/spacesharks.git && git push origin main`
- To commit only specific files: `git add <files> && git commit -m "..."`
  then `/spacesharks-push -DryRun` to confirm before push
