#!/bin/bash
# Setup script for SkillFlow cron job automation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="$PROJECT_DIR/.venv"
INTERVAL_HOURS=${SKILLFLOW_INTERVAL:-1}  # Default: run every hour

# Log file location
LOG_FILE="$PROJECT_DIR/logs/skillflow.log"

echo "========================================"
echo "SkillFlow Cron Job Setup"
echo "========================================"
echo ""

# Check if Python is available
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo -e "${RED}Error: Python not found. Please install Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_BIN --version | awk '{print $2}')
echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "Creating virtual environment..."
    $PYTHON_BIN -m venv "$VENV_DIR"
    echo -e "${GREEN}Virtual environment created at $VENV_DIR${NC}"
else
    echo -e "${GREEN}Virtual environment already exists at $VENV_DIR${NC}"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$PROJECT_DIR/requirements.txt"
echo -e "${GREEN}Dependencies installed${NC}"

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/skills"
echo -e "${GREEN}Directories created${NC}"

# Check for .env file
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo ""
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo "Creating .env from .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo -e "${YELLOW}Please edit .env and add your API keys:${NC}"
    echo "  - GITHUB_TOKEN"
    echo "  - ANTHROPIC_API_KEY"
    echo ""
    read -p "Press Enter after you've configured .env..."
fi

# Verify .env has required keys
echo ""
echo "Verifying environment variables..."
source "$PROJECT_DIR/.env"

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY not set in .env${NC}"
    exit 1
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${YELLOW}Warning: GITHUB_TOKEN not set. GitHub API features will be limited.${NC}"
fi

# Test run
echo ""
echo "Running initial test..."
cd "$PROJECT_DIR"
$PYTHON_BIN -m src.main --stats

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Test run successful${NC}"
else
    echo -e "${RED}Test run failed. Please check configuration.${NC}"
    exit 1
fi

# Setup cron job
echo ""
echo "Setting up cron job..."

# Calculate cron expression
if [ "$INTERVAL_HOURS" -eq 1 ]; then
    CRON_EXPR="0 * * * *"  # Every hour at minute 0
elif [ "$INTERVAL_HOURS" -eq 24 ]; then
    CRON_EXPR="0 0 * * *"  # Daily at midnight
else
    # For other intervals, we need multiple lines
    # This is a simplification - for production, consider using a more sophisticated scheduler
    CRON_EXPR="0 */$INTERVAL_HOURS * * *"
fi

# Create the cron command
CRON_CMD="cd $PROJECT_DIR && $VENV_DIR/bin/python -m src.main >> $LOG_FILE 2>&1"

# Get current crontab
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# Check if SkillFlow cron entry already exists
if echo "$CURRENT_CRON" | grep -q "SkillFlow"; then
    echo -e "${YELLOW}SkillFlow cron entry already exists. Updating...${NC}"
    # Remove existing SkillFlow entries
    NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "SkillFlow")
else
    NEW_CRON="$CURRENT_CRON"
fi

# Add new cron entry
CRON_ENTRY="$CRON_EXPR $CRON_CMD # SkillFlow automated skill aggregator"

# Append new entry
(crontab -l 2>/dev/null | grep -v "SkillFlow"; echo "$CRON_ENTRY") | crontab -

echo -e "${GREEN}Cron job installed:${NC}"
echo "  Schedule: $CRON_EXPR"
echo "  Command: $CRON_CMD"
echo ""

# Setup log rotation
echo "Setting up log rotation..."
LOGROTATE_CONF="$PROJECT_DIR/scripts/skillflow.logrotate"
cat > "$LOGROTATE_CONF" << EOF
$LOG_FILE {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
}
EOF

# Try to install logrotate config (may require sudo)
if command -v logrotate &> /dev/null; then
    if [ -w "/etc/logrotate.d" ]; then
        sudo cp "$LOGROTATE_CONF" /etc/logrotate.d/skillflow 2>/dev/null || \
            echo -e "${YELLOW}Could not install logrotate config (requires sudo)${NC}"
    else
        echo -e "${YELLOW}Cannot write to /etc/logrotate.d (requires sudo)${NC}"
    fi
else
    echo -e "${YELLOW}logrotate not found. Manual log rotation may be needed.${NC}"
fi

echo ""
echo "========================================"
echo -e "${GREEN}Setup complete!${NC}"
echo "========================================"
echo ""
echo "Cron job will run with schedule: $CRON_EXPR"
echo ""
echo "Next steps:"
echo "  1. Monitor logs: tail -f $LOG_FILE"
echo "  2. View stats: $PYTHON_BIN -m src.main --stats"
echo "  3. Manual run: $PYTHON_BIN -m src.main"
echo "  4. View cron: crontab -l"
echo "  5. Edit schedule: crontab -e"
echo ""
echo "To disable: crontab -e (remove the SkillFlow line)"
echo ""
