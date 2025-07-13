# Getting Started Locally

### Prerequisites and Requirements
• Install Python 3.11 or higher.
• Install [Poetry](https://python-poetry.org/docs/#installation).
• (Optional) Install Docker and Docker Compose.
• (Optional) Ensure PostgreSQL/PostGIS are installed if you don’t use Docker for the database.

### Cloning the Project
```bash
git clone https://github.com/***REMOVED_USER***/pantry-pirate-radio.git
cd pantry-pirate-radio
```

### Local Environment Setup
```bash
poetry install
poetry shell
```
• Configure any environment variables (e.g., DB credentials) in a .env file or your shell.

### Database Configuration
• For local DB, install PostgreSQL + PostGIS. Create a database if needed.
• Or use Docker Compose:
```bash
docker-compose up -d
```
(Makes a local database container.)

### Running the Application
```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
• Visit http://localhost:8000/docs for the API docs.

### Testing and Linting
```bash
poetry run pytest --cov
poetry run mypy .
poetry run ruff .
poetry run black .
```

### Troubleshooting / FAQ
• Port collisions: Check if something else uses port 8000.
• Database connection errors: Confirm DB credentials match your environment variables.

### Devcontainer Comparison
• The devcontainer has everything preconfigured. Locally, you must install or configure all dependencies yourself.
