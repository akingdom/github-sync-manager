#!/usr/bin/env python3
# filename: git_sync_manager.py
# version 1.1.6

import os
import sys
import subprocess
import argparse
import requests
import time
import logging
import getpass
import shutil
from pathlib import Path

class GitSyncManager:
    def __init__(self):
        self.username = None
        self.token = None
        self.target_dir = None
        self.confirm_all = False
        self.dry_run = False
        self.include_forks = False

        self.remote_repos = []
        self.remote_gists = []
        self.all_remote_repo_names = set()
        self.all_remote_gist_names = set()

        self.local_repos = set()
        self.local_gists = set()

        self.log_enabled = True

    # ---------------------------
    # Logging
    # ---------------------------
    def setup_logging(self, no_log):
        self.log_enabled = not no_log

        handlers = [logging.StreamHandler(sys.stdout)]

        if not no_log:
            log_file = Path("git_sync.log").resolve()
            handlers.append(logging.FileHandler(log_file))
            print(f"Logging initialized: {log_file}")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers,
            force=True   # FIX: ensure re-init works
        )

    def log(self, message, level="info"):
        level_map = {
            "info": logging.info,
            "warn": logging.warning,
            "warning": logging.warning,
            "error": logging.error
        }

        if not self.log_enabled:
            print(message)
            return

        log_func = level_map.get(level, logging.info)
        log_func(message)

    # ---------------------------
    # CLI / Input
    # ---------------------------
    def get_parameters(self):
        parser = argparse.ArgumentParser(description="GitHub Repo + Gist Sync Tool")

        parser.add_argument("--user", help="GitHub Username")
        parser.add_argument("--token", help="GitHub Personal Access Token")
        parser.add_argument("--dir", help="Target local directory")
        parser.add_argument("--action", choices=['R', 'T', 'C', 'U', 'D', 'Q'], help="Default action")
        parser.add_argument("--confirm", action="store_true", help="Skip countdowns")
        parser.add_argument("--no-log", action="store_true", help="Disable file logging")
        parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
        parser.add_argument("--include-forks", action="store_true", help="Include forked repositories")

        args, _ = parser.parse_known_args()
        self.setup_logging(args.no_log)

        print("\n--- Parameter Check ---")
        
        if args.user: print(f"User: {args.user}")
        self.username = args.user or input("GitHub Username: ")

        if args.dir: print(f"Target Directory: {args.dir}")
        self.target_dir = Path(args.dir or input("Target local path: ")).expanduser().resolve()
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.token = args.token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            self.log("No token detected in environment → public-only mode", "warn")
            token_input = getpass.getpass("Token (optional): ")
            self.token = token_input.strip() or None

        self.log("Authenticated mode enabled" if self.token else "Public-only mode")

        self.confirm_all = args.confirm
        self.dry_run = args.dry_run
        self.include_forks = args.include_forks

        # Only Gists get a subdirectory
        (self.target_dir / "gists").mkdir(exist_ok=True)

        return args.action

    # ---------------------------
    # API & State
    # ---------------------------
    def fetch_all_pages(self, url_template):
        results = []
        page = 1
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        while True:
            sep = '&' if '?' in url_template else '?'
            url = f"{url_template}{sep}page={page}&per_page=100"

            try:
                response = requests.get(url, headers=headers, timeout=15)

                if response.status_code == 403:
                    remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
                    if remaining == 0:
                        reset = int(response.headers.get("X-RateLimit-Reset", time.time()+60))
                        sleep_time = max(0, reset - int(time.time()))
                        self.log(f"Rate limit hit. Sleeping {sleep_time}s...", "warn")
                        time.sleep(sleep_time)
                        continue

                response.raise_for_status()
            except Exception as e:
                self.log(f"API error: {e}", "error")
                sys.exit(1)

            data = response.json()
            if not data: break
            results.extend(data)
            page += 1

        return results

    # ---------------------------
    # Sync State
    # ---------------------------
    def sync_state(self):
        self.log("Refreshing state from GitHub...")

        repos = self.fetch_all_pages(f"https://api.github.com/users/{self.username}/repos")
        self.all_remote_repo_names = {r["name"] for r in repos}
        
        # Filter: Skip forks unless --include-forks is used
        self.remote_repos = [
            {"name": r["name"], "url": r["clone_url"], "type": "Repo"} 
            for r in repos if self.include_forks or not r.get("fork")
        ]

        gists = self.fetch_all_pages(f"https://api.github.com/users/{self.username}/gists")
        self.all_remote_gist_names = {g["id"] for g in gists}
        
        self.remote_gists = [{
            "name": g["id"],
            "display": g["description"] or f"Gist {g['id'][:8]}",
            "url": g["git_pull_url"],
            "type": "Gist"
        } for g in gists]

        # Repos in root (excluding 'gists' dir); Gists in subfolder
        self.local_repos = {d.name for d in self.target_dir.iterdir() if d.is_dir() and d.name != "gists"}
        self.local_gists = {d.name for d in (self.target_dir / "gists").iterdir() if d.is_dir()}

        # Warning only, listing happens in Table action
        orphans = (self.local_repos - self.all_remote_repo_names) | (self.local_gists - self.all_remote_gist_names)
        if orphans:
            self.log(f"{len(orphans)} total local orphans found (no remote match)", "warn")

    def display_summary(self):
        repo_names = {r["name"] for r in self.remote_repos}
        gist_names = {g["name"] for g in self.remote_gists}

        repo_missing = repo_names - self.local_repos
        repo_existing = repo_names & self.local_repos

        gist_missing = gist_names - self.local_gists
        gist_existing = gist_names & self.local_gists

        print("\n" + "="*60)
        print(f"USER: {self.username} | {self.target_dir}")
        print(f"REPOS: {len(repo_missing)} to clone | {len(repo_existing)} to update")
        print(f"GISTS: {len(gist_missing)} to clone | {len(gist_existing)} to update")
        print("="*60)

        return repo_missing, repo_existing, gist_missing, gist_existing

    # ---------------------------
    # Git Operations
    # ---------------------------
    def run_git(self, cmd, cwd):
        if self.dry_run:
            self.log(f"[DRY RUN] {' '.join(cmd)} in {cwd}")
            return True

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            result = subprocess.run(cmd, cwd=cwd)
            if result.returncode == 0: return True
            if attempt < max_attempts:
                self.log(f"Git command failed (attempt {attempt}/{max_attempts}), retrying: {' '.join(cmd)}", "warn")
                time.sleep(1)

        self.log(f"Git failure after 3 attempts: {' '.join(cmd)}", "error")
        return False

    def countdown(self):
        if self.confirm_all or self.dry_run:
            return
        print("Starting in 5 seconds (Press Ctrl+C to cancel)...")
        try:
            for i in range(5, 0, -1):
                print(f"{i}...", end=" ", flush=True)
                time.sleep(1)
            print("EXECUTE\n")
        except KeyboardInterrupt:
            print("\nOperation Halted.")
            sys.exit(0)

    def process(self, items, base_dir, mode):
        for i, item in enumerate(items):
            name, url = item["name"], item["url"]
            path = base_dir / name

            # Explicit check for 'gists' repo name collision
            if item["type"] == "Repo" and name.lower() == "gists":
                print("\n" + "!" * 60)
                self.log("CRITICAL SKIP: repo named 'gists'", "error")
                print("!" * 60 + "\n")
                continue

            self.log(f"[{i+1}/{len(items)}] {mode.upper()}: {name}")

            if mode == "clone":
                if path.exists():
                    self.log(f"Path exists, skipping clone: {name}", "warn")
                    continue

                ok = self.run_git(["git", "clone", url, name], base_dir)
                if not ok:
                    self.log(f"Cleaning up failed clone: {name}", "warn")
                    shutil.rmtree(path, ignore_errors=True)

            else:
                if not (path / ".git").exists():
                    self.log(f"Skipping update (not a git repo): {name}", "warn")
                    continue

                dirty = subprocess.run(
                    ["git", "status", "--porcelain"], 
                    cwd=path, 
                    capture_output=True, 
                    text=True
                )
                if dirty.stdout.strip():
                    self.log(f"Skipping (local changes present): {name}", "warn")
                    continue

                upstream = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "@{u}"], 
                    cwd=path, 
                    capture_output=True, 
                    text=True,
                    stderr=subprocess.DEVNULL   # FIX
                )
                if upstream.returncode != 0:
                    self.log(f"Skipping (no upstream branch): {name}", "warn")
                    continue

                ok = self.run_git(["git", "pull", "--ff-only"], path)
                if not ok:
                    self.log(f"FAILED update: {name}", "error")

    # ---------------------------
    # Main Loop
    # ---------------------------
    def run(self, preset_action):
        self.sync_state()

        while True:
            repo_missing, repo_existing, gist_missing, gist_existing = self.display_summary()

            action = preset_action or input(
                "\n[R] Remote List | [T] Table List | [C] Clone | [U] Update | [D] Prune | [Q] Quit\nAction: "
            ).strip().upper()

            if action == 'Q':
                break

            elif action == 'R':
                for r in self.remote_repos: print(f"[Repo] {r['name']}")
                for g in self.remote_gists: print(f"[Gist] {g['display']} ({g['name']})")

            elif action == 'T':
                print(f"\n{'TYPE':<6} {'NAME':<45} STATUS")
                for r in self.remote_repos:
                    s = "NEW" if r["name"] in repo_missing else "LOCAL"
                    print(f"{'Repo':<6} {r['name']:<45} {s}")
                for g in self.remote_gists:
                    s = "NEW" if g["name"] in gist_missing else "LOCAL"
                    print(f"{'Gist':<6} {g['display']:<45} {s}")
                
                # 2. List Local items that have NO remote (Orphans)
                orphan_repos = self.local_repos - self.all_remote_repo_names
                for name in sorted(orphan_repos):
                    print(f"{'Repo':<6} {name:<45} ORPHAN")
                
                orphan_gists = self.local_gists - self.all_remote_gist_names
                for name in sorted(orphan_gists):
                    print(f"{'Gist':<6} {name:<45} ORPHAN")

            elif action == 'D':
                o_repos = sorted(list(self.local_repos - self.all_remote_repo_names))
                o_gists = sorted(list(self.local_gists - self.all_remote_gist_names))
                
                if not o_repos and not o_gists:
                    print("No orphans to prune.")
                    continue
                
                print("\nORPHANS TO REMOVE:")
                for n in o_repos: print(f"  [Repo] {n}")
                for n in o_gists: print(f"  [Gist] {n}")
                
                confirm = input(f"\nType 'DELETE' to confirm removal of {len(o_repos) + len(o_gists)} directories: ")
                if confirm == "DELETE":
                    for n in o_repos:
                        self.log(f"Pruning: {n}"); shutil.rmtree(self.target_dir / n)
                    for n in o_gists:
                        self.log(f"Pruning Gist: {n}"); shutil.rmtree(self.target_dir / "gists" / n)
                    self.sync_state()
                else:
                    print("Action aborted.")

            elif action in ['C', 'U']:
                mode = "clone" if action == 'C' else "update"
                r_targets = repo_missing if mode == "clone" else repo_existing
                g_targets = gist_missing if mode == "clone" else gist_existing

                if not r_targets and not g_targets:
                    print(f"No items to {mode}.")
                else:
                    print(f"\nTargeting {len(r_targets)} repos and {len(g_targets)} gists.")
                    if self.confirm_all or input(f"Proceed with {mode.upper()}? (y/n): ").lower() == 'y':
                        self.countdown()
                        self.process([r for r in self.remote_repos if r["name"] in r_targets], self.target_dir, mode)
                        self.process([g for g in self.remote_gists if g["name"] in g_targets], self.target_dir / "gists", mode)
                        self.sync_state()

            if preset_action:
                break
            
            preset_action = None

if __name__ == "__main__":
    mgr = GitSyncManager()
    mgr.run(mgr.get_parameters())