#!/bin/bash
# Test script to verify HAARRRvest setup is working correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Testing HAARRRvest Setup${NC}"
echo "========================="

# Test 1: Check scripts exist and are executable
echo -e "\n${GREEN}Test 1: Checking scripts${NC}"
SCRIPTS=(
    "init-data-repo.sh"
    "publish-data.sh"
    "sync-data-repo.sh"
    "datasette-lite-template.html"
)

for script in "${SCRIPTS[@]}"; do
    if [ -f "$SCRIPT_DIR/$script" ]; then
        echo "✓ $script exists"
        if [[ "$script" == *.sh ]]; then
            if [ -x "$SCRIPT_DIR/$script" ]; then
                echo "  ✓ Executable"
            else
                echo -e "  ${RED}✗ Not executable${NC}"
                exit 1
            fi
        fi
    else
        echo -e "${RED}✗ $script missing${NC}"
        exit 1
    fi
done

# Test 2: Check environment variables
echo -e "\n${GREEN}Test 2: Checking environment${NC}"
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "✓ .env file exists"
    # Check for required HAARRRvest variables
    if grep -q "DATA_REPO_URL" "$PROJECT_ROOT/.env"; then
        echo "✓ DATA_REPO_URL configured"
    else
        echo -e "${YELLOW}! DATA_REPO_URL not found in .env${NC}"
    fi
else
    echo -e "${YELLOW}! No .env file found (using defaults)${NC}"
fi

# Test 3: Verify output directory structure
echo -e "\n${GREEN}Test 3: Checking output directory${NC}"
if [ -d "$PROJECT_ROOT/outputs" ]; then
    echo "✓ outputs/ directory exists"
    
    # Check for new directory structure
    if [ -d "$PROJECT_ROOT/outputs/daily" ]; then
        echo "✓ outputs/daily/ exists (new structure)"
    else
        mkdir -p "$PROJECT_ROOT/outputs/daily"
        echo "✓ Created outputs/daily/"
    fi
    
    if [ -d "$PROJECT_ROOT/outputs/latest" ]; then
        echo "✓ outputs/latest/ exists"
    else
        mkdir -p "$PROJECT_ROOT/outputs/latest"
        echo "✓ Created outputs/latest/"
    fi
else
    echo -e "${YELLOW}! outputs/ directory not found${NC}"
    echo "  Creating directory structure..."
    mkdir -p "$PROJECT_ROOT/outputs/daily"
    mkdir -p "$PROJECT_ROOT/outputs/latest"
    echo "✓ Created output directories"
fi

# Test 4: Git configuration
echo -e "\n${GREEN}Test 4: Checking Git configuration${NC}"
if git config user.email > /dev/null 2>&1; then
    echo "✓ Git email configured: $(git config user.email)"
else
    echo -e "${RED}✗ Git email not configured${NC}"
    echo "  Run: git config --global user.email 'your-email@example.com'"
    exit 1
fi

if git config user.name > /dev/null 2>&1; then
    echo "✓ Git name configured: $(git config user.name)"
else
    echo -e "${RED}✗ Git name not configured${NC}"
    echo "  Run: git config --global user.name 'Your Name'"
    exit 1
fi

# Test 5: Check for SSH key
echo -e "\n${GREEN}Test 5: Checking SSH configuration${NC}"
if [ -f "$HOME/.ssh/id_rsa" ] || [ -f "$HOME/.ssh/id_ed25519" ]; then
    echo "✓ SSH key found"
    
    # Test GitHub SSH connection
    if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        echo "✓ GitHub SSH authentication working"
    else
        echo -e "${YELLOW}! GitHub SSH test failed (this is normal if using HTTPS)${NC}"
    fi
else
    echo -e "${YELLOW}! No SSH key found (you can use HTTPS instead)${NC}"
fi

# Test 6: Python dependencies
echo -e "\n${GREEN}Test 6: Checking Python environment${NC}"
if command -v poetry &> /dev/null; then
    echo "✓ Poetry installed"
    
    cd "$PROJECT_ROOT"
    if poetry check > /dev/null 2>&1; then
        echo "✓ Poetry dependencies valid"
    else
        echo -e "${YELLOW}! Poetry dependencies need update${NC}"
        echo "  Run: poetry install"
    fi
else
    echo -e "${YELLOW}! Poetry not found${NC}"
fi

# Test 7: Docker (optional)
echo -e "\n${GREEN}Test 7: Checking Docker (optional)${NC}"
if command -v docker &> /dev/null; then
    echo "✓ Docker installed"
    
    if docker info > /dev/null 2>&1; then
        echo "✓ Docker daemon running"
    else
        echo -e "${YELLOW}! Docker daemon not running${NC}"
    fi
else
    echo -e "${YELLOW}! Docker not installed (optional)${NC}"
fi

# Summary
echo -e "\n${BLUE}=== Setup Summary ===${NC}"
echo
echo "Next steps to complete HAARRRvest setup:"
echo
echo "1. Create HAARRRvest repository on GitHub:"
echo "   ${BLUE}https://github.com/new${NC}"
echo "   Name: HAARRRvest (Public repository)"
echo
echo "2. Initialize the repository:"
echo "   ${BLUE}./scripts/init-data-repo.sh${NC}"
echo
echo "3. Push to GitHub:"
echo "   ${BLUE}cd ../HAARRRvest && git push -u origin main${NC}"
echo
echo "4. Enable GitHub Pages:"
echo "   Repository Settings → Pages → Deploy from main branch"
echo
echo "5. Add DATA_REPO_TOKEN secret to main repository:"
echo "   Settings → Secrets → Actions → New repository secret"
echo
echo "6. Run test pipeline:"
echo "   ${BLUE}DAYS_TO_SYNC=1 PUSH_TO_REMOTE=false ./scripts/publish-data.sh${NC}"
echo
echo -e "${GREEN}✓ Basic setup checks complete!${NC}"