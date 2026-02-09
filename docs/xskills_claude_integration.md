# X-Skills Claude Code Plugin Integration

## Overview

X-Skills is now integrated as a Claude Code plugin, allowing you to browse, install, and manage 9000+ AI-powered skills directly from the command line.

## Installation

### Option 1: Install as Python Package

```bash
cd /root/SkillFlow
pip install -e .
```

### Option 2: Use Directly from Source

```bash
cd /root/SkillFlow
python3 -m src.xskills_cli_new --help
```

## Available Commands

### 1. Patch Management

Patches are curated skill bundles for common use cases.

```bash
# List all available patches
xskills patches list

# Install a patch
xskills patches install research-agent

# Install multiple patches
xskills patches install research-agent web-dev-agent

# Uninstall a patch
xskills patches uninstall research-agent

# Force reinstall
xskills patches install research-agent --force
```

### 2. Skill Browsing

Browse and search through the X-Skills repository.

```bash
# Browse all skills
xskills browse

# Browse by category
xskills browse --category research

# Browse with limit
xskills browse --limit 100

# Search skills
xskills search "web development"

# Search in category
xskills search "citation" --category research
```

### 3. System Status

Check the status of your X-Skills installation.

```bash
# Show system status
xskills status
```

## Available Patches

| Patch | Skills | Description |
|-------|--------|-------------|
| research-agent | 30 | Academic research and literature review |
| web-dev-agent | 80 | Full-stack web development |
| content-creator | 60 | Writing and content generation |
| data-analyst | 60 | Data analysis and visualization |
| automation-agent | 40 | Workflow automation |
| python-dev | 50 | Python development |
| communication-agent | 40 | Communication and messaging |
| devops-engineer | 60 | DevOps and infrastructure |
| productivity-assistant | 50 | Productivity tools |

## Categories

- **Research** - Academic papers, citations, literature search
- **Development** - Coding, debugging, web development
- **Content Creation** - Writing, editing, documentation
- **Data Analysis** - Statistics, visualization
- **Automation** - Workflows, scripting
- **Communication** - Email, messaging
- **Productivity** - Efficiency tools
- **Commercial** - E-commerce, business
- **Investment** - Trading, finance

## How It Works

### Installation Process

When you install a patch:

1. Skills are symlinked to `~/.claude/skills/patch-<patch-id>/`
2. Skills become immediately available in Claude Code
3. No manual copying required (symlinks save space)

### File Structure

```
~/.claude/skills/
├── patch-research-agent/
│   ├── 094-searching_f25e7adf/
│   │   ├── skill.md
│   │   └── README.md
│   ├── 053-searching_494df9be/
│   └── ...
├── patch-web-dev-agent/
│   └── ...
└── .installed_patches.json
```

## Example Workflow

```bash
# 1. Check available patches
xskills patches list

# 2. Install research agent patch
xskills patches install research-agent
# ✓ Installed research-agent

# 3. Verify installation
xskills status
# Installed Patches: 1

# 4. Browse installed skills
ls ~/.claude/skills/patch-research-agent/

# 5. Use skills in Claude Code
# Skills are now available in your Claude Code sessions
```

## Advanced Usage

### Custom Patches

Create your own skill bundles:

```python
from src.custom_skill_editor import CustomSkillEditor

editor = CustomSkillEditor()

# Add skills to custom patch
editor.add_skill_to_patch("research/094-searching_f25e7adf", "my-research")
editor.add_skill_to_patch("development/264-quickstart_666d3de7", "my-research")

# Export patch
editor.export_patch("my-research")
```

### Skill Browser API

```python
from src.skill_browser import SkillBrowser

browser = SkillBrowser()

# List categories
categories = browser.list_categories()

# Get category stats
stats = browser.get_category_stats()

# Search skills
results = browser.search_skills("web development", limit=10)

# Get skill info
info = browser.get_skill_info("research/094-searching_f25e7adf")

# Get skill content
content = browser.get_skill_content("research/094-searching_f25e7adf")
```

## Troubleshooting

### Skills Not Appearing in Claude Code

1. Check installation:
   ```bash
   xskills status
   ```

2. Verify skills directory:
   ```bash
   ls ~/.claude/skills/
   ```

3. Restart Claude Code

### Permission Issues

If symlinks fail, use copy mode:
```bash
xskills patches install research-agent --copy
```

## Next Steps

1. Install your first patch:
   ```bash
   xskills patches install research-agent
   ```

2. Explore available skills:
   ```bash
   xskills browse --category research
   ```

3. Check out the documentation:
   - X-Skills Repository: https://github.com/tools-only/X-Skills
   - Patch Index: See `patches/INDEX.md` in X-Skills

## Support

For issues or questions:
- GitHub: https://github.com/tools-only/SkillFlow
- Documentation: See `/root/SkillFlow/docs/`
