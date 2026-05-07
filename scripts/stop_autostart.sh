#!/bin/zsh
set -e

LABEL="com.samg.telegram-ai-bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl disable "gui/$(id -u)/$LABEL" 2>/dev/null || true
echo "Bot autostart stopped."
