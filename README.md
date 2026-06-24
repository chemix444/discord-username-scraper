# Discord Username Scraper

A powerful, production-grade tool that **randomly generates** Discord usernames of any length (2–32 characters) and **checks** them in real-time against Discord's public username availability API.

## ✨ Features

- **Random Generation** of usernames of any character length
- **Multiple Generation Strategies**
  - Pure random (letters + digits + symbols)
  - Wordlist-based (smart + suffixes)
  - Patterned (e.g. `word123`, `word.word`, `word_word`)
- **Concurrent checking** with `ThreadPoolExecutor`
- **Rate limit handling** + automatic retries + jitter
- **Proxy support** (rotating)
- **User-Agent rotation**
- **Resume support** — skips usernames already checked
- **Strict validation** against Discord's username rules
- **Beautiful CLI** powered by Rich (progress bars, colored output)
- **Webhook notifications** for available usernames
- **Multiple export formats**: TXT, CSV, JSON
- **Comprehensive logging** + persistent stats
- Fully configurable via `config.yml`

## 📡 API Endpoint Used

```
POST https://discord.com/api/v9/unique-username/username-attempt-unauthed
```

This is the **public unauthenticated** endpoint used by the official Discord client.

**Example response:**
```json
{ "taken": false }   // ✅ Available
{ "taken": true }    // ❌ Taken
```

## 🚀 Installation

```bash
git clone https://github.com/chemix444/discord-username-scraper.git
cd discord-username-scraper
pip install -r requirements.txt
```

## ▶️ Usage

```bash
python main.py
```

The tool launches an **interactive menu**:

1. Generate + Check Random Usernames
2. Generate + Check using Wordlist
3. Generate + Check Patterned
4. Check from `usernames.txt` list
5. Check custom usernames (paste)
6. Settings / Config
7. View last stats
0. Exit

## ⚙️ Configuration (`config.yml`)

```yaml
threads: 5
min_delay: 0.8
max_delay: 1.5
default_min_length: 3
default_max_length: 6
default_count: 100

use_letters: true
use_digits: true
use_underscore: true
use_period: true

webhook_url: ""           # Add your Discord webhook here
use_proxies: false
resume_checks: true
```

## 📁 Output Files

All results are saved in the `results/` folder:

- `available_usernames.txt` — All available hits
- `known.txt` — All previously checked usernames (for resume)
- `stats.json` — Detailed session statistics
- `scrape_*.txt / .csv / .json` — Exported results

## ⚠️ Important Warnings

- Discord rate limits are very aggressive
- Recommended: **3–5 threads** and **≥ 0.7s delay**
- Use **residential proxies** for best success rate
- This tool uses **no user tokens** (fully public endpoint)
- Respect Discord's Terms of Service

## 📜 License

This project is provided for **educational and research purposes only**.

---

**Made for username hunters** • Use responsibly.

---

**Note**: This README was recently fixed after an empty push. If you're seeing a blank page, try hard-refreshing (Ctrl+Shift+R) or wait 1-2 minutes for GitHub's CDN to update.
