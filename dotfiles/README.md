# Pantry Pirate Radio - Dotfiles Configuration

This directory contains automated VSCode and development environment configuration for GitHub Codespaces, ensuring a consistent development experience across all team members and contributors.

## 🚀 Quick Setup

### For GitHub Codespaces

1. **Automatic Setup**: When you create a new Codespace, the configuration will automatically apply
2. **Manual Trigger**: If needed, run the installation manually:
   ```bash
   chmod +x /workspaces/pantry-pirate-radio/dotfiles/install.sh
   /workspaces/pantry-pirate-radio/dotfiles/install.sh
   ```

### For Local Development

1. **Clone the dotfiles**:
   ```bash
   git clone https://github.com/***REMOVED_USER***/pantry-pirate-radio.git
   cd pantry-pirate-radio/dotfiles
   ```

2. **Run the installer**:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

## 📁 Structure

```
dotfiles/
├── .vscode/
│   ├── settings.json          # VSCode editor settings
│   ├── extensions.json        # Recommended extensions
│   ├── keybindings.json       # Custom keyboard shortcuts
│   └── snippets/
│       └── python.json        # Python code snippets
├── .bashrc                    # Bash shell configuration
├── .zshrc                     # Zsh shell configuration
├── .aliases                   # Shell aliases and shortcuts
├── install.sh                 # Automated installation script
└── README.md                  # This documentation
```

## ⚙️ Configuration Details

### VSCode Settings

#### Editor Configuration
- **Python**: Configured for FastAPI development with strict type checking
- **Formatting**: Black formatter with 88-character line length
- **Linting**: MyPy, Ruff, and Bandit for comprehensive code quality
- **Testing**: pytest integration with coverage reporting
- **Auto-save**: Format on save with import organization

#### Theme and UI
- **Theme**: GitHub Dark with Material Icon Theme
- **Layout**: Explorer, search, and extensions panels optimized
- **Terminal**: Bash default with zsh option
- **File Exclusions**: Hides Python cache files and build artifacts

### Extensions (35+ Included)

#### Python Development
- `ms-python.python` - Python language support
- `ms-python.black-formatter` - Code formatting
- `ms-python.mypy-type-checker` - Type checking
- `charliermarsh.ruff` - Fast Python linter
- `ms-python.isort` - Import sorting

#### Web Development
- `ms-toolsai.jupyter` - Jupyter notebook support
- `esbenp.prettier-vscode` - Code formatting for JSON/YAML
- `redhat.vscode-yaml` - YAML language support

#### Database & APIs
- `mtxr.sqltools` - SQL query and database management
- `mtxr.sqltools-driver-pg` - PostgreSQL driver
- `cweijan.vscode-redis-client` - Redis management
- `humao.rest-client` - API testing
- `42crunch.vscode-openapi` - OpenAPI/Swagger support

#### Docker & Containers
- `ms-azuretools.vscode-docker` - Docker support
- `ms-vscode-remote.remote-containers` - Dev container support

#### Git & Collaboration
- `eamodio.gitlens` - Advanced Git features
- `mhutchie.git-graph` - Git repository visualization
- `github.vscode-pull-request-github` - GitHub integration
- `ms-vsliveshare.vsliveshare` - Live collaboration

#### Quality & Security
- `ms-python.bandit` - Security linting
- `timonwong.shellcheck` - Shell script linting
- `ms-python.coverage-gutters` - Test coverage display

### Shell Configuration

#### Aliases (80+ shortcuts)
```bash
# Git shortcuts
gs          # git status
ga          # git add
gcm         # git commit -m
gp          # git push

# Python/Poetry shortcuts
py          # python
pr          # poetry run
ptest       # poetry run pytest
pcov        # poetry run pytest --cov

# Docker shortcuts
dc          # docker-compose
dcu         # docker-compose up
dcd         # docker-compose down

# Project shortcuts
serve       # Start FastAPI server
test        # Run tests
lint        # Run all linting tools
```

#### Environment Features
- **Auto-activation**: Virtual environments activate automatically
- **Git integration**: Branch name in prompt
- **Smart navigation**: Quick directory switching with `goto` command
- **Development helpers**: `dev_setup` and `project_info` commands

### Code Snippets

#### FastAPI Snippets
- `fastapi-router` - Complete router with endpoint
- `fastapi-endpoint` - HTTP endpoint template
- `pydantic-model` - Model with Field descriptions
- `async-func` - Async function template

#### Testing Snippets
- `test-func` - Async test with AAA pattern
- `pytest-fixture` - Pytest fixture template

#### Database Snippets
- `db-query` - SQLAlchemy query template

## 🔧 Customization

### Adding Extensions

1. **Edit extensions.json**:
   ```json
   {
     "recommendations": [
       "existing.extension",
       "new.extension.id"
     ]
   }
   ```

2. **Reinstall extensions**:
   ```bash
   code --install-extension new.extension.id
   ```

### Modifying Settings

1. **Edit settings.json** for global changes
2. **Create workspace settings** in `.vscode/settings.json` for project-specific overrides

### Adding Aliases

1. **Edit .aliases** file:
   ```bash
   # Custom project alias
   alias mycommand='some-long-command-here'
   ```

2. **Reload shell**:
   ```bash
   source ~/.bashrc  # or ~/.zshrc for zsh
   ```

### Adding Snippets

1. **Edit .vscode/snippets/python.json**:
   ```json
   {
     "My Custom Snippet": {
       "prefix": "mysnippet",
       "body": [
         "# Your code here",
         "$1"
       ],
       "description": "Description of snippet"
     }
   }
   ```

## 🐛 Troubleshooting

### Extensions Not Installing

```bash
# Check VSCode CLI availability
code --version

# Manually install extensions
code --install-extension ms-python.python --force
```

### Shell Configuration Not Loading

```bash
# Reload configuration
source ~/.bashrc
# or
source ~/.zshrc

# Check for syntax errors
bash -n ~/.bashrc
```

### Git Configuration Issues

```bash
# Set up Git manually
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Virtual Environment Problems

```bash
# Manually activate environment
source .venv/bin/activate

# Or use Poetry
poetry shell
```

## 🔄 Updating Configuration

### Sync Local Changes to Repository

1. **Test changes locally**
2. **Update dotfiles in repository**:
   ```bash
   git add dotfiles/
   git commit -m "Update dotfiles configuration"
   git push
   ```

3. **New Codespaces will use updated configuration automatically**

### Apply Updates to Existing Environment

```bash
# Re-run the installer
cd /workspaces/pantry-pirate-radio/dotfiles
./install.sh
```

## 📋 Requirements

### System Requirements
- **OS**: Linux (Ubuntu/Debian based)
- **Shell**: Bash or Zsh
- **Editor**: VSCode with Remote-Containers extension
- **Container Runtime**: Docker

### Project Requirements
- **Python**: 3.11+
- **Package Manager**: Poetry
- **Database**: PostgreSQL with PostGIS
- **Cache**: Redis
- **Container Orchestration**: Docker Compose

## 🚨 Security Notes

- **No secrets included**: All configuration is safe to commit
- **Permission handling**: Script uses sudo for system package installation
- **File backups**: Existing configurations are backed up before replacement
- **Non-destructive**: Can be safely run multiple times

## 🤝 Contributing

### Adding New Features

1. **Test locally** in a fresh Codespace
2. **Document changes** in this README
3. **Update installation script** if needed
4. **Submit pull request** with comprehensive testing

### Reporting Issues

1. **Check troubleshooting section** first
2. **Include environment details**:
   - OS and version
   - VSCode version
   - Shell type
   - Error messages

## 📚 Additional Resources

- [VSCode DevContainer Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [GitHub Codespaces Dotfiles](https://docs.github.com/en/codespaces/customizing-your-codespace/personalizing-github-codespaces-for-your-account#dotfiles)
- [Poetry Documentation](https://python-poetry.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

**Last Updated**: July 2025
**Maintainer**: Pantry Pirate Radio Development Team