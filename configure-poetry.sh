#!/bin/bash

# Function to add Poetry virtualenv to PATH if not already present
configure_poetry_path() {
    local venv_path=$(poetry env info --path)
    local path_entry="${venv_path}/bin"

    # Check if the path is already in .bashrc
    if ! grep -q "export PATH=\"${path_entry}:\$PATH\"" ~/.bashrc; then
        echo "# Add Poetry virtual environment to PATH" >> ~/.bashrc
        echo "export PATH=\"${path_entry}:\$PATH\"" >> ~/.bashrc
    fi
}

# Run the configuration
configure_poetry_path
