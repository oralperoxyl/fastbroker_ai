#!/bin/zsh
set -e

PROJECT_DIR="/Users/samg/telegram-ai-bot"

cd "$PROJECT_DIR"
source "$PROJECT_DIR/.venv/bin/activate"
python "$PROJECT_DIR/main.py"
