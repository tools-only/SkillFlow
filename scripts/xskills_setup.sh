#!/bin/bash
# X-Skills Plugin Setup Script
# This script sets up the X-Skills plugin for Claude Code

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}X-Skills Plugin Setup${NC}"
echo "=========================="
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not found"
    exit 1
fi
print_status "Python 3 found"

# Check if X-Skills repository exists
XSKILLS_PATH="$PROJECT_ROOT/skillflow_repos/X-Skills"
if [ ! -d "$XSKILLS_PATH" ]; then
    print_error "X-Skills repository not found at $XSKILLS_PATH"
    echo "Please clone the X-Skills repository first:"
    echo "  git clone https://github.com/your-repo/X-Skills.git $XSKILLS_PATH"
    exit 1
fi
print_status "X-Skills repository found"

# Create necessary directories
echo ""
echo "Creating directories..."

mkdir -p "$PROJECT_ROOT/.claude/skills/xskills"
print_status "Created .claude/skills/xskills/"

mkdir -p "$PROJECT_ROOT/.claude/agents"
print_status "Created .claude/agents/"

mkdir -p "$PROJECT_ROOT/config"
print_status "Created config/"

# Check if requirements need to be installed
echo ""
echo "Checking dependencies..."

REQUIRED_DEPS=("pyyaml" "rich" "questionary")
MISSING_DEPS=()

for dep in "${REQUIRED_DEPS[@]}"; do
    if ! python3 -c "import ${dep//-/_}" 2>/dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    print_warning "Missing dependencies: ${MISSING_DEPS[*]}"
    echo ""
    read -p "Install missing dependencies? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install "${MISSING_DEPS[@]}"
        print_status "Dependencies installed"
    else
        print_warning "Skipping dependency installation"
    fi
else
    print_status "All dependencies satisfied"
fi

# Create or update config file
echo ""
if [ -f "$PROJECT_ROOT/config/xskills_config.yaml" ]; then
    print_warning "Config file already exists"
    read -p "Overwrite with default config? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 -m src.xskills_cli config --init
        print_status "Config file overwritten"
    else
        print_status "Keeping existing config"
    fi
else
    python3 -m src.xskills_cli config --init
    print_status "Config file created"
fi

# Summary
echo ""
echo "=========================="
echo -e "${GREEN}Setup Complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Browse available skills:"
echo "     python -m src.xskills_cli list"
echo ""
echo "  2. Search for skills:"
echo "     python -m src.xskills_cli search '<query>'"
echo ""
echo "  3. Enable skills interactively:"
echo "     python -m src.xskills_cli enable --interactive"
echo ""
echo "  4. Or use the xskills-loader agent in Claude Code"
echo ""
echo "For more help:"
echo "  python -m src.xskills_cli --help"
