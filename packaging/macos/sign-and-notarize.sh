#!/bin/bash
set -euo pipefail

# Sign and notarize Quodeq macOS artifacts.
#
# Usage:
#   sign-and-notarize.sh sign-app <path/to/App.app>
#   sign-and-notarize.sh notarize-dmg <path/to/File.dmg>
#
# sign-app is skipped (exit 0) unless MACOS_SIGN_IDENTITY is set.
# notarize-dmg is skipped unless NOTARY_KEY_ID, NOTARY_ISSUER_ID and
# NOTARY_KEY_P8_BASE64 are all set.
# Once the env vars are present, any failure is fatal: an opted-in build
# must never ship a half-signed artifact.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENTITLEMENTS="$SCRIPT_DIR/entitlements.plist"

sign_app() {
    local app="$1"
    if [ -z "${MACOS_SIGN_IDENTITY:-}" ]; then
        echo "==> Signing skipped (MACOS_SIGN_IDENTITY not set)"
        return 0
    fi
    echo "==> Signing $app as '$MACOS_SIGN_IDENTITY'"

    # Nested code first: shared libraries and extension modules anywhere in
    # the bundle, then framework bundles, then the .app itself (which covers
    # the main executable) with entitlements.
    find "$app/Contents" -type f \( -name '*.dylib' -o -name '*.so' \) -print0 |
        while IFS= read -r -d '' bin; do
            codesign --force --options runtime --timestamp \
                --sign "$MACOS_SIGN_IDENTITY" "$bin"
        done

    if [ -d "$app/Contents/Frameworks" ]; then
        find "$app/Contents/Frameworks" -maxdepth 1 -name '*.framework' -print0 |
            while IFS= read -r -d '' fw; do
                codesign --force --options runtime --timestamp \
                    --sign "$MACOS_SIGN_IDENTITY" "$fw"
            done
    fi

    codesign --force --options runtime --timestamp \
        --entitlements "$ENTITLEMENTS" \
        --sign "$MACOS_SIGN_IDENTITY" "$app"

    echo "==> Verifying signature"
    codesign --verify --strict --deep --verbose=2 "$app"
}

notarize_dmg() {
    local dmg="$1"
    if [ -z "${NOTARY_KEY_ID:-}" ] || [ -z "${NOTARY_ISSUER_ID:-}" ] \
        || [ -z "${NOTARY_KEY_P8_BASE64:-}" ]; then
        echo "==> Notarization skipped (notary credentials not set)"
        return 0
    fi

    if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
        echo "==> Signing DMG"
        codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$dmg"
    fi

    local keyfile
    keyfile="$(mktemp -t notary-key.XXXXXX).p8"
    # shellcheck disable=SC2064  # expand keyfile now, not at trap time
    trap "rm -f '$keyfile'" EXIT
    printf '%s' "$NOTARY_KEY_P8_BASE64" | base64 -d > "$keyfile"

    echo "==> Submitting $dmg for notarization (this can take a few minutes)"
    local out submission_id status
    out=$(xcrun notarytool submit "$dmg" \
        --key "$keyfile" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" \
        --wait 2>&1) || true
    echo "$out"
    submission_id=$(echo "$out" | awk '/^[[:space:]]*id: / {print $2; exit}')
    status=$(echo "$out" | awk '/^[[:space:]]*status: / {print $2; exit}')

    if [ "$status" != "Accepted" ]; then
        echo "ERROR: notarization did not succeed (status: ${status:-unknown})"
        if [ -n "$submission_id" ]; then
            echo "==> notarytool log:"
            xcrun notarytool log "$submission_id" \
                --key "$keyfile" --key-id "$NOTARY_KEY_ID" \
                --issuer "$NOTARY_ISSUER_ID" || true
        fi
        exit 1
    fi

    echo "==> Stapling ticket"
    xcrun stapler staple "$dmg"
    echo "==> Gatekeeper check"
    spctl -a -t open --context context:primary-signature -vv "$dmg"
    echo "==> Notarization complete: $dmg"
}

case "${1:-}" in
    sign-app)     sign_app "$2" ;;
    notarize-dmg) notarize_dmg "$2" ;;
    *)
        echo "Usage: $0 {sign-app <App.app>|notarize-dmg <File.dmg>}" >&2
        exit 2
        ;;
esac
