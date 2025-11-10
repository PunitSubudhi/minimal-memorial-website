# Adding another domain or host (e.g. xyz.com)

This document explains the minimal steps to make a second domain (for example `xyz.com`) work with the memorial site. It assumes the app is deployed behind a reverse proxy (commonly `nginx`) on a server (EC2 / VPS) and that you control DNS for `xyz.com`. Adjust for your environment (load balancer, Cloud provider, or managed DNS/CDN).

## Summary checklist

- Add DNS records (A/AAAA or CNAME) pointing to your server or load-balancer.
- Open ports 80 and 443 on the server firewall / cloud security group.
- Add an `nginx` server block for `xyz.com` (and `www.xyz.com` if desired).
- Obtain a TLS certificate (Let's Encrypt / Certbot or Cloud provider) and enable HTTPS.
- Configure any app-level settings only if you use absolute URLs or Flask `SERVER_NAME`.
- Test and monitor certificate renewal.

---

## 1) DNS

1. Create DNS records at the registrar/DNS provider:
   - For a single server: add an A record for `xyz.com` pointing to your public IPv4 address.
   - (Optional) Add an AAAA record for IPv6 if you have an IPv6 address.
   - To support `www.xyz.com`, add either an A/AAAA for `www` or a CNAME `www -> xyz.com`.

2. If your app is behind a load balancer (ALB, Cloud Run, Cloudflare, Netlify, etc.), point DNS to the provider's address/alias per their instructions.

3. Wait for DNS propagation (TTL dependent). Use `dig` or online tools to verify.

Quick checks (local macOS zsh):

```zsh
dig +short A xyz.com
dig +short AAAA xyz.com
dig +short CNAME www.xyz.com
```

---

## 2) Firewall / Security Group

- Ensure inbound rules allow HTTP (80) and HTTPS (443) to your server/load balancer.
- If using AWS EC2, update the EC2 Security Group to allow ports 80 and 443 from 0.0.0.0/0 (or a narrower range if you prefer).

---

## 3) Configure nginx (reverse proxy)

Create a server block for `xyz.com`. On Ubuntu this is typically placed at `/etc/nginx/sites-available/xyz.com` and symlinked to `sites-enabled`.

Example minimal `nginx` server block (adjust paths and proxy settings to match your setup):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name xyz.com www.xyz.com;

    # Let Certbot use this location if using --webroot or certbot --nginx
    location /.well-known/acme-challenge/ {
        root /var/www/html; # or your chosen webroot
    }

    # Redirect all HTTP to HTTPS (after cert is in place you can enable this redirect)
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS server block will be created by Certbot when using --nginx, or add a manual block
```

If your Flask app runs behind Gunicorn on a Unix socket, the HTTPS block might look like:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name xyz.com www.xyz.com;

    ssl_certificate /etc/letsencrypt/live/xyz.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/xyz.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/run/gunicorn.sock; # or http://127.0.0.1:8000
    }
}
```

After editing nginx configs, test and reload:

```zsh
sudo nginx -t
sudo systemctl reload nginx
```

---

## 4) Obtain TLS certificate (Let's Encrypt / Certbot)

Recommended: use Certbot's `--nginx` plugin which can create/enable the HTTPS server block automatically.

Example (on Ubuntu / Debian):

```zsh
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d xyz.com -d www.xyz.com
```

If you prefer webroot method (useful with custom setups):

```zsh
sudo certbot certonly --webroot -w /var/www/html -d xyz.com -d www.xyz.com
# Then add the ssl_certificate paths to your nginx config and reload nginx
```

Test auto-renewal (dry run):

```zsh
sudo certbot renew --dry-run
```

Notes:
- Certbot will create necessary files under `/etc/letsencrypt/live/xyz.com/`.
- Ensure the server time is correct (NTP) — Let's Encrypt requires accurate time.

---

## 5) Flask / application considerations

- Flask itself does not require special configuration to serve multiple domains behind nginx. The reverse proxy forwards requests with the Host header preserved.
- Only set `SERVER_NAME` in your Flask `config.py` if you need to generate absolute URLs (via `url_for(..., _external=True)`) or you are using subdomain routing. Setting `SERVER_NAME` can restrict the app to that domain and affects local development, so do this only when necessary.

Example if you must set it (NOT usually required):

```py
# in app/config.py (only if you need it)
SERVER_NAME = 'xyz.com'
```

- If your app builds absolute links for emails or external callbacks, update any configuration or environment variables that hold the canonical site URL (e.g., `SITE_URL`), and make sure notification services use the correct host.

- If you use any host-based allowlist or security middleware (rare in simple Flask apps), add `xyz.com` and `www.xyz.com` to that list.

---

## 6) Redirects and canonical host

If you want `xyz.com` to be canonical and redirect from another domain (or vice versa), implement a 301 redirect at the nginx level. Example:

```nginx
# Redirect example: non-www -> www
server {
    listen 80; server_name xyz.com;
    return 301 https://www.xyz.com$request_uri;
}
```

---

## 7) Testing and verification

- DNS: `dig +short A xyz.com` -> should return the server IP.
- TLS: `curl -I https://xyz.com/` and `openssl s_client -connect xyz.com:443 -servername xyz.com`.
- End-to-end: open the site in a browser, check for lock icon and valid cert.

Certificates should auto-renew via systemd timer or cron added by Certbot. Verify with `sudo certbot renew --dry-run`.

---

## 8) Common pitfalls & troubleshooting

- Problem: DNS points to the old server or wrong IP. Fix: check and update the record; wait for TTL.
- Problem: Ports 80/443 blocked by firewall/SG. Fix: open ports in server firewall and cloud security groups.
- Problem: Certbot fails because `/.well-known` is blocked by a catch-all redirect. Fix: add an exception for `/.well-known/acme-challenge/` in nginx before the redirect.
- Problem: Time skew causing Let’s Encrypt validation failures. Fix: enable NTP.

---

## 9) Optional: Using Cloudflare or a CDN

If you use Cloudflare in front of your server:
- Point DNS to the Cloudflare-provided endpoint.
- Use `Full (strict)` SSL mode and install an origin certificate on your server, or use Certbot on the origin and keep Cloudflare proxy enabled.
- Cloudflare can provide DNS, CDN caching, WAF, and redirect rules; adjust accordingly.

---

## 10) Rollback and notes

- Keep backups of any nginx config files before editing.
- If a cert renewal or config change causes site outage, revert to the previous nginx config and reload.

---

If you'd like, I can also:
- Provide a ready-to-use `nginx` site file tailored to the exact socket/port your Gunicorn uses.
- Add a small section to `app/config.py` explaining how to store a canonical `SITE_URL`.
- Create a short script to test DNS + TLS for a domain.

