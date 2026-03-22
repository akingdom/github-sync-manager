# GitHub Sync Manager

A robust, safety‑first command‑line tool for synchronizing all GitHub repositories and gists for a given user.  
It supports cloning missing items, updating existing ones, handling rate limits, retrying failed git operations, and avoiding destructive actions on dirty or misconfigured repositories.

This tool is intentionally conservative: it never overwrites local changes, never force‑merges, and always warns about orphaned or mismatched directories.

---

## Features

- 🔄 **Full GitHub sync**  
  Clone missing repositories and gists, update existing ones.

- 🛡️ **Safety‑first design**  
  - Skips dirty repos  
  - Skips repos without upstream branches  
  - Cleans up failed clone attempts  
  - Warns about orphaned local directories  
  - Protects against a repo named `gists` (reserved for gist storage)

- 🔁 **Retry logic for git operations**  
  Automatically retries transient failures up to three times.

- ⏱️ **Rate‑limit aware**  
  Automatically waits for GitHub API reset when necessary.

- 🧪 **Dry‑run mode**  
  Shows all git commands without executing them.

- 📝 **Optional file logging**  
  Logs to both console and `git_sync.log` unless `--no-log` is used.

- 🔐 **Secure token handling**  
  Uses `getpass` to avoid exposing tokens in terminal history.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-username>/github-sync-manager
cd github-sync-manager
```

Run the script with Python 3.8+:

```bash
python sync.py
```

---

## Usage

You can run the tool interactively or provide parameters up front.

### **Interactive Mode**

```bash
python sync.py
```

You will be prompted for:

- GitHub username  
- Target directory  
- Optional token  
- Action to perform  

### **Preset / Non‑Interactive Mode**

```bash
python sync.py --user alice --dir ~/github --action C --confirm
```

Common flags:

| Flag | Meaning |
|------|---------|
| `--user` | GitHub username |
| `--token` | Personal Access Token (optional) |
| `--dir` | Target directory |
| `--action` | `R` list, `T` table, `C` clone, `U` update, `Q` quit |
| `--confirm` | Skip countdowns |
| `--no-log` | Disable file logging |
| `--dry-run` | Show git commands without executing |

---

## Directory Structure

```
target_dir/
    repo1/
    repo2/
    ...
    gists/
        <gist-id-1>/
        <gist-id-2>/
```

Repositories live in the root of the target directory.  
Gists are stored under the reserved name `gists/` to avoid naming collisions.

---

## Notes

- The tool never force‑merges or overwrites local work.
- If a repo or gist exists locally but not remotely, a warning is shown.
- If a repo named `gists` exists remotely, it is skipped to avoid breaking the directory structure.

---

## License

MIT License.

---

## Contributing

Pull requests are welcome.  
Please ensure changes preserve the tool’s safety‑first philosophy.
