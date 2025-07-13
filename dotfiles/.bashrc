# ~/.bashrc: executed by bash(1) for non-login shells.

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# History configuration
HISTCONTROL=ignoreboth
HISTSIZE=10000
HISTFILESIZE=20000
shopt -s histappend
shopt -s checkwinsize

# Make less more friendly for non-text input files
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# Set variable identifying the chroot you work in
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# Set a fancy prompt (non-color, unless we know we "want" color)
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

# Enable color prompt
force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        color_prompt=yes
    else
        color_prompt=
    fi
fi

# Custom prompt with git branch
git_branch() {
    git branch 2>/dev/null | grep '^*' | colrm 1 2
}

if [ "$color_prompt" = yes ]; then
    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\[\033[01;33m\]$(git_branch)\[\033[00m\]\$ '
else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w$(git_branch)\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm set the title to user@host:dir
case "$TERM" in
xterm*|rxvt*)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

# Enable programmable completion features
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi

# Load aliases
if [ -f ~/.aliases ]; then
    . ~/.aliases
fi

# Python environment configuration
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1

# Poetry configuration
export POETRY_VENV_IN_PROJECT=1
export POETRY_CACHE_DIR=/tmp/poetry_cache

# Development environment variables
export DEVELOPMENT=1
export DEBUG=1
export LOG_LEVEL=DEBUG

# Editor configuration
export EDITOR=nano
export VISUAL=nano

# Language and locale
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Path additions
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.poetry/bin:$PATH"

# Node.js and npm (if needed for frontend tools)
export PATH="$HOME/.npm-global/bin:$PATH"

# Function to activate Python virtual environment if available
activate_venv() {
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "Activated virtual environment: .venv"
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        echo "Activated virtual environment: venv"
    fi
}

# Function to set up development environment
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

# Function to show project information
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

# Auto-completion for common commands
complete -C "poetry" poetry
complete -C "docker" docker
complete -C "docker-compose" docker-compose

# Welcome message for development environment
if [ -t 1 ] && [ "$SHLVL" = 1 ]; then
    echo "Welcome to Pantry Pirate Radio development environment!"
    echo "Type 'project_info' for quick reference or 'dev_setup' to initialize."
fi

# Auto-activate virtual environment when entering project directory
cd() {
    builtin cd "$@"
    if [ -f ".venv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then
        source .venv/bin/activate
    fi
}

# Function to quickly switch between common directories
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

# Export functions for use in subshells
export -f activate_venv
export -f dev_setup
export -f project_info
export -f goto