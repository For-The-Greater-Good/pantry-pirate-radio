# 🏴‍☠️ Pantry Pirate Radio v0.2 - "Sailing the Container Seas"

*Ahoy, data liberators! We're launching our fleet of containerized vessels into the cloud, ready to sail the digital seas with automated deployments!*

## 🚢 Container Fleet Launch

We're excited to announce **Pantry Pirate Radio v0.2**, which brings continuous deployment capabilities and production-ready container infrastructure to our food security data aggregation system.

## 🗺️ Charting New Territory

### What's New in v0.2?

With this release, we're making it easier than ever to deploy Pantry Pirate Radio to production environments. Our new continuous deployment pipeline automatically builds and publishes Docker images to GitHub Container Registry, enabling seamless deployments across any Docker-compatible infrastructure.

### 🏴‍☠️ Liberation Through Automation

Just as radio pirates automated their broadcasts to reach more listeners, we're automating our deployments to make food security data more accessible. Every commit to main, every version tag - automatically built, tested, and ready to sail.

## ⚓ Key Features in v0.2

### 🐳 Continuous Deployment Pipeline
- **Automated Docker builds** for all services on GitHub Container Registry (ghcr.io)
- **Multi-service container images**: app, worker, recorder, scraper, datasette-exporter, datasette
- **Smart tagging strategy** with version tags, branch tags, and SHA tags
- **CI/CD integration** - deployments only run after all tests pass
- **GitHub Actions caching** for faster build times

### 📦 Production-Ready Infrastructure
- **New `docker-compose.prod.yml`** for production deployments using pre-built images
- **Configurable deployments** via environment variables
- **Consistent service architecture** between development and production
- **Automated release creation** with Docker pull commands

### 🛠️ Infrastructure Improvements
- **Build optimization** with layer caching
- **Secure container registry** authentication
- **Provenance attestation** for supply chain security
- **Platform compatibility** (currently linux/amd64, with ARM64 planned)

## 🎯 Deployment Made Simple

Deploy the latest version with just a few commands:

```bash
# Using docker-compose with production images
docker-compose -f docker-compose.prod.yml up -d

# Or specify a version
DOCKER_TAG=v0.2 docker-compose -f docker-compose.prod.yml up -d
```

## 📊 What's Next?

### Coming in Future Releases:
- **ARM64 support** for Apple Silicon and ARM servers
- **Kubernetes manifests** for cloud-native deployments
- **Automated security scanning** in CI/CD pipeline
- **Multi-registry support** for redundancy
- **Container health monitoring** and auto-recovery

## 🏴‍☠️ Join the Crew

We're building a community of data pirates committed to breaking down barriers in food security information. Your contributions help ensure that vital community resources remain accessible to all.

### How to Contribute:
- 🐛 Report bugs and issues
- 💡 Suggest new features
- 🔧 Submit pull requests
- 📖 Improve documentation
- 🗺️ Add new data sources

## 🙏 Acknowledgments

Special thanks to all contributors who helped make this release possible. Together, we're charting a course toward universal access to food security data!

---

*"Information wants to be free, especially when it feeds communities."*

**Full Changelog**: https://github.com/For-The-Greater-Good/pantry-pirate-radio/compare/v0.1...v0.2