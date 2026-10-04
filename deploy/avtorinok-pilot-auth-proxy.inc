# Merge into the authorized pilot server {} block after reviewing its existing
# TLS and trusted X-Forwarded-Proto configuration. Replace any existing
# location / handler; do not include duplicate locations.
# General HTTP Basic Auth was disabled by the user for portal testing on 2026-10-04.
# Preserve application-account authentication, noindex, and private API/database ports.
auth_basic off;

location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
