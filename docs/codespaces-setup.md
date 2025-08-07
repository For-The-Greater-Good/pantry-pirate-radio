# GitHub Codespaces and Cloud Development Setup

This document explains how to use GitHub Codespaces and other cloud development environments with Pantry Pirate Radio's Docker-based architecture.

## 🚀 Quick Start

### Creating a New Codespace

1. **Go to the repository**: [pantry-pirate-radio](https://github.com/For-The-Greater-Good/pantry-pirate-radio)
2. **Click "Code" → "Codespaces" → "Create codespace"**
3. **Wait for automatic setup**: 
   - Docker and bouy are pre-configured
   - VSCode extensions install automatically
   - Dotfiles configure shell and editor
4. **Initialize the environment**:
   ```bash
   ./bouy setup         # Run configuration wizard
   ./bouy up           # Start services
   ```

### What Gets Configured Automatically

#### Development Environment
- ✅ **Docker & Bouy**: Container orchestration ready
- ✅ **Unified Image**: Pre-built or builds on first use
- ✅ **VSCode Extensions**: 35+ extensions for Python, Docker, Git
- ✅ **Editor Settings**: Auto-formatting, linting, testing
- ✅ **Shell Configuration**: Bouy aliases, git integration
- ✅ **Port Forwarding**: All service ports auto-configured

#### Service Ports (Auto-forwarded)
| Service | Port | URL in Codespace |
|---------|------|------------------|
| FastAPI | 8000 | `https://*.github.dev:8000` |
| Datasette | 8001 | `https://*.github.dev:8001` |
| RQ Dashboard | 9181 | `https://*.github.dev:9181` |
| Content Store | 5050 | `https://*.github.dev:5050` |
| PostgreSQL | 5432 | Internal only |
| Redis | 6379 | Internal only |
| Worker Health | 8080-8089 | `https://*.github.dev:8080` |

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

#### Quick Commands with Bouy
```bash
# Service management
./bouy up            # Start all services
./bouy up --with-init # Start with populated database
./bouy down          # Stop services
./bouy ps            # Check status
./bouy logs app      # View logs

# Testing
./bouy test          # Run all tests
./bouy test --pytest # Run pytest only
./bouy test --black  # Format code
./bouy test --mypy   # Type checking

# Scrapers
./bouy scraper --list # List scrapers
./bouy scraper --all  # Run all scrapers

# Database
./bouy shell db      # Database shell
./bouy exec app python # Python REPL
```

#### Smart Features
- **Unified Image**: Single Docker image for all Python services
- **Auto-configuration**: `.env` setup wizard on first run
- **Git Integration**: Branch info in prompt, aliases configured
- **Port Management**: Automatic forwarding with HTTPS URLs
- **Health Monitoring**: Service health checks and status

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

### Initial Setup in Codespace

1. **Create Codespace**: Wait for environment configuration
2. **Configure application**:
   ```bash
   ./bouy setup         # Interactive setup wizard
   ```
3. **Start services**:
   ```bash
   ./bouy up --with-init # Start with data
   # or
   ./bouy up            # Start empty
   ```
4. **Verify services**:
   ```bash
   ./bouy ps            # Check all services
   ./bouy logs app      # View application logs
   ```
5. **Access applications**:
   - Click on "Ports" tab in VSCode
   - Open port 8000 for API
   - Open port 8001 for Datasette
   - Open port 9181 for RQ Dashboard

### Daily Commands

```bash
# Start development session
./bouy up              # Start all services
./bouy logs -f app     # Monitor application

# Development cycle
./bouy test --pytest   # Run tests
./bouy test --black    # Format code
./bouy test --mypy     # Type check
git add .
git commit -m "message"
git push

# Debugging
./bouy shell app       # Container shell
./bouy exec app python # Python REPL

# End session
./bouy down            # Stop all services
```

### Available Services

After running `./bouy up`, access services through forwarded ports:

| Service | Local URL | Codespace URL |
|---------|-----------|---------------|
| **FastAPI API** | http://localhost:8000 | Via Ports tab → 8000 |
| **API Docs** | http://localhost:8000/docs | Via Ports tab → 8000 + /docs |
| **Datasette** | http://localhost:8001 | Via Ports tab → 8001 |
| **RQ Dashboard** | http://localhost:9181 | Via Ports tab → 9181 |
| **Content Store** | http://localhost:5050 | Via Ports tab → 5050 |
| **Worker Health** | http://localhost:8080 | Via Ports tab → 8080 |

**Note**: Codespaces provides HTTPS URLs with authentication for all forwarded ports.

## 🔧 Customization

### Codespace Configuration

#### Machine Type Selection
Choose appropriate resources:
- **2-core (Basic)**: Light development, testing
- **4-core (Standard)**: Full development with services
- **8-core (Large)**: Heavy workloads, multiple workers

#### Environment Variables
Set secrets in Codespace settings:
1. Go to Settings → Codespaces
2. Add repository secrets:
   - `ANTHROPIC_API_KEY`
   - `OPENROUTER_API_KEY`
   - `DATA_REPO_TOKEN`

#### Personal Dotfiles
1. **Create dotfiles repository** in your GitHub account
2. **Add your configurations**:
   ```bash
   # install.sh in your dotfiles repo
   #!/bin/bash
   # Install custom tools
   npm install -g your-tools
   # Configure git
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```
3. **Enable in GitHub Settings** → Codespaces → Dotfiles

### DevContainer Configuration

The project uses `.devcontainer/devcontainer.json` for Codespace setup:

```json
{
  "name": "Pantry Pirate Radio",
  "dockerComposeFile": "../.docker/compose/docker-compose.codespaces.yml",
  "service": "app",
  "workspaceFolder": "/workspace",
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/git:1": {}
  },
  "postCreateCommand": "./bouy setup",
  "forwardPorts": [8000, 8001, 5432, 6379, 9181, 5050],
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-azuretools.vscode-docker"
      ]
    }
  }
}
```

## 🚨 Troubleshooting

### Docker Issues in Codespace

```bash
# Check Docker status
docker --version
docker ps

# Restart Docker if needed
sudo service docker restart

# Verify bouy is working
./bouy --version
./bouy ps
```

### Service Startup Issues

```bash
# Check service status
./bouy ps

# View logs for errors
./bouy logs | grep ERROR
./bouy logs app

# Rebuild if needed
./bouy build app
./bouy up

# Check port forwarding
# Go to Ports tab in VSCode
# Ensure ports are forwarded
```

### Manual Recovery

If automatic setup fails:

```bash
# Clean and restart
./bouy clean           # Remove volumes
./bouy setup          # Reconfigure
./bouy build app      # Rebuild image
./bouy up            # Start fresh

# Check resources
df -h                 # Disk space
free -h              # Memory
```

### Port Forwarding Issues

1. **Ports not accessible**:
   - Check Ports tab in VSCode
   - Set visibility to "Public" if needed
   - Use provided HTTPS URLs

2. **Service not responding**:
   ```bash
   ./bouy ps | grep app
   ./bouy logs app | tail -20
   ./bouy exec app curl localhost:8000/health
   ```

## Cloud Development Alternatives

### GitPod

1. **Setup `.gitpod.yml`**:
   ```yaml
   image:
     file: .docker/images/app/Dockerfile
   tasks:
     - init: |
         ./bouy setup
         ./bouy build app
     - command: ./bouy up
   ports:
     - port: 8000
       visibility: public
     - port: 8001-9181
       visibility: private
   ```

2. **Launch**: Add `gitpod.io/#` before GitHub URL

### Google Cloud Shell

```bash
# Clone repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose

# Start services
./bouy setup
./bouy up

# Use Web Preview for port 8000
```

### AWS Cloud9

1. **Create environment** with Ubuntu Server
2. **Resize disk** if needed (default is small)
3. **Install dependencies**:
   ```bash
   # Update Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   
   # Clone and setup
   git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
   cd pantry-pirate-radio
   ./bouy setup
   ./bouy up
   ```

## 📚 Related Documentation

- **Docker Development**: [Docker Development](docker-development.md)
- **Docker Startup**: [Docker Startup Sequence](docker-startup-sequence.md)
- **Multi-Worker**: [Multi-Worker Support](multi-worker-support.md)
- **Architecture**: [System Architecture](architecture.md)

## 💡 Tips and Best Practices

### Codespace Optimization

1. **Resource Management**:
   - Stop Codespace when not in use (auto-stops after 30 min)
   - Use appropriate machine size for your workload
   - Clean Docker resources periodically:
     ```bash
     docker system prune -a
     ./bouy clean  # Reset volumes
     ```

2. **Performance Tips**:
   - Use `./bouy up` without `--with-init` for faster starts
   - Scale workers based on machine size:
     ```bash
     # 2-core machine
     WORKER_COUNT=1 ./bouy up
     
     # 8-core machine
     WORKER_COUNT=4 ./bouy up
     ```

3. **Development Workflow**:
   - Use VSCode's integrated terminal for all commands
   - Keep services running during development
   - Use `./bouy logs -f app` in separate terminal for monitoring

### Security in Codespaces

1. **Secrets Management**:
   - Never commit `.env` files
   - Use Codespace secrets for API keys
   - Rotate credentials regularly

2. **Port Visibility**:
   - Keep database ports private
   - Only expose API endpoints as needed
   - Use HTTPS URLs provided by Codespaces

3. **Data Protection**:
   - Codespace data persists between sessions
   - Use `./bouy clean` to remove sensitive data
   - Export important data before deleting Codespace

### Collaboration Features

1. **Live Share**:
   - Share Codespace session with teammates
   - Collaborative debugging and coding
   - Shared terminal and servers

2. **Port Sharing**:
   - Share specific service URLs with team
   - Temporary access for testing
   - Automatic HTTPS and authentication

## Codespace Prebuilds

For faster startup, configure prebuilds:

1. **Repository Settings** → **Codespaces** → **Prebuild**
2. **Configuration**:
   ```yaml
   # Triggers
   - On push to main
   - On pull request
   
   # Prebuild command
   ./bouy build app
   ```
3. **Benefits**:
   - Image pre-built and cached
   - Instant Codespace creation
   - Reduced startup time from 10+ min to <2 min

---

**Last Updated**: January 2025  
**Compatibility**: Docker Compose 2.x, Codespaces, GitPod, Cloud Shell  
**Author**: Pantry Pirate Radio Development Team