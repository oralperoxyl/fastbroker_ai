#!/bin/zsh
set -e

LABEL="com.samg.telegram-ai-bot"
PROJECT_DIR="/Users/samg/telegram-ai-bot"
SOURCE_PLIST="$PROJECT_DIR/$LABEL.plist"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
cp "$SOURCE_PLIST" "$PLIST"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Bot autostart installed and started."
