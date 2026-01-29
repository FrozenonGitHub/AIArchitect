# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Management

This project uses **uv** for package management and dependency installation.

## Virtual Environment

A virtual environment is located at `.venv` in the project root. Always activate it before running commands:

```bash
source .venv/bin/activate
```

## Installing Dependencies

Use uv to install Python packages:

```bash
uv pip install <package-name>
```

## Environment Variables

The `.env` file stores API keys and other sensitive configuration. This file is excluded from version control via `.gitignore` to keep credentials safe. Never commit this file to git.

## Project Structure

- `FastAPITrial/` - FastAPI web application
  - `main.py` - Main application file with API endpoints

## Running the FastAPI Server

To run the FastAPI server in development mode with auto-reload:

### FastAPITrial
```bash
source .venv/bin/activate
cd FastAPITrial
uvicorn main:app --reload
```

The server runs on http://127.0.0.1:8000 by default.

### LevitechDemo
Use the venv Python directly (no activation required):
```bash
cd /Users/wzmacbook/myProj/AIArchitect/LevitechDemo
../.venv/bin/python -m uvicorn main:app --reload
```

## Stopping the Application

If running in foreground:
- Press `CTRL+C` to stop the server

If running in background:
- Find the process: `ps aux | grep uvicorn`
- Kill it: `kill <process_id>`
- Or use: `pkill -f "uvicorn main:app"`
