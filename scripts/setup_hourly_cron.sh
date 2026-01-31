#!/bin/bash
# Setup hourly cron job for SkillFlow pipeline

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

echo "========================================"
echo "SkillFlow Hourly Pipeline Setup"
echo "========================================"
echo ""

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# Setup cron entry
CRON_CMD="cd $PROJECT_DIR && $PYTHON_BIN -m src.run_pipeline >> $PROJECT_DIR/logs/pipeline.log 2>&1"
CRON_ENTRY="0 * * * * $CRON_CMD # SkillFlow hourly pipeline"

# Get current crontab
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# Remove existing SkillFlow entries
NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "SkillFlow")

# Add new entry
(echo "$NEW_CRON"; echo "$CRON_ENTRY") | crontab -

echo "✓ Hourly cron job installed"
echo ""
echo "Schedule: Every hour at minute 0"
echo "Log file: $PROJECT_DIR/logs/pipeline.log"
echo ""
echo "To view logs: tail -f $PROJECT_DIR/logs/pipeline.log"
echo "To edit: crontab -e"
echo ""
