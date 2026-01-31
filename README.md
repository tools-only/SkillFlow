# SkillFlow - Automated GitHub Skill Aggregator

A self-governed Python project that automatically searches GitHub for Claude/Anthropic agent skills, analyzes them using AI, categorizes them, and keeps the SkillFlow repository updated with the latest skills.

## Features

- **GitHub Search Integration**: Automatically finds repositories containing skill files
- **AI-Powered Analysis**: Uses Claude API to analyze and categorize skills
- **Smart Organization**: Organizes skills into nested category/subcategory folders
- **Duplicate Detection**: Tracks processed skills to avoid duplicates
- **Automated Updates**: Cron job support for periodic updates
- **Git Integration**: Automatic commit and push of new skills

## Project Structure

```
SkillFlow/
├── skills/                    # Downloaded skill files (git tracked)
│   └── {category}/           # Nested categories (e.g., daily-assistant/writing/)
│       └── {subcategory}/    # Sub-categories for organization
│           └── {skill-name}.md
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point for cron jobs
│   ├── config.py            # Configuration loader
│   ├── github_searcher.py   # GitHub Search API integration
│   ├── skill_analyzer.py    # AI-based skill analysis
│   ├── skill_fetcher.py     # Clone and extract skill files
│   ├── organizer.py         # Category-based file organization
│   ├── tracker.py           # Track processed skills (SQLite + JSON)
│   └── updater.py           # Git operations for repo updates
├── config/
│   ├── config.yaml          # Main configuration file
│   └── search_terms.yaml    # Custom search terms configuration
├── data/
│   └── skills_tracker.db    # SQLite database of processed skills
├── logs/
│   └── skillflow.log        # Application logs
├── requirements.txt
├── .env.example             # Environment variables template
├── .gitignore
├── README.md
└── scripts/
    └── setup_cron.sh        # Cron job setup script
```

## Installation

### Prerequisites

- Python 3.11+
- GitHub Token (optional, for higher API rate limits)
- Anthropic API Key (required)

### Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd SkillFlow
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

   Required variables:
   - `ANTHROPIC_API_KEY`: Your Anthropic API key (get from https://console.anthropic.com/)
   - `GITHUB_TOKEN`: Your GitHub token (optional, get from https://github.com/settings/tokens)

## Usage

### Manual Run

```bash
# Run a single update cycle
python -m src.main

# Show statistics only
python -m src.main --stats

# Dry run (no git commits)
python -m src.main --dry-run
```

### Automated Cron Job

Run the setup script:
```bash
bash scripts/setup_cron.sh
```

This will:
- Create a virtual environment
- Install dependencies
- Verify configuration
- Set up a cron job (default: every hour)
- Configure log rotation

### Cron Schedule

To customize the schedule, edit the crontab:
```bash
crontab -e
```

Default schedule (every hour):
```
0 * * * * cd /path/to/SkillFlow && .venv/bin/python -m src.main >> logs/skillflow.log 2>&1
```

## Configuration

### `config/config.yaml`

Main configuration file with GitHub token, API keys, and paths.

```yaml
github:
  token: "${GITHUB_TOKEN}"
  max_results: 20
  min_stars: 5

anthropic:
  api_key: "${ANTHROPIC_API_KEY}"
  model: "claude-3-5-sonnet-20241022"
  max_tokens: 2000

paths:
  skills_dir: "skills"
  data_dir: "data"
  log_dir: "logs"

search:
  languages: ["python", "javascript", "typescript"]
  sort_by: "updated"
  order: "desc"
```

### `config/search_terms.yaml`

Custom search terms for finding skill repositories.

```yaml
terms:
  - "claude skill"
  - "anthropic agent"
  - "claude function"
  - "ai assistant skill"

excluded_repos:
  - "tools-only/SkillFlow"

required_file_patterns:
  - "**/*.md"
```

## Skill Categories

Skills are automatically categorized into:

- `daily-assistant`: Personal organization, scheduling, reminders
- `commercial`: E-commerce, business tools, customer service
- `investment`: Financial analysis, trading, portfolio management
- `development`: Coding assistance, DevOps, software tools
- `research`: Academic research, data gathering
- `content-creation`: Writing, media creation, editing
- `data-analysis`: Statistics, visualization
- `automation`: Workflow automation, scripting
- `communication`: Email, messaging, collaboration
- `productivity`: Efficiency tools, optimization
- `other`: Anything that doesn't fit above

## Skill File Format

Each skill file includes a YAML header with metadata:

```markdown
---
name: Skill Name
description: What this skill does
source: https://github.com/user/repo
original_path: path/to/skill.md
source_repo: user/repo
updated_at: 2024-01-31T10:00:00Z
category: daily-assistant
subcategory: writing
tags: ['writing', 'content']
primary_purpose: Main function of this skill
file_hash: abc123...
---

# Original skill content...
```

## Troubleshooting

### View Logs
```bash
tail -f logs/skillflow.log
```

### Check Statistics
```bash
python -m src.main --stats
```

### Test Configuration
```bash
python -c "from src.config import Config; c = Config(); print('GitHub token:', bool(c.github_token)); print('Anthropic key:', bool(c.anthropic_api_key))"
```

### Reset Tracker
```bash
rm data/skills_tracker.db
```

## License

MIT License - See LICENSE file for details
