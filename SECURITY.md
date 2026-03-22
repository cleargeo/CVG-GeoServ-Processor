# Security — CVG GeoServ Processor

© Clearview Geographic, LLC — Proprietary Software

## Reporting Vulnerabilities

Report security issues to: azelenski@clearviewgeographic.com  
Subject line: `[SECURITY] GeoServ Processor`

## Notes

- The web UI does NOT perform authentication. Do not expose port 8003 to public internet without a reverse proxy (Caddy/nginx) with auth.
- Config JSON paths should be restricted to authorized data directories.
- Docker production deployment uses Caddy with TLS.
