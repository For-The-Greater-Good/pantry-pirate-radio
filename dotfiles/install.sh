#!/bin/bash

# Pantry Pirate Radio - Dotfiles Installation Script
# Automatically configures GitHub Codespaces with development environment

set -e

echo "🚀 Setting up Pantry Pirate Radio development environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get the directory where this script is located
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="$HOME"

log_info "Dotfiles directory: $DOTFILES_DIR"
log_info "Home directory: $HOME_DIR"

# Function to create symlink with backup
create_symlink() {
    local source="$1"
    local target="$2"

    if [ -L "$target" ]; then
        log_warning "Removing existing symlink: $target"
        rm "$target"
    elif [ -f "$target" ] || [ -d "$target" ]; then
        log_warning "Backing up existing file/directory: $target -> $target.backup"
        mv "$target" "$target.backup"
    fi

    ln -s "$source" "$target"
    log_success "Created symlink: $target -> $source"
}

# 1. Set up shell configuration
log_info "Setting up shell configuration..."

create_symlink "$DOTFILES_DIR/.bashrc" "$HOME_DIR/.bashrc"
create_symlink "$DOTFILES_DIR/.zshrc" "$HOME_DIR/.zshrc"
create_symlink "$DOTFILES_DIR/.aliases" "$HOME_DIR/.aliases"

# 2. Set up VSCode configuration
log_info "Setting up VSCode configuration..."

# Create .vscode directory in home for user settings
mkdir -p "$HOME_DIR/.vscode"

# Copy VSCode settings to user directory (not symlink to avoid conflicts)
if [ -f "$DOTFILES_DIR/.vscode/settings.json" ]; then
    cp "$DOTFILES_DIR/.vscode/settings.json" "$HOME_DIR/.vscode/settings.json"
    log_success "Copied VSCode settings.json"
fi

if [ -f "$DOTFILES_DIR/.vscode/keybindings.json" ]; then
    cp "$DOTFILES_DIR/.vscode/keybindings.json" "$HOME_DIR/.vscode/keybindings.json"
    log_success "Copied VSCode keybindings.json"
fi

# Copy snippets
if [ -d "$DOTFILES_DIR/.vscode/snippets" ]; then
    cp -r "$DOTFILES_DIR/.vscode/snippets" "$HOME_DIR/.vscode/"
    log_success "Copied VSCode snippets"
fi

# 3. Install VSCode extensions
log_info "Installing VSCode extensions..."

if command -v code &> /dev/null; then
    if [ -f "$DOTFILES_DIR/.vscode/extensions.json" ]; then
        # Extract extension IDs from extensions.json and install them
        extensions=$(grep -E '^\s*"[^"]+/[^"]+"\s*,' "$DOTFILES_DIR/.vscode/extensions.json" | sed 's/.*"\([^"]*\)".*/\1/' | grep -v '//')

        for extension in $extensions; do
            if [ -n "$extension" ]; then
                log_info "Installing extension: $extension"
                code --install-extension "$extension" --force || log_warning "Failed to install extension: $extension"
            fi
        done

        log_success "VSCode extensions installation complete"
    else
        log_warning "extensions.json not found, skipping extension installation"
    fi
else
    log_warning "VSCode CLI not available, skipping extension installation"
fi

# 4. Set up Git configuration (if not already configured)
log_info "Checking Git configuration..."

if ! git config --global user.name &> /dev/null; then
    log_info "Setting up Git user configuration..."
    echo "Please enter your Git username:"
    read -r git_username
    git config --global user.name "$git_username"
fi

if ! git config --global user.email &> /dev/null; then
    log_info "Setting up Git email configuration..."
    echo "Please enter your Git email:"
    read -r git_email
    git config --global user.email "$git_email"
fi

# Set up some useful Git defaults
git config --global init.defaultBranch main
git config --global pull.rebase false
git config --global core.autocrlf input
git config --global core.editor nano

log_success "Git configuration complete"

# 5. Set up Python development environment
log_info "Setting up Python development environment..."

# Update package lists
sudo apt-get update -y

# Install additional development tools
sudo apt-get install -y \
    tree \
    jq \
    curl \
    wget \
    htop \
    nano \
    vim \
    zsh \
    build-essential \
    shellcheck

# Install Oh My Zsh if not present and user wants it
if [ ! -d "$HOME/.oh-my-zsh" ]; then
    log_info "Oh My Zsh not found. Would you like to install it? (y/n)"
    read -r install_omz
    if [ "$install_omz" = "y" ] || [ "$install_omz" = "Y" ]; then
        sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
        log_success "Oh My Zsh installed"

        # Install additional plugins
        git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions 2>/dev/null || true
        git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting 2>/dev/null || true
        log_success "Zsh plugins installed"
    fi
fi

# 6. Set up Poetry if not present
if ! command -v poetry &> /dev/null; then
    log_info "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
    log_success "Poetry installed"
else
    log_info "Poetry already installed"
fi

# 7. Install project dependencies
log_info "Installing project dependencies..."
cd /workspaces/pantry-pirate-radio || cd "$(pwd)"

if [ -f "pyproject.toml" ]; then
    poetry install
    log_success "Poetry dependencies installed"
else
    log_warning "pyproject.toml not found, skipping Poetry installation"
fi

# 8. Set up pre-commit hooks (if available)
if command -v poetry &> /dev/null && poetry show pre-commit &> /dev/null; then
    log_info "Setting up pre-commit hooks..."
    poetry run pre-commit install
    log_success "Pre-commit hooks installed"
fi

# 9. Create workspace-specific VSCode settings
log_info "Creating workspace-specific VSCode settings..."

WORKSPACE_VSCODE_DIR="/workspaces/pantry-pirate-radio/.vscode"
mkdir -p "$WORKSPACE_VSCODE_DIR"

# Copy extensions.json to workspace for automatic extension recommendations
if [ -f "$DOTFILES_DIR/.vscode/extensions.json" ]; then
    cp "$DOTFILES_DIR/.vscode/extensions.json" "$WORKSPACE_VSCODE_DIR/extensions.json"
    log_success "Copied extensions.json to workspace"
fi

# Create a basic workspace settings file
cat > "$WORKSPACE_VSCODE_DIR/settings.json" << 'EOF'
{
  "python.defaultInterpreterPath": "/usr/local/bin/python",
  "python.terminal.activateEnvironment": true,
  "terminal.integrated.cwd": "/workspaces/pantry-pirate-radio"
}
EOF
log_success "Created workspace settings.json"

# 10. Set default shell to zsh if installed and user wants it
if command -v zsh &> /dev/null && [ "$SHELL" != "$(which zsh)" ]; then
    log_info "Would you like to set zsh as your default shell? (y/n)"
    read -r set_zsh
    if [ "$set_zsh" = "y" ] || [ "$set_zsh" = "Y" ]; then
        chsh -s "$(which zsh)"
        log_success "Default shell set to zsh"
    fi
fi

# 11. Source the new shell configuration
log_info "Sourcing shell configuration..."
if [ -f "$HOME_DIR/.bashrc" ]; then
    source "$HOME_DIR/.bashrc" || true
fi

echo ""
log_success "🎉 Pantry Pirate Radio development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Restart your terminal or run 'source ~/.bashrc' (or ~/.zshrc if using zsh)"
echo "2. Run 'poetry shell' to activate the Python environment"
echo "3. Run 'docker-compose up -d' to start the development services"
echo "4. Run 'project_info' for a quick reference of available commands"
echo ""
echo "Happy coding! 🚀"