#!/usr/bin/env bash
# The editor user's Epic sign-in on a Linux box: the EOS SDK's persistent credential (~/.local/share/.eos_sdk, what the
# MetaHuman cloud services and Fab log in with), kept in S3 encrypted so a new box starts signed in. Installed as
# /usr/local/bin/ue-epic and /usr/local/bin/ue-epic-url; run as the editor's user (ue-editor.service does).
#
#   ue-epic restore    from $EPIC_S3 if this box has no sign-in yet (the unit runs it before the editor starts)
#   ue-epic save       to $EPIC_S3, SSE-KMS (the unit runs it after the editor stops: a refreshed token is kept)
#   ue-epic status     signed_in=yes|no
#   ue-epic code       the activation code of a pending device sign-in (code=XXXXXXXX), nothing else of the URL
#   ue-epic-url URL    the editor's "browser" (BROWSER=ue-epic-url): keeps the sign-in URL in a 0600 file instead of
#                      opening one, so `film-ue epic-login` can hand the code to a person
#
# $EPIC_S3 (an s3:// object; /etc/default/ue-editor) unset: restore and save do nothing. The credential is a sign-in
# to the whole Epic account: nothing here prints it, and it is never written anywhere but its own folder and S3.
set -euo pipefail
umask 077
SHARE="$HOME/.local/share"
STATE="$HOME/.film-ue"
URLFILE="$STATE/epic-signin.url"

signed_in() { compgen -G "$SHARE/.eos_sdk/keychain/*/persistent_auth/credential" >/dev/null; }

if [ "$(basename "$0")" = ue-epic-url ]; then
    mkdir -p "$STATE"
    printf '%s\n' "${1:-}" > "$URLFILE"
    exit 0
fi

case "${1:-}" in
    status)
        signed_in && echo signed_in=yes || echo signed_in=no ;;
    restore)
        [ -n "${EPIC_S3:-}" ] || { echo "epic: EPIC_S3 unset, nothing to restore"; exit 0; }
        if signed_in; then echo "epic: already signed in here, kept"; exit 0; fi
        tmp="$(mktemp -d)"
        trap 'rm -rf "$tmp"' EXIT
        if ! aws s3 cp --only-show-errors "$EPIC_S3" "$tmp/epic.tgz" 2>/dev/null; then
            echo "epic: no sign-in in S3 (or no access): sign in once with film-ue epic-login"
            exit 0
        fi
        mkdir -p "$tmp/x" "$SHARE"
        tar -xzf "$tmp/epic.tgz" -C "$tmp/x"
        src="$(find "$tmp/x" -type d -name .eos_sdk -prune | head -1)"  # whatever prefix the archive was made with
        [ -n "$src" ] || { echo "epic: the archive has no .eos_sdk folder; left as is"; exit 1; }
        rm -rf "$SHARE/.eos_sdk"
        mv "$src" "$SHARE/.eos_sdk"
        chmod -R u=rwX,go= "$SHARE/.eos_sdk"
        signed_in && echo "epic: sign-in restored" || echo "epic: restored, but no credential inside" ;;
    save)
        [ -n "${EPIC_S3:-}" ] || { echo "epic: EPIC_S3 unset, nothing saved"; exit 0; }
        signed_in || { echo "epic: not signed in here, S3 left as is"; exit 0; }  # never overwrite a sign-in with nothing
        tar -czf - -C "$SHARE" .eos_sdk | aws s3 cp --only-show-errors --sse aws:kms - "$EPIC_S3"
        echo "epic: sign-in saved" ;;
    code)
        [ -f "$URLFILE" ] && grep -o 'userCode=[A-Za-z0-9]*' "$URLFILE" | head -1 | sed 's/userCode=/code=/' || true ;;
    clear-code)
        rm -f "$URLFILE" ;;
    *)
        echo "usage: ue-epic restore|save|status|code|clear-code" >&2
        exit 2 ;;
esac
