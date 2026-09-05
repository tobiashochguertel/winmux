#!/usr/bin/env bash
# Apply all .patch files in .github/patches/ in order.
# Idempotent: skips patches that are already applied.
# Fails loudly if a patch doesn't apply cleanly.
#
# Usage: apply_patches.sh
set -euo pipefail

PATCH_DIR=".github/patches"

if [[ ! -d "$PATCH_DIR" ]]; then
    echo "⚠️  $PATCH_DIR not found — no patches to apply"
    exit 0
fi

for patch in "$PATCH_DIR"/*.patch; do
    [[ ! -f "$patch" ]] && continue
    name=$(basename "$patch")

    # Idempotency: if reverse applies cleanly, the patch is already present
    if git apply --reverse --check "$patch" 2>/dev/null; then
        echo "✅ $name already applied"
        continue
    fi

    # Check if it applies cleanly
    if git apply --check "$patch" 2>/dev/null; then
        git apply "$patch"
        echo "✅ applied $name"
    else
        echo "::error::$name does not apply cleanly — upstream may have changed the surrounding code"
        exit 1
    fi
done
