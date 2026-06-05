#!/bin/bash
# Mock 1Password CLI for bouy tests. Behavior is driven by env vars so each
# test can script responses without a real vault.
#   OP_MOCK_LOG       : file to append the raw argv of each call (for assertions)
#   OP_MOCK_READ_OUT  : stdout to emit for `op read ...`
#   OP_MOCK_READ_RC   : exit code for `op read ...` (default 0)
#   OP_MOCK_SIGNED_IN : "1" => `op account get`/`op whoami` succeed (default "1")
[ -n "$OP_MOCK_LOG" ] && printf '%s\n' "$*" >> "$OP_MOCK_LOG"
case "$1" in
  read)
    printf '%s' "$OP_MOCK_READ_OUT"
    exit "${OP_MOCK_READ_RC:-0}"
    ;;
  account|whoami)
    [ "${OP_MOCK_SIGNED_IN:-1}" = "1" ] && exit 0 || exit 1
    ;;
  item)
    exit "${OP_MOCK_ITEM_RC:-0}"
    ;;
  *)
    exit 0
    ;;
esac
