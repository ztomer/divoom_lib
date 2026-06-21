#!/usr/bin/env bash
# tui/lib.sh — Kare TUI output primitives (vendored from ~/projects/scripts/_lib.sh).
# Source at the top of any script:  source "$(dirname "$0")/tui/lib.sh"
# Self-contained: reads tui/stylerc (repo source of truth), no machine dependency.
# Icons: → · ✓ ✗ ⚠   Colors: restrained, NO_COLOR + non-tty aware (degrades to plain text).

_TUI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Icons + colors from the repo stylerc (fall back to Kare defaults if absent).
ICON_START="→"; ICON_STEP="·"; ICON_OK="✓"; ICON_ERR="✗"; ICON_WARN="⚠"
# shellcheck disable=SC1091
[ -f "$_TUI_DIR/stylerc" ] && source "$_TUI_DIR/stylerc"

if [[ -t 1 ]] && [[ "${NO_COLOR:-}" != "1" ]]; then
  : "${C_RESET:=\033[0m}"; : "${C_DIM:=\033[2m}"; : "${C_BOLD:=\033[1m}"
  : "${C_GREEN:=\033[0;32m}"; : "${C_RED:=\033[0;31m}"
  : "${C_YELLOW:=\033[0;33m}"; : "${C_GRAY:=\033[0;90m}"
else
  C_RESET=''; C_DIM=''; C_BOLD=''; C_GREEN=''; C_RED=''; C_YELLOW=''; C_GRAY=''
fi

export ICON_START ICON_STEP ICON_OK ICON_ERR ICON_WARN
export C_RESET C_DIM C_BOLD C_GREEN C_RED C_YELLOW C_GRAY

# ── Log functions ──────────────────────────────────────────────────────
info()  { echo -e "${C_GRAY}${ICON_START}${C_RESET} ${C_DIM}$1${C_RESET}"; }
ok()    { echo -e "${C_GREEN}${ICON_OK}${C_RESET} $1"; }
err()   { echo -e "${C_RED}${ICON_ERR}${C_RESET} $1" >&2; }
warn()  { echo -e "${C_YELLOW}${ICON_WARN}${C_RESET} $1"; }
die()   { err "$1"; exit "${2:-1}"; }
bold()  { echo -e "${C_BOLD}$1${C_RESET}"; }

# ── Dividers ───────────────────────────────────────────────────────────
# Build the rule by concatenation — `tr ' ' '─'` mangles the multibyte ─ (byte-oriented).
hr() {
  local cols="${1:-72}" line="" i
  for ((i = 0; i < cols; i++)); do line+="─"; done
  echo -e "${C_GRAY}${line}${C_RESET}"
}

section() { echo ""; hr; bold "  $1"; hr; }

# ── Utilities ──────────────────────────────────────────────────────────
require_commands() {
  local missing=()
  for cmd in "$@"; do
    command -v "$cmd" &>/dev/null || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required commands: ${missing[*]}"
  fi
}
