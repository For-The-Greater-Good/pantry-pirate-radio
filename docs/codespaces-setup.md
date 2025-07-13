# GitHub Codespaces Setup Guide

This document explains how to use the automated VSCode configuration sync for GitHub Codespaces with Pantry Pirate Radio.

## 🚀 Quick Start

### Creating a New Codespace

1. **Go to the repository**: [pantry-pirate-radio](https://github.com/For-The-Greater-Good/pantry-pirate-radio)
2. **Click "Code" → "Codespaces" → "Create codespace"**
3. **Wait for automatic setup**: The dotfiles will configure everything automatically
4. **Start developing**: Your environment is ready with all tools and extensions

### What Gets Configured Automatically

- ✅ **VSCode Extensions** (35+ extensions for Python, FastAPI, Docker, Git, etc.)
- ✅ **Editor Settings** (formatting, linting, testing, themes)
- ✅ **Shell Configuration** (80+ aliases, auto-venv activation, git integration)
- ✅ **Development Tools** (Poetry, Docker, database tools)
- ✅ **Code Snippets** (FastAPI, Pydantic, testing templates)
- ✅ **Port Forwarding** (FastAPI:8000, PostgreSQL:5432, Redis:6379, etc.)

## 🔧 Configuration Overview

### VSCode Features

#### Essential Extensions
- **Python Development**: Python, MyPy, Black, Ruff, iSort
- **Web Development**: Prettier, YAML, Markdown
- **Database**: SQL Tools, PostgreSQL driver, Redis client
- **Docker**: Docker support, DevContainer integration
- **Git**: GitLens, Git Graph, GitHub integration
- **Quality**: Bandit security, Coverage gutters, ShellCheck

#### Productivity Features
- **Auto-formatting**: Code formats on save with import organization
- **Type checking**: Strict MyPy configuration for robust code
- **Testing**: Integrated pytest with coverage reporting
- **Debugging**: Full debugging support for Python and FastAPI
- **Themes**: GitHub Dark theme with Material icons

### Shell Enhancements

#### Quick Commands
```bash
# Development shortcuts
serve       # Start FastAPI development server
test        # Run pytest with coverage
lint        # Run all linting tools (MyPy, Ruff, Bandit)
dcu         # docker-compose up -d
dcd         # docker-compose down

# Git shortcuts  
gs          # git status
ga          # git add
gcm 'msg'   # git commit -m 'msg'
gp          # git push

# Poetry shortcuts
pr          # poetry run
ptest       # poetry run pytest
pi          # poetry install
```

#### Smart Features
- **Auto-activation**: Virtual environments activate when entering project
- **Git integration**: Current branch shown in terminal prompt
- **Quick navigation**: `goto app|tests|docs|scripts|root` for fast directory switching
- **Project info**: `project_info` command shows development guide

## 📁 File Structure

The configuration is stored in the `dotfiles/` directory:

```
dotfiles/
├── .vscode/
│   ├── settings.json          # Editor configuration
│   ├── extensions.json        # Extension recommendations
│   ├── keybindings.json       # Keyboard shortcuts
│   └── snippets/python.json   # Code snippets
├── .bashrc                    # Bash configuration
├── .zshrc                     # Zsh configuration  
├── .aliases                   # Development aliases
├── install.sh                 # Setup script
└── README.md                  # Detailed documentation
```

## 🎯 Development Workflow

### Starting Development

1. **Create Codespace**: Environment auto-configures with all tools
2. **Check setup**: Run `project_info` for quick reference
3. **Start services**: Use `dcu` to start PostgreSQL, Redis, etc.
4. **Run application**: Use `serve` to start FastAPI development server
5. **Run tests**: Use `test` to execute test suite with coverage

### Daily Commands

```bash
# Start development session
dcu                    # Start all services
serve                  # Start FastAPI server (localhost:8000)

# Development cycle
test                   # Run tests
lint                   # Check code quality
ga . && gcm "message"  # Add and commit changes
gp                     # Push changes

# End session
dcd                    # Stop all services
```

### Available Services

After running `dcu`, these services are available:

- **FastAPI API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **RQ Dashboard**: http://localhost:9181
- **Datasette**: http://localhost:8001
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## 🔧 Customization

### Personal Preferences

To customize the environment for your preferences:

1. **Fork the repository** to your account
2. **Modify dotfiles** in your fork:
   - Edit `dotfiles/.vscode/settings.json` for editor preferences
   - Add extensions in `dotfiles/.vscode/extensions.json`
   - Customize aliases in `dotfiles/.aliases`
3. **Update devcontainer.json** to point to your fork:
   ```json
   "dotfilesRepository": "https://github.com/YOUR_USERNAME/pantry-pirate-radio.git"
   ```

### Project-Wide Changes

For changes that benefit all contributors:

1. **Test changes** in a Codespace
2. **Submit a pull request** with updates to `dotfiles/`
3. **Include documentation** for new features

## 🚨 Troubleshooting

### Extensions Not Loading

```bash
# Check VSCode CLI
code --version

# Reinstall extensions
cd /workspaces/pantry-pirate-radio/dotfiles
./install.sh
```

### Environment Issues

```bash
# Reset shell configuration
source ~/.bashrc

# Check Poetry
poetry --version
poetry install

# Check Docker services
docker-compose ps
```

### Manual Setup

If automatic setup fails:

```bash
# Run dotfiles installer manually
cd /workspaces/pantry-pirate-radio/dotfiles
chmod +x install.sh
./install.sh
```

## 📚 Related Documentation

- **Main Setup**: [Getting Started Locally](getting-started-locally.md)
- **API Documentation**: [API Guide](api.md)
- **Architecture**: [System Architecture](architecture.md)
- **Dotfiles Details**: [dotfiles/README.md](../dotfiles/README.md)

## 💡 Tips

### Productivity Tips
- Use `Ctrl+Shift+P` for VSCode command palette
- Use `Ctrl+`` ` for integrated terminal
- Use `Ctrl+Shift+F` for global search
- Use `F2` for symbol renaming across files

### Development Tips
- **Auto-completion**: Extensive IntelliSense for Python and FastAPI
- **Debugging**: Set breakpoints and debug FastAPI endpoints directly
- **Testing**: Run individual tests with right-click → "Run Test"
- **Git**: Use GitLens for advanced Git features and blame annotations

### Performance Tips
- **Extensions load automatically** but can be disabled if not needed
- **Services auto-start** with port forwarding configured
- **File watching** optimized to exclude cache directories

---

**Last Updated**: July 2025  
**Author**: Pantry Pirate Radio Development Team