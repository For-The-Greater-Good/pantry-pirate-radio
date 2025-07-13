# ~/.zshrc: executed by zsh for interactive shells

# Path to oh-my-zsh installation (if available)
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load
ZSH_THEME="robbyrussell"

# Enable command auto-correction
ENABLE_CORRECTION="true"

# Display red dots whilst waiting for completion
COMPLETION_WAITING_DOTS="true"

# History configuration
HISTSIZE=10000
SAVEHIST=10000
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_SAVE_NO_DUPS
setopt SHARE_HISTORY
setopt APPEND_HISTORY

# Auto-completion configuration
autoload -Uz compinit
compinit

# Case-insensitive completion
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

# Load Oh My Zsh plugins (if available)
plugins=(
    git
    docker
    docker-compose
    python
    poetry
    vscode
    history-substring-search
    zsh-autosuggestions
    zsh-syntax-highlighting
)

# Load Oh My Zsh if available
if [ -f "$ZSH/oh-my-zsh.sh" ]; then
    source $ZSH/oh-my-zsh.sh
fi

# Custom prompt with git info (fallback if oh-my-zsh not available)
if [ -z "$ZSH_VERSION" ] || [ ! -f "$ZSH/oh-my-zsh.sh" ]; then
    autoload -Uz vcs_info
    precmd() { vcs_info }
    zstyle ':vcs_info:git:*' formats ' (%b)'
    setopt PROMPT_SUBST
    PROMPT='%n@%m:%~${vcs_info_msg_0_}$ '
fi

# Load aliases
if [ -f ~/.aliases ]; then
    source ~/.aliases
fi

# Environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export POETRY_VENV_IN_PROJECT=1
export POETRY_CACHE_DIR=/tmp/poetry_cache
export DEVELOPMENT=1
export DEBUG=1
export LOG_LEVEL=DEBUG
export EDITOR=nano
export VISUAL=nano
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Path additions
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.poetry/bin:$PATH"
export PATH="$HOME/.npm-global/bin:$PATH"

# Functions
activate_venv() {
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "Activated virtual environment: .venv"
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        echo "Activated virtual environment: venv"
    fi
}

dev_setup() {
    echo "Setting up development environment..."

    # Try to activate virtual environment
    activate_venv

    # Check if Poetry is available
    if command -v poetry &> /dev/null; then
        echo "Poetry available"
        echo "Run 'poetry install' to install dependencies"
        echo "Run 'poetry shell' to activate poetry environment"
    fi

    # Check if Docker Compose is available
    if command -v docker-compose &> /dev/null; then
        echo "Docker Compose available"
        echo "Run 'docker-compose up -d' to start services"
    fi

    echo "Development aliases loaded. Type 'alias' to see available shortcuts."
}

project_info() {
    echo "=== Pantry Pirate Radio Development Environment ==="
    echo "Project: Food security data aggregation system"
    echo "Tech Stack: Python, FastAPI, PostgreSQL, Redis, Docker"
    echo ""
    echo "Quick commands:"
    echo "  serve    - Start FastAPI development server"
    echo "  test     - Run tests"
    echo "  lint     - Run linting and type checking"
    echo "  dcu      - Start Docker Compose services"
    echo "  dcd      - Stop Docker Compose services"
    echo ""
    echo "For more commands, see: alias | grep -E '^alias'"
}

goto() {
    case $1 in
        app) cd app ;;
        tests) cd tests ;;
        docs) cd docs ;;
        scripts) cd scripts ;;
        root) cd /workspaces/pantry-pirate-radio ;;
        *) echo "Usage: goto [app|tests|docs|scripts|root]" ;;
    esac
}

# Auto-completion
if command -v poetry &> /dev/null; then
    fpath+=~/.zfunc
    autoload -Uz compinit && compinit
fi

# Key bindings
bindkey "^[[A" history-substring-search-up
bindkey "^[[B" history-substring-search-down
bindkey "^R" history-incremental-search-backward

# Auto-activate virtual environment when entering project directory
chpwd() {
    if [ -f ".venv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then
        source .venv/bin/activate
    fi
}

# Welcome message for development environment
if [ -t 1 ] && [ "$SHLVL" = 1 ]; then
    echo "Welcome to Pantry Pirate Radio development environment!"
    echo "Type 'project_info' for quick reference or 'dev_setup' to initialize."
fi