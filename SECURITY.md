# Security Policy

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a security problem.**

Use GitHub's private reporting channel instead:

1. Open the repository on GitHub, go to the **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, the impact, and how to reproduce it.

You get an acknowledgement, and you are kept informed while the report is handled. If private
reporting is disabled on the repository, open a regular issue containing only the statement
"security report available on request" and no technical detail.

Please give the maintainer a reasonable time to ship a fix before disclosing anything publicly.

## What to include

- Type of issue and the component involved (server, CLI, Docker image, front-end).
- Steps to reproduce, with the smallest deck or payload that triggers it.
- The impact you observed, and the access level needed (anonymous LAN, authenticated, ...).

## Supported versions

Quick-Pick has a single maintained line: the latest `main`/`master` state and the most recent
tagged release. Older releases are not patched; upgrade before reporting.

## Hardening a public instance

Quick-Pick is designed for a single user or a small trusted team. Before exposing it to the
Internet, put it behind an authenticating reverse proxy (Caddy, Traefik, Authelia, Cloudflare
Access) or a private network such as Tailscale, and keep it up to date.