#!/bin/sh
set -eu

HTPASSWD_FILE=${PILOT_HTPASSWD_FILE:-/etc/nginx/.htpasswd-suite-s1.denjik.by}
PASSWORD_FILE=${PILOT_PASSWORD_FILE:-${XDG_CONFIG_HOME:-${HOME:-/tmp}/.config}/avtorinok/pilot-password}
USERNAME=${PILOT_AUTH_USER:-pilot}
HTPASSWD_GROUP=${PILOT_HTPASSWD_GROUP:-www-data}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --htpasswd)
            [ "$#" -ge 2 ] || { printf '%s\n' 'Missing path after --htpasswd' >&2; exit 2; }
            HTPASSWD_FILE=$2
            shift 2
            ;;
        --password-file)
            [ "$#" -ge 2 ] || { printf '%s\n' 'Missing path after --password-file' >&2; exit 2; }
            PASSWORD_FILE=$2
            shift 2
            ;;
        --user)
            [ "$#" -ge 2 ] || { printf '%s\n' 'Missing username after --user' >&2; exit 2; }
            USERNAME=$2
            shift 2
            ;;
        *)
            printf '%s\n' 'Usage: generate-pilot-auth.sh [--htpasswd PATH] [--password-file PATH] [--user USER]' >&2
            exit 2
            ;;
    esac
done

case "$USERNAME" in
    ''|*[!A-Za-z0-9_.-]*) printf '%s\n' 'Username may contain only letters, digits, dot, underscore, and hyphen' >&2; exit 2 ;;
esac
command -v openssl >/dev/null 2>&1 || { printf '%s\n' 'openssl is required' >&2; exit 1; }
command -v chgrp >/dev/null 2>&1 || { printf '%s\n' 'chgrp is required' >&2; exit 1; }

if [ -e "$HTPASSWD_FILE" ] || [ -e "$PASSWORD_FILE" ]; then
    printf '%s\n' 'Refusing to overwrite an existing Basic Auth file' >&2
    exit 1
fi

HTPASSWD_DIR=$(dirname -- "$HTPASSWD_FILE")
PASSWORD_DIR=$(dirname -- "$PASSWORD_FILE")
umask 077
mkdir -p "$HTPASSWD_DIR" "$PASSWORD_DIR"
PASSWORD=$(openssl rand -hex 24)
PASSWORD_HASH=$(printf '%s\n' "$PASSWORD" | openssl passwd -6 -stdin)
HTPASSWD_TEMP=
PASSWORD_TEMP=
cleanup() {
    [ -z "$HTPASSWD_TEMP" ] || rm -f -- "$HTPASSWD_TEMP"
    [ -z "$PASSWORD_TEMP" ] || rm -f -- "$PASSWORD_TEMP"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
HTPASSWD_TEMP=$(mktemp "$HTPASSWD_DIR/.htpasswd.XXXXXX")
PASSWORD_TEMP=$(mktemp "$PASSWORD_DIR/.pilot-password.XXXXXX")
printf '%s:%s\n' "$USERNAME" "$PASSWORD_HASH" > "$HTPASSWD_TEMP"
printf '%s\n' "$PASSWORD" > "$PASSWORD_TEMP"
chgrp "$HTPASSWD_GROUP" "$HTPASSWD_TEMP"
chmod 640 "$HTPASSWD_TEMP"
chmod 600 "$PASSWORD_TEMP"
mv "$HTPASSWD_TEMP" "$HTPASSWD_FILE"
mv "$PASSWORD_TEMP" "$PASSWORD_FILE"
trap - EXIT HUP INT TERM
printf 'Created Basic Auth for user %s. Nginx hash file is group-readable; password handoff file: %s (mode 600).\n' "$USERNAME" "$PASSWORD_FILE"
