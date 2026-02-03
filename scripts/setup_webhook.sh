#!/bin/bash
# Setup script for GitHub webhook configuration for SkillFlow
# This script generates a webhook secret and configures the GitHub webhook

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8765/webhook/github}"
REPO_NAME="${GITHUB_REPO:-tools-only/X-Skills}"

echo "================================"
echo "SkillFlow Webhook Setup"
echo "================================"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed${NC}"
    echo "Please install it from: https://cli.github.com/"
    exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with GitHub${NC}"
    echo "Please run: gh auth login"
    exit 1
fi

# Step 1: Generate webhook secret
echo -e "${YELLOW}Step 1: Generating webhook secret...${NC}"

if [ -f "$ENV_FILE" ]; then
    # Check if WEBHOOK_SECRET already exists
    if grep -q "^WEBHOOK_SECRET=" "$ENV_FILE" 2>/dev/null; then
        echo -e "${GREEN}Webhook secret already exists in .env file${NC}"
        WEBHOOK_SECRET=$(grep "^WEBHOOK_SECRET=" "$ENV_FILE" | cut -d'=' -f2)
    else
        WEBHOOK_SECRET=$(openssl rand -hex 32)
        echo "WEBHOOK_SECRET=$WEBHOOK_SECRET" >> "$ENV_FILE"
        echo -e "${GREEN}Generated new webhook secret and added to .env${NC}"
    fi
else
    WEBHOOK_SECRET=$(openssl rand -hex 32)
    echo "WEBHOOK_SECRET=$WEBHOOK_SECRET" > "$ENV_FILE"
    echo -e "${GREEN}Generated new webhook secret and created .env${NC}"
fi

echo "Webhook Secret: ${WEBHOOK_SECRET:0:16}..."
echo ""

# Step 2: Prompt for webhook URL
echo -e "${YELLOW}Step 2: Configure webhook URL${NC}"
echo "Current webhook URL: $WEBHOOK_URL"
read -p "Enter webhook URL (or press Enter to use current): " INPUT_URL
if [ -n "$INPUT_URL" ]; then
    WEBHOOK_URL="$INPUT_URL"
fi
echo "Using webhook URL: $WEBHOOK_URL"
echo ""

# Step 3: Create webhook on GitHub
echo -e "${YELLOW}Step 3: Creating webhook on GitHub...${NC}"
echo "Repository: $REPO_NAME"

# Check if webhook already exists
EXISTING_WEBHOOKS=$(gh api repos/"$REPO_NAME"/hooks --jq '.[] | select(.config.url == "'"$WEBHOOK_URL"'") | .id' 2>/dev/null || echo "")

if [ -n "$EXISTING_WEBHOOKS" ]; then
    echo -e "${YELLOW}Webhook already exists. Updating...${NC}"
    WEBHOOK_ID=$(echo "$EXISTING_WEBHOOKS" | head -n1)
    gh api -X PATCH repos/"$REPO_NAME"/hooks/"$WEBHOOK_ID" \
        -f config.url="$WEBHOOK_URL" \
        -f config.content_type="json" \
        -f config.secret="$WEBHOOK_SECRET" \
        -f config.insecure_ssl="0" \
        -F active=true > /dev/null
    echo -e "${GREEN}Webhook updated successfully${NC}"
else
    echo "Creating new webhook..."
    gh api -X POST repos/"$REPO_NAME"/hooks \
        -f name=web \
        -f config.url="$WEBHOOK_URL" \
        -f config.content_type="json" \
        -f config.secret="$WEBHOOK_SECRET" \
        -f config.insecure_ssl="0" \
        -f active=true \
        -F events='[issues,pull_request,pull_request_review,issue_comment]' > /dev/null
    echo -e "${GREEN}Webhook created successfully${NC}"
fi
echo ""

# Step 4: Export webhook URL to .env
echo -e "${YELLOW}Step 4: Saving configuration...${NC}"

if ! grep -q "^WEBHOOK_URL=" "$ENV_FILE" 2>/dev/null; then
    echo "WEBHOOK_URL=$WEBHOOK_URL" >> "$ENV_FILE"
else
    # Update existing line
    sed -i "s|^WEBHOOK_URL=.*|WEBHOOK_URL=$WEBHOOK_URL|" "$ENV_FILE"
fi
echo -e "${GREEN}Configuration saved to .env${NC}"
echo ""

# Step 5: Test webhook endpoint
echo -e "${YELLOW}Step 5: Testing webhook endpoint...${NC}"

# Check if webhook server is running
if curl -s -f "$WEBHOOK_URL/../health" > /dev/null 2>&1 || curl -s -f "http://localhost:8765/webhook/health" > /dev/null 2>&1; then
    echo -e "${GREEN}Webhook server is running${NC}"
else
    echo -e "${YELLOW}Warning: Webhook server doesn't appear to be running${NC}"
    echo "Start it with: python -m src.webhook_server"
    echo "Or use the systemd service: sudo systemctl start skillflow-webhook"
fi
echo ""

# Summary
echo "================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "================================"
echo ""
echo "Webhook configured for: $REPO_NAME"
echo "Webhook URL: $WEBHOOK_URL"
echo "Events: issues, pull_request, pull_request_review, issue_comment"
echo ""
echo "Next steps:"
echo "  1. Source the environment: source $ENV_FILE"
echo "  2. Start the webhook server:"
echo "     - Manual: python -m src.webhook_server"
echo "     - Service: sudo systemctl start skillflow-webhook"
echo "  3. Test by creating a new issue with 'repo-request' label"
echo ""
