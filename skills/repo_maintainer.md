---
name: Repo Maintainer
description: Agent that manages and organizes skills into GitHub repositories. Analyzes new skills, creates "X Skills" repos, organizes into folders, generates READMEs, and pushes to GitHub.
category: development
subcategory: tools
tags: [github, agent, automation]
---

# Repo Maintainer Agent

The **Repo Maintainer Agent** manages and organizes AI skills into separate GitHub repositories.

## What It Does

1. **Analyzes skills** and determines which repository they belong to
2. **Creates new repos** when needed (e.g., "Development Skills", "Daily Assistant Skills")
3. **Organizes skills** into appropriate folders
4. **Generates README** with introductions and statistics
5. **Pushes to GitHub** under the appropriate repository

## Known Skill Repositories

| Repository | Contains |
|-----------|----------|
| Development Skills | Coding, debugging, testing, DevOps |
| Daily Assistant Skills | Scheduling, tasks, reminders, calendar |
| Content Creation Skills | Writing, blogging, editing |
| Data Analysis Skills | Visualization, statistics, charts |
| Automation Skills | Workflows, scripts, batch operations |
| Research Skills | Academic papers, citations, literature |
| Communication Skills | Email, messaging, chat tools |
| Productivity Skills | Efficiency, optimization, focus |
| Commercial Skills | E-commerce, business tools |
| Investment Skills | Trading, stocks, crypto, finance |

## Usage from Claude Code

### Process Skills from Current Repo

```python
# Import the agent
from src.repo_maintainer import process_skills, create_skill_from_file

# Collect skills from the skills/ directory
skills_list = []
for skill_file in Path("skills").rglob("*.md"):
    skill_data = create_skill_from_file(str(skill_file))
    skills_list.append(skill_data)

# Process and organize into separate repos
results = process_skills(
    skills_list,
    org="tools-only",  # Your GitHub org/username
    push=True          # Set False to test without pushing
)

# Results shows which repos were created/updated
# {
#   "Development Skills": "/path/to/Development Skills",
#   "Daily Assistant Skills": "/path/to/Daily Assistant Skills"
# }
```

### Process Specific Skills

```python
from src.repo_maintainer import process_skills, create_skill_from_file

# Process specific skill files
skills_list = [
    create_skill_from_file("skills/coding/python-helper.md"),
    create_skill_from_file("skills/daily/task-manager.md"),
]

results = process_skills(skills_list)
```

### Direct Agent Usage

```python
from src.repo_maintainer import RepoMaintainerAgent, Skill

# Create agent
agent = RepoMaintainerAgent(github_token="your_token", org="tools-only")

# Create skill objects
skills = [
    Skill(
        name="Python Debugger",
        content="# Python Debugger\n...",
        source_repo="user/repo",
        source_path="skills/debugger.md",
        source_url="https://raw.githubusercontent.com/...",
        file_hash="abc123",
        metadata={"category": "development", "subcategory": "debugging"}
    )
]

# Analyze and plan
plans = agent.analyze_and_plan(skills)

# Execute plans
for plan in plans:
    agent.execute_plan(plan, push=True)
```

## Agent Decision Making

The agent reasons about:

1. **Repository Selection**: Uses keyword matching and metadata to determine which "X Skills" repo a skill belongs to

2. **New vs Existing**: Checks if a repo already exists before creating

3. **Folder Organization**: Groups skills into subcategory folders within each repo

4. **README Generation**: Creates descriptive READMEs with:
   - Repository description
   - Category overview
   - Skill counts
   - Usage instructions
   - Last update timestamp

## Example Output

```
Processing: Development Skills
  ✓ Created GitHub repo: https://github.com/tools-only/Development Skills
  ✓ Organized 15 skills into 4 folders:
    - coding: 6 skills
    - testing: 4 skills
    - devops: 3 skills
    - tools: 2 skills
  ✓ Generated README with overview
  ✓ Committed and pushed changes
```

## Integration with SkillFlow

The agent integrates with the main SkillFlow workflow:

```
SkillFlow Workflow (script)
    ↓
    Finds and fetches skills
    ↓
    Passes to Repo Maintainer Agent
    ↓
    Agent organizes into separate repos
    ↓
    Each repo gets its own README
    ↓
    Pushed to GitHub as "X Skills"
```

## Configuration

- **GitHub Token**: Set `GITHUB_TOKEN` environment variable
- **Organization**: Default is `tools-only`, customize as needed
- **Work Directory**: `./skillflow_repos/` for local clones

## Troubleshooting

**"Repo already exists"**: The agent will clone and update existing repos instead of creating new ones.

**"Nothing to commit"**: No new skills were added, or all skills already exist.

**Push fails**: Check your GitHub token has repo creation permissions.
