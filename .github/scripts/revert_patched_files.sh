#!/usr/bin/env bash
# Revert patched files to upstream's version before merging.
# This avoids merge conflicts on files we patch.
#
# Usage: revert_patched_files.sh <upstream_sha> <merge_ref>
set -euo pipefail

UPSTREAM_SHA="$1"
MERGE_REF="$2"
PATCHED_FILES="${PATCHED_FILES:?PATCHED_FILES env var must be set}"

while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    echo "Reverting $file to upstream $MERGE_REF"
    git checkout "$UPSTREAM_SHA" -- "$file" 2>/dev/null || {
        echo "⚠️  $file not found in upstream — it may have been removed or renamed"
    }
done <<< "$PATCHED_FILES"

git commit -m "chore: revert patched files to upstream $MERGE_REF before merge [skip ci]" 2>/dev/null || true
