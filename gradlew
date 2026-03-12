#!/usr/bin/env sh
# Workspace shim for the backend workspace directory.
# If CI invokes `./gradlew` from this workspace, delegate to the frontend wrapper.

exec "$(dirname "$0")/../founder-academy-242883-242892/gradlew" "$@"
