# SkillFlow - Automated GitHub Skill Aggregator

A self-governed Python project that automatically searches GitHub for Claude/Anthropic agent skills, analyzes them using AI, categorizes them, and keeps the SkillFlow repository updated with the latest skills.

## X-Skills Plugin System

X-Skills is a npm-style plugin system that allows you to install and manage AI sub-agents as executable commands. Skills are packaged as plugins that can be searched, installed, and run directly from your CLI.

### Installation

**One-Line Install (Recommended):**
```bash
curl -fsSL https://raw.githubusercontent.com/tools-only/X-Skills/main/xsk-install.sh | bash
```

**Via Claude Code CLI:**
```bash
# Use the xskills command directly
xskills search "research"
xskills install research-agent
```

**Full Installation:**
```bash
git clone https://github.com/tools-only/SkillFlow.git ~/.skillflow
cd ~/.skillflow
bash scripts/setup_xskills.sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### CLI Commands

```bash
# Search plugins
xskills search "research"              # Search by keyword
xskills search "代码审查" --tier expert  # Filter by quality tier

# Install plugins
xskills install research-agent         # Single plugin
xskills install @academic_research     # Scenario bundle (multiple plugins)

# Manage plugins
xskills list-plugins                   # List installed
xskills capabilities research-agent    # View plugin capabilities
xskills validate research-agent        # Validate plugin
xskills info                           # System info

# Run plugins
xskills run research-agent "搜索最新的AI论文"
research-agent "搜索最新的AI论文"      # Direct command after install

# Update/Uninstall
xskills update research-agent
xskills uninstall research-agent

# Scenario bundles
xskills scenarios                      # List all 22 scenarios
xskills scenarios --category education # Filter by category
```

### Quality Tiers

Plugins are rated across four dimensions (0-25 each):
- **Depth**: Technical depth and domain expertise
- **Practicality**: Real-world applicability
- **Reliability**: Consistency and robustness
- **Collaboration**: Integration and compatibility

**Tiers:**
- **Expert** (★): Top 5% - Highest quality skills
- **Good**: Reliable, production-ready
- **Basic**: Functional skills with room for improvement

### Scenario Bundles (22 Available)

| ID | Name | Category | Description |
|---|---|---|---|
| @academic_research | 学术研究 | Education | Literature search to paper writing |
| @software_engineering | 软件工程 | Development | Full software development lifecycle |
| @intelligent_cs | 智能客服 | Business | Customer service automation |
| @data_science | 数据科学 | Science | Data analysis and visualization |
| @devops_engineering | DevOps工程 | Development | CI/CD and infrastructure |
| @content_creation | 自媒体创作 | Media | Content generation and editing |
| @social_media_operation | 社交运营 | Marketing | Social media management |
| @investment_research | 投研分析 | Finance | Financial analysis |
| @legal_research | 法律研究 | Legal | Legal document analysis |
| @medical_research | 医学研究 | Medical | Medical research assistance |
| @security_analysis | 安全分析 | Security | Security auditing |
| @product_management | 产品管理 | Business | Product development |
| @project_management | 项目管理 | Business | Project coordination |
| @education_tutoring | 教育辅导 | Education | Teaching and tutoring |
| @e_commerce | 电商运营 | Commerce | E-commerce operations |
| @ux_design | UX设计 | Design | User experience design |
| @translation_localization | 翻译本地化 | Language | Translation services |
| @hr_management | 人力资源 | Business | HR management |
| @real_estate | 房产分析 | Real Estate | Real estate analysis |
| @creative_writing | 创意写作 | Writing | Creative content writing |
| @api_development | API开发 | Development | API design and development |
| @life_assistant | 生活助理 | Lifestyle | Daily life assistance |

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
