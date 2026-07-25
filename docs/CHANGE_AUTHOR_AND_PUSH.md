# Changing the Git Author & Pushing from Your Own Email

All commits in this repo were created with:

```
author:  asahu6 <arpit_sahu@intuit.com>
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

If you want the commits attributed to a **different email** (e.g. your personal
GitHub email so they link to your GitHub account and show on your contribution
graph), follow this guide. Nothing has been pushed yet, so rewriting history is
completely safe.

> **Which email should I use?** GitHub matches commits to your account by the
> commit *email*. Use the email registered on the GitHub account you'll push to
> (Settings → Emails). If you want to keep your address private, use the GitHub
> `noreply` email shown there (looks like `12345+username@users.noreply.github.com`).

---

## Step 0 — Set the identity you want future commits to use

Do this first so any *new* commits already use the right identity.

**macOS / Linux (bash/zsh):**
```bash
cd careerforge-ai
git config user.name  "Your Name"
git config user.email "you@example.com"
```

**Windows (PowerShell):**
```powershell
cd careerforge-ai
git config user.name  "Your Name"
git config user.email "you@example.com"
```

> Use `git config --global ...` (add `--global`) if you want this to be your
> default for every repo on the machine, not just this one.

Verify:
```bash
git config user.name
git config user.email
```

---

## Step 1 — Rewrite the author/committer on the EXISTING commits

Pick **one** of the options below.

### Option A — `git filter-repo` (recommended, cleanest)

`git filter-repo` is the modern, safe tool for this.

Install it once:
```bash
# macOS
brew install git-filter-repo
# or via pip (any OS)
pip install git-filter-repo
```

Rewrite every commit whose author/committer email is the old one:
```bash
cd careerforge-ai
git filter-repo --force \
  --email-callback '
    return b"you@example.com" if email == b"arpit_sahu@intuit.com" else email
  ' \
  --name-callback '
    return b"Your Name" if name == b"asahu6" else name
  '
```

This updates BOTH author and committer on all matching commits and keeps the
`Co-Authored-By: Claude Opus 4.8` trailer intact.

> `filter-repo` intentionally removes the `origin` remote after rewriting (a
> safety feature). You re-add it in Step 2.

### Option B — `git rebase` with `--reset-author` (no extra tools)

Works with plain git; good when you don't want to install anything. This
re-authors **all** commits to your currently-configured identity (Step 0).

```bash
cd careerforge-ai
git rebase --root --committer-date-is-author-date \
  --exec 'git commit --amend --no-edit --reset-author'
```

If the rebase pauses, run `git rebase --continue` until it finishes.

> `--reset-author` sets author = your current `user.name`/`user.email` from
> Step 0, so make sure Step 0 is done first.

### Option C — Environment-variable filter (built-in, scriptable)

If you can't install `filter-repo` and prefer a one-shot filter:

```bash
cd careerforge-ai
git -c 'filter-branch.force=1' filter-branch --env-filter '
OLD_EMAIL="arpit_sahu@intuit.com"
NEW_NAME="Your Name"
NEW_EMAIL="you@example.com"
if [ "$GIT_COMMITTER_EMAIL" = "$OLD_EMAIL" ]; then
  export GIT_COMMITTER_NAME="$NEW_NAME"
  export GIT_COMMITTER_EMAIL="$NEW_EMAIL"
fi
if [ "$GIT_AUTHOR_EMAIL" = "$OLD_EMAIL" ]; then
  export GIT_AUTHOR_NAME="$NEW_NAME"
  export GIT_AUTHOR_EMAIL="$NEW_EMAIL"
fi
' --tag-name-filter cat -- --branches --tags
```

(`filter-branch` is older/slower and prints a deprecation warning — that's
expected; it still works. Prefer Option A when you can.)

---

## Step 2 — Verify the rewrite

```bash
cd careerforge-ai
git log --pretty=format:"%h | %an <%ae>" | head
```

Every line should now show your name/email. Also confirm the co-author trailer
survived:
```bash
git log -1 --format='%(trailers:key=Co-authored-by)'
```

---

## Step 3 — Point at YOUR remote and push

Create an **empty** repository on your GitHub (or other host) first — no README,
no .gitignore (this repo already has them).

```bash
cd careerforge-ai

# If a remote already exists (e.g. left over), update it; otherwise add it:
git remote remove origin 2>/dev/null   # ignore error if none
git remote add origin https://github.com/<you>/<your-repo>.git

# optional: use 'main' as the default branch name
git branch -M main

git push -u origin main
```

**Windows (PowerShell)** is identical — the same `git` commands work.

> If you used Option A (`filter-repo`), the `origin` remote was removed by the
> tool — the `git remote add origin ...` above re-adds it, so you're covered.

---

## Step 4 — Authenticating the push

- **HTTPS (simplest):** when `git push` prompts for a password, paste a GitHub
  **Personal Access Token** (Settings → Developer settings → Tokens), not your
  account password. Scope `repo` is enough for a private repo; `public_repo`
  for a public one.
- **GitHub CLI:** `gh auth login` once, then `git push` just works.
- **SSH:** use `git@github.com:<you>/<your-repo>.git` as the remote URL and an
  SSH key added to your account.

> Per the safety rules I follow, I don't enter credentials or push on your
> behalf — you run Steps 1–4 yourself with your own account/token.

---

## Quick reference (the fast path)

```bash
cd careerforge-ai
git config user.name  "Your Name"
git config user.email "you@example.com"

# rewrite existing history to the new identity (needs git-filter-repo):
git filter-repo --force \
  --email-callback 'return b"you@example.com" if email == b"arpit_sahu@intuit.com" else email' \
  --name-callback  'return b"Your Name" if name == b"asahu6" else name'

git remote add origin https://github.com/<you>/<your-repo>.git
git branch -M main
git push -u origin main
```

---

## Notes

- **Nothing is pushed yet**, so rewriting history here has no downside — there
  are no collaborators to disrupt and no remote to force-past.
- The **`Co-Authored-By: Claude Opus 4.8`** trailer is preserved by all three
  options; remove it manually only if you don't want the AI co-attribution.
- If you ever push first and *then* rewrite, you'd need `git push --force-with-lease`.
  Doing the rewrite **before** the first push (as above) avoids that entirely.
- Cross-platform transfer details (git bundle, first-run) are in
  [`TRANSFER_AND_PUSH.md`](TRANSFER_AND_PUSH.md).
