#!/usr/bin/env python3
"""
Discord Username Scraper & Availability Checker
A powerful, feature-rich tool for generating random Discord usernames
and checking their availability using Discord's public unauthed endpoint.

Features:
- Random username generation (any length 2-32)
- Multiple generation strategies (pure random, wordlist, patterned)
- Concurrent checking with rate limit handling
- Proxy support (rotating)
- User-Agent rotation
- Resume support & deduplication
- Real-time progress with rich
- Webhook notifications for hits
- Comprehensive logging & stats
- Configurable delays, retries, character sets
- CLI menu with advanced options
- Export results (TXT, CSV, JSON)

WARNING: This tool interacts with Discord's public APIs.
Use responsibly. Excessive use may lead to IP blocks or account issues.
Respect rate limits. Recommended: max 3-5 threads and delays >0.7s

Endpoint used: https://discord.com/api/v9/unique-username/username-attempt-unauthed
"""

import os
import sys
import time
import random
import string
import json
import re
import csv
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

import requests
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich import print as rprint
from rich.logging import RichHandler
from fake_useragent import UserAgent

# ---------------- CONFIG & GLOBALS ----------------
console = Console()
BASE_DIR = Path(__file__).parent.resolve()
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CONFIG_FILE = BASE_DIR / "config.yml"
PROXIES_FILE = BASE_DIR / "proxies.txt"
WORDLIST_FILE = BASE_DIR / "wordlist.txt"
KNOWN_FILE = RESULTS_DIR / "known.txt"
AVAILABLE_FILE = RESULTS_DIR / "available_usernames.txt"
TAKEN_FILE = RESULTS_DIR / "taken_usernames.txt"
STATS_FILE = RESULTS_DIR / "stats.json"
LOG_FILE = BASE_DIR / "scraper.log"

# Discord endpoint
DISCORD_ENDPOINT = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"

# Discord username rules (2023+ pomelo system)
USERNAME_MIN = 2
USERNAME_MAX = 32
ALLOWED_CHARS = set(string.ascii_lowercase + string.digits + "._")

# Global state
config: Dict[str, Any] = {}
proxies: List[str] = []
wordlist: List[str] = []
known_usernames: set = set()
ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# Stats
stats = {
    "total_checked": 0,
    "available": 0,
    "taken": 0,
    "invalid": 0,
    "errors": 0,
    "rate_limits": 0,
    "start_time": None,
    "end_time": None,
}

# ---------------- LOGGING ----------------
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            RichHandler(console=console, rich_tracebacks=True, show_path=False)
        ]
    )
    return logging.getLogger("discord-scraper")

logger = setup_logging()

# ---------------- CONFIG LOADING ----------------
def load_config() -> Dict[str, Any]:
    global config
    default_config = {
        "threads": 5,
        "min_delay": 0.8,
        "max_delay": 1.5,
        "max_retries": 3,
        "default_min_length": 3,
        "default_max_length": 6,
        "default_count": 100,
        "use_letters": True,
        "use_digits": True,
        "use_underscore": True,
        "use_period": True,
        "save_available": True,
        "save_taken": False,
        "results_dir": "results",
        "log_file": "scraper.log",
        "webhook_url": "",
        "notify_on_available": True,
        "use_proxies": False,
        "rotate_user_agents": True,
        "resume_checks": True,
        "validate_usernames": True,
        "use_wordlist": False,
        "wordlist_path": "wordlist.txt",
    }

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            config = {**default_config, **loaded}
            logger.info("Loaded config from config.yml")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
            config = default_config
    else:
        config = default_config
        save_config()

    # Ensure results dir
    global RESULTS_DIR
    RESULTS_DIR = BASE_DIR / config.get("results_dir", "results")
    RESULTS_DIR.mkdir(exist_ok=True)
    return config

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.error(f"Could not save config: {e}")

# ---------------- PROXY & HEADERS ----------------
def load_proxies():
    global proxies
    proxies = []
    if not PROXIES_FILE.exists():
        return
    try:
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.startswith("http"):
                        line = "http://" + line
                    proxies.append(line)
        logger.info(f"Loaded {len(proxies)} proxies")
    except Exception as e:
        logger.error(f"Failed to load proxies: {e}")

def get_proxy() -> Optional[Dict[str, str]]:
    if not config.get("use_proxies") or not proxies:
        return None
    proxy = random.choice(proxies)
    return {"http": proxy, "https": proxy}

def get_headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": ua.random if config.get("rotate_user_agents") else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyNC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTI0LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjI4NzE5OSwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0=",
    }
    return headers

# ---------------- WORDLIST & KNOWN ----------------
def load_wordlist():
    global wordlist
    wordlist = []
    path = BASE_DIR / config.get("wordlist_path", "wordlist.txt")
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w and len(w) >= 2:
                    wordlist.append(w)
        logger.info(f"Loaded {len(wordlist)} words from wordlist")
    except Exception as e:
        logger.error(f"Failed to load wordlist: {e}")

def load_known():
    global known_usernames
    known_usernames = set()
    if not config.get("resume_checks"):
        return
    if KNOWN_FILE.exists():
        try:
            with open(KNOWN_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    u = line.strip().lower()
                    if u:
                        known_usernames.add(u)
            logger.info(f"Loaded {len(known_usernames)} previously checked usernames")
        except Exception as e:
            logger.error(f"Error loading known usernames: {e}")

def save_known(username: str):
    if config.get("resume_checks"):
        try:
            with open(KNOWN_FILE, "a", encoding="utf-8") as f:
                f.write(username.lower() + "\n")
            known_usernames.add(username.lower())
        except Exception as e:
            logger.debug(f"Failed to save known: {e}")

# ---------------- USERNAME GENERATION ----------------
def is_valid_username(username: str) -> bool:
    if not username or not (USERNAME_MIN <= len(username) <= USERNAME_MAX):
        return False
    if not all(c in ALLOWED_CHARS for c in username):
        return False
    if ".." in username or "__" in username or "._" in username or "_." in username:
        return False
    if username[0] in "._" or username[-1] in "._":
        return False
    reserved = {"discord", "admin", "support", "system", "everyone", "here"}
    if username.lower() in reserved:
        return False
    return True

def generate_random_username(length: int) -> str:
    chars = ""
    if config.get("use_letters", True):
        chars += string.ascii_lowercase
    if config.get("use_digits", True):
        chars += string.digits
    if config.get("use_underscore", True):
        chars += "_"
    if config.get("use_period", True):
        chars += "."

    if not chars:
        chars = string.ascii_lowercase + string.digits

    username = "".join(random.choices(chars, k=length))

    attempts = 0
    while not is_valid_username(username) and attempts < 20:
        username = "".join(random.choices(chars, k=length))
        attempts += 1

    if username and username[0] in "._":
        username = random.choice(string.ascii_lowercase) + username[1:]
    if username and username[-1] in "._":
        username = username[:-1] + random.choice(string.ascii_lowercase + string.digits)

    return username.lower()

def generate_from_wordlist(length: Optional[int] = None) -> str:
    if not wordlist:
        return generate_random_username(length or random.randint(3, 8))

    word = random.choice(wordlist)
    suffix = ""

    if length:
        target = length - len(word)
        if target > 0:
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=target))
        else:
            word = word[:length-1]
    else:
        suffix_len = random.randint(0, 3)
        if suffix_len:
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits + "_.", k=suffix_len))

    candidate = (word + suffix).lower()[:32]

    if len(candidate) < 2:
        return generate_random_username(4)

    if candidate[0] in "._":
        candidate = random.choice(string.ascii_lowercase) + candidate[1:]
    if candidate and candidate[-1] in "._":
        candidate = candidate[:-1] + random.choice(string.ascii_lowercase + string.digits)

    return candidate

def generate_patterned(length: int) -> str:
    patterns = [
        "{word}{num}",
        "{word}.{num}",
        "{word}_{num}",
        "{word}{let}{num}",
        "{word}.{word}",
    ]
    pattern = random.choice(patterns)

    if not wordlist:
        return generate_random_username(length)

    word1 = random.choice(wordlist)
    word2 = random.choice(wordlist)
    num = str(random.randint(1, 999))
    let = random.choice(string.ascii_lowercase)

    candidate = pattern.format(word=word1, num=num, let=let, word2=word2)
    candidate = candidate[:length].lower()

    while len(candidate) < length:
        candidate += random.choice(string.ascii_lowercase + string.digits)

    return candidate[:length]

def generate_usernames(count: int, min_len: int = 3, max_len: int = 6,
                       strategy: str = "random") -> List[str]:
    usernames = set()
    max_attempts = count * 10
    attempts = 0

    while len(usernames) < count and attempts < max_attempts:
        attempts += 1
        length = random.randint(min_len, max_len)

        if strategy == "wordlist" and wordlist:
            u = generate_from_wordlist(length)
        elif strategy == "patterned":
            u = generate_patterned(length)
        else:
            u = generate_random_username(length)

        if config.get("validate_usernames") and not is_valid_username(u):
            continue
        if u in known_usernames:
            continue
        if u not in usernames:
            usernames.add(u.lower())

    return list(usernames)

# ---------------- DISCORD CHECK ----------------
def check_username(username: str, attempt: int = 0) -> Dict[str, Any]:
    global stats

    if config.get("validate_usernames") and not is_valid_username(username):
        stats["invalid"] += 1
        return {
            "username": username,
            "available": False,
            "status": "invalid",
            "message": "Invalid format per Discord rules",
            "taken": True,
        }

    headers = get_headers()
    proxy = get_proxy()
    payload = {"username": username}

    try:
        resp = requests.post(
            DISCORD_ENDPOINT,
            json=payload,
            headers=headers,
            proxies=proxy,
            timeout=12,
        )

        status = resp.status_code

        if status == 200:
            data = resp.json()
            taken = data.get("taken", True)
            available = not taken

            result = {
                "username": username,
                "available": available,
                "status": "available" if available else "taken",
                "message": "Available!" if available else "Taken",
                "taken": taken,
                "raw": data,
            }
            return result

        elif status == 429:
            stats["rate_limits"] += 1
            retry_after = 1.5
            try:
                retry_after = float(resp.json().get("retry_after", 1.5))
            except Exception:
                pass
            if attempt < config.get("max_retries", 3):
                time.sleep(retry_after + random.uniform(0.3, 0.8))
                return check_username(username, attempt + 1)
            return {
                "username": username,
                "available": False,
                "status": "rate_limited",
                "message": f"Rate limited after retries",
                "taken": True,
            }

        elif status == 400:
            try:
                msg = resp.json().get("message", "Invalid username")
            except Exception:
                msg = resp.text[:120]
            stats["invalid"] += 1
            return {
                "username": username,
                "available": False,
                "status": "invalid",
                "message": msg,
                "taken": True,
            }

        elif status in (403, 503):
            return {
                "username": username,
                "available": False,
                "status": "blocked",
                "message": f"Access blocked (status {status}) - try proxies or residential IP",
                "taken": True,
            }

        else:
            stats["errors"] += 1
            return {
                "username": username,
                "available": False,
                "status": "error",
                "message": f"HTTP {status}: {resp.text[:100]}",
                "taken": True,
            }

    except requests.exceptions.Timeout:
        return {"username": username, "available": False, "status": "timeout", "message": "Request timeout", "taken": True}
    except requests.exceptions.ConnectionError:
        return {"username": username, "available": False, "status": "connection", "message": "Connection error", "taken": True}
    except Exception as e:
        stats["errors"] += 1
        return {"username": username, "available": False, "status": "error", "message": str(e)[:80], "taken": True}

# ---------------- RESULTS & SAVING ----------------
def save_result(result: Dict[str, Any]):
    username = result["username"]
    save_known(username)

    if result.get("available"):
        if config.get("save_available", True):
            with open(AVAILABLE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{username}\n")
        stats["available"] += 1
        if config.get("notify_on_available") and config.get("webhook_url"):
            send_webhook(result)
    else:
        if config.get("save_taken", False):
            with open(TAKEN_FILE, "a", encoding="utf-8") as f:
                f.write(f"{username}\n")
        if result.get("status") != "available":
            stats["taken"] += 1

    stats["total_checked"] += 1

def send_webhook(result: Dict[str, Any]):
    webhook = config.get("webhook_url")
    if not webhook:
        return
    try:
        payload = {
            "content": "",
            "embeds": [{
                "title": "✅ Discord Username Available!",
                "description": f"**`{result['username']}`** is available!",
                "color": 0x57F287,
                "timestamp": datetime.utcnow().isoformat(),
                "fields": [
                    {"name": "Length", "value": str(len(result['username'])), "inline": True},
                    {"name": "Status", "value": result.get("status", "available"), "inline": True},
                ],
                "footer": {"text": "Discord Username Scraper"}
            }]
        }
        requests.post(webhook, json=payload, timeout=8)
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")

def export_results(results: List[Dict[str, Any]], format: str = "txt"):
    if not results:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = RESULTS_DIR / f"scrape_{timestamp}"

    if format == "txt":
        avail = [r["username"] for r in results if r.get("available")]
        if avail:
            with open(base.with_suffix(".available.txt"), "w") as f:
                f.write("\n".join(avail))

    elif format == "csv":
        with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["username", "available", "status", "message"])
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "username": r["username"],
                    "available": r.get("available"),
                    "status": r.get("status"),
                    "message": r.get("message", "")
                })

    elif format == "json":
        with open(base.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    console.print(f"[green]Results exported to {base}*[/green]")

# ---------------- CHECKING LOGIC ----------------
def check_batch(usernames: List[str], max_workers: int = 5) -> List[Dict[str, Any]]:
    results = []
    min_d = config.get("min_delay", 0.8)
    max_d = config.get("max_delay", 1.5)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Checking usernames...", total=len(usernames))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_name = {executor.submit(check_username, name): name for name in usernames}

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    res = future.result()
                    results.append(res)
                    save_result(res)

                    if res.get("available"):
                        rprint(f"[bold green]✓ AVAILABLE[/bold green]  [cyan]{res['username']}[/cyan]")
                    else:
                        color = "red" if res.get("status") == "taken" else "yellow"
                        rprint(f"[{color}]✗ {res.get('status', 'taken').upper()}[/{color}]  {res['username']} - {res.get('message', '')[:40]}")

                    if min_d > 0:
                        time.sleep(random.uniform(min_d, max_d))

                except Exception as e:
                    logger.error(f"Error checking {name}: {e}")
                    stats["errors"] += 1

                progress.update(task, advance=1)

    return results

# ---------------- STATS & DISPLAY ----------------
def print_stats(results: List[Dict[str, Any]] = None):
    stats["end_time"] = datetime.now()

    table = Table(title="📊 Scrape Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    total = stats.get("total_checked", 0)
    avail = stats.get("available", 0)
    rate = (avail / total * 100) if total > 0 else 0

    table.add_row("Total Checked", str(total))
    table.add_row("Available", f"[bold green]{avail}[/bold green]")
    table.add_row("Taken / Invalid", str(stats.get("taken", 0) + stats.get("invalid", 0)))
    table.add_row("Rate Limits Hit", str(stats.get("rate_limits", 0)))
    table.add_row("Errors", str(stats.get("errors", 0)))
    table.add_row("Success Rate", f"{rate:.1f}%")

    if stats["start_time"] and stats["end_time"]:
        duration = (stats["end_time"] - stats["start_time"]).total_seconds()
        table.add_row("Duration", f"{duration:.1f}s")
        if duration > 0 and total > 0:
            table.add_row("Avg speed", f"{total / duration:.1f} checks/sec")

    console.print(table)

    if results and avail > 0:
        avail_names = [r["username"] for r in results if r.get("available")]
        console.print(Panel("\n".join(avail_names[:20]), title=f"🎉 {len(avail_names)} Available Hits (first 20)"))

def save_stats():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, default=str)
    except Exception:
        pass

# ---------------- CLI & MODES ----------------
def interactive_menu():
    console.rule("[bold cyan]Discord Username Scraper[/bold cyan]", style="cyan")
    console.print(Panel.fit(
        "[bold]1.[/bold] Generate + Check Random Usernames\n"
        "[bold]2.[/bold] Generate + Check using Wordlist\n"
        "[bold]3.[/bold] Generate + Check Patterned\n"
        "[bold]4.[/bold] Check from usernames.txt list\n"
        "[bold]5.[/bold] Check custom usernames (paste)\n"
        "[bold]6.[/bold] Settings / Config\n"
        "[bold]7.[/bold] View last stats\n"
        "[bold]0.[/bold] Exit",
        title="Main Menu", border_style="cyan"
    ))

    choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7"], default="1")

    if choice == "0":
        console.print("[yellow]Goodbye![/yellow]")
        return False

    if choice == "6":
        edit_settings()
        return True
    if choice == "7":
        show_last_stats()
        return True

    if choice in ["1", "2", "3"]:
        min_len = IntPrompt.ask("Minimum username length", default=config["default_min_length"])
        max_len = IntPrompt.ask("Maximum username length", default=config["default_max_length"])
        count = IntPrompt.ask("How many usernames to generate & check?", default=config["default_count"])
        threads = IntPrompt.ask("Concurrency (threads)", default=config["threads"])

        if choice == "1":
            strategy = "random"
        elif choice == "2":
            strategy = "wordlist"
            if not wordlist:
                console.print("[yellow]Wordlist empty. Falling back to random.[/yellow]")
                strategy = "random"
        else:
            strategy = "patterned"

        usernames = generate_usernames(count, min_len, max_len, strategy)
        console.print(f"[green]Generated {len(usernames)} unique usernames[/green]")

    elif choice == "4":
        list_path = BASE_DIR / "usernames.txt"
        if not list_path.exists():
            console.print("[red]usernames.txt not found in project root.[/red]")
            return True
        with open(list_path, "r", encoding="utf-8") as f:
            usernames = [line.strip().lower() for line in f if line.strip()]
        usernames = [u for u in usernames if u not in known_usernames]
        threads = IntPrompt.ask("Concurrency (threads)", default=config["threads"])
        console.print(f"[green]Loaded {len(usernames)} usernames from list[/green]")

    elif choice == "5":
        console.print("[dim]Paste usernames (one per line). Press Ctrl+D (or Ctrl+Z) when done.[/dim]")
        usernames = []
        try:
            while True:
                line = input().strip().lower()
                if line:
                    usernames.append(line)
        except EOFError:
            pass
        usernames = [u for u in usernames if u not in known_usernames and is_valid_username(u)]
        threads = min(8, max(1, len(usernames) // 4 + 1))
        console.print(f"[green]Loaded {len(usernames)} valid usernames[/green]")

    else:
        return True

    if not usernames:
        console.print("[red]No usernames to check.[/red]")
        return True

    stats["start_time"] = datetime.now()
    stats["total_checked"] = 0
    stats["available"] = 0
    stats["taken"] = 0
    stats["invalid"] = 0
    stats["errors"] = 0
    stats["rate_limits"] = 0

    console.rule(f"[bold]Checking {len(usernames)} usernames[/bold]")

    results = check_batch(usernames, max_workers=threads)

    print_stats(results)

    if Confirm.ask("Export results?", default=True):
        fmt = Prompt.ask("Export format", choices=["txt", "csv", "json", "none"], default="txt")
        if fmt != "none":
            export_results(results, fmt)

    save_stats()
    console.print("[green]Done! Results saved to results/ folder.[/green]")
    return True

def edit_settings():
    global config
    console.print(Panel("Current Config", expand=False))
    for k, v in config.items():
        console.print(f"[cyan]{k}[/cyan]: {v}")

    if Confirm.ask("Edit key values?", default=False):
        new_threads = IntPrompt.ask("Threads", default=config["threads"])
        new_min = float(Prompt.ask("Min delay (seconds)", default=str(config["min_delay"])))
        new_max = float(Prompt.ask("Max delay (seconds)", default=str(config["max_delay"])))
        use_proxy = Confirm.ask("Use proxies?", default=config.get("use_proxies", False))
        use_resume = Confirm.ask("Resume / skip known usernames?", default=config.get("resume_checks", True))
        webhook = Prompt.ask("Webhook URL (blank to disable)", default=config.get("webhook_url", ""))

        config.update({
            "threads": new_threads,
            "min_delay": new_min,
            "max_delay": new_max,
            "use_proxies": use_proxy,
            "resume_checks": use_resume,
            "webhook_url": webhook.strip(),
        })
        save_config()
        console.print("[green]Config updated and saved![/green]")

def show_last_stats():
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE) as f:
                old = json.load(f)
            console.print(Panel.fit(str(old), title="Last Run Stats"))
        except Exception:
            console.print("[red]Could not load stats file[/red]")
    else:
        console.print("[yellow]No previous stats found[/yellow]")

    if AVAILABLE_FILE.exists():
        with open(AVAILABLE_FILE) as f:
            avail = [line.strip() for line in f if line.strip()]
        if avail:
            console.print(f"[green]Total available ever found: {len(avail)}[/green]")
            console.print(", ".join(avail[-5:]))

# ---------------- MAIN ENTRY ----------------
def main():
    load_config()
    load_proxies()
    load_wordlist()
    load_known()

    console.print(Panel.fit(
        "[bold cyan]Discord Username Scraper[/bold cyan]\n"
        "Random generation + Public unauthed API checks\n"
        f"Endpoint: {DISCORD_ENDPOINT}\n\n"
        "[yellow]Tip:[/yellow] Use residential proxies for best results. Keep threads low.",
        border_style="bright_blue"
    ))

    # Ensure sample usernames.txt
    if not (BASE_DIR / "usernames.txt").exists():
        with open(BASE_DIR / "usernames.txt", "w") as f:
            f.write("# Put one username per line to check in bulk\nexampleuser\n")

    # Run interactive loop
    running = True
    while running:
        try:
            running = interactive_menu()
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user. Saving progress...[/yellow]")
            save_stats()
            break
        except Exception as e:
            logger.exception("Unexpected error in main loop")
            console.print(f"[red]Error: {e}[/red]")
            if not Confirm.ask("Continue anyway?", default=True):
                break

    console.print("[bold green]Session ended. Check results/ directory.[/green]")

if __name__ == "__main__":
    main()
