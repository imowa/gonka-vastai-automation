#!/bin/bash
# Setup script for Gonka Vast.ai Automation

set -e  # Exit on error

echo "================================================"
echo "  Gonka Vast.ai Automation Setup"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: requirements.txt not found${NC}"
    echo "Please run this script from the gonka-vastai-automation directory"
    exit 1
fi

# Create directory structure
echo -e "${YELLOW}Creating directory structure...${NC}"
mkdir -p config
mkdir -p scripts
mkdir -p logs
mkdir -p docker
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.8"

# Simple version comparison
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
    echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
else
    echo -e "${RED}✗ Python 3.8+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo ""

# Create virtual environment
echo -e "${YELLOW}Creating Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi
echo ""

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
./venv/bin/pip install -r requirements.txt --quiet
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Copy .env.example if .env doesn't exist
if [ ! -f "config/.env" ]; then
    echo -e "${YELLOW}Creating config/.env from template...${NC}"
    cp config/.env.example config/.env
    echo -e "${GREEN}✓ Config file created${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit config/.env with your API keys${NC}"
    echo "   nano config/.env"
else
    echo -e "${GREEN}✓ Config file already exists${NC}"
fi
echo ""

# Test network connectivity
echo -e "${YELLOW}Testing Gonka node connectivity...${NC}"
if curl -s --max-time 5 http://node2.gonka.ai:8000/v1/epochs/current > /dev/null; then
    echo -e "${GREEN}✓ Gonka node accessible${NC}"
else
    echo -e "${RED}✗ Cannot reach Gonka node${NC}"
    echo "  Check your internet connection"
fi
echo ""

# Check if Vast.ai CLI is available (optional)
echo -e "${YELLOW}Checking for Vast.ai CLI (optional)...${NC}"
if command -v vastai &> /dev/null; then
    echo -e "${GREEN}✓ Vast.ai CLI found${NC}"
    VASTAI_VERSION=$(vastai --version 2>&1 || echo "unknown")
    echo "  Version: $VASTAI_VERSION"
else
    echo -e "${YELLOW}⚠️  Vast.ai CLI not found (we'll use API instead)${NC}"
    echo "  Optional: Install with: pip install vastai"
fi
echo ""

# Test Script 1
echo -e "${YELLOW}Testing PoC Monitor (Script 1)...${NC}"
if python3 scripts/1_poc_monitor.py 2>&1 | grep -q "Testing epoch fetch"; then
    echo -e "${GREEN}✓ Script 1 working${NC}"
else
    echo -e "${RED}✗ Script 1 has errors${NC}"
    echo "  Check scripts/1_poc_monitor.py"
fi
echo ""

# Summary
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your API keys:"
echo "   ${GREEN}nano config/.env${NC}"
echo ""
echo "2. Add your Vast.ai API key from:"
echo "   ${GREEN}https://cloud.vast.ai/api/${NC}"
echo ""
echo "3. Activate virtual environment:"
echo "   ${GREEN}source venv/bin/activate${NC}"
echo ""
echo "4. Test PoC monitoring:"
echo "   ${GREEN}python test_monitor.py${NC}"
echo ""
echo "5. When done, deactivate virtual environment:"
echo "   ${GREEN}deactivate${NC}"
echo ""
echo "6. Wait for Script 2 (Vast.ai Manager)"
echo ""
echo "Questions? Check README.md"
echo ""
