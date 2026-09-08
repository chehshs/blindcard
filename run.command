#!/bin/zsh
eval "$(/opt/homebrew/bin/brew shellenv)"
CD_PATH="$(cd "$(dirname "$0")" && pwd)"
cd "$CD_PATH"

if [ -x "$CD_PATH/.venv/bin/python" ]; then
  PYTHON="$CD_PATH/.venv/bin/python"
else
  PYTHON="/usr/bin/env python3"
fi

exec "$PYTHON" "$CD_PATH/make_pdf.py"
