# Deployment Instructions (AWS EC2 · Gunicorn · Nginx)

These steps describe how to deploy the memorial Flask application on an Amazon Linux EC2 instance, run it behind Gunicorn, proxy requests through Nginx, and enable HTTPS via Let's Encrypt. Adjust usernames, domains, and paths to match your environment.

## 1. Prerequisites
- AWS account with permissions to create EC2 instances, security groups, and IAM roles.
- Domain name pointed to Route 53 (or another DNS provider) with an `A` record you can update later to the EC2 instance's public IP.
- Existing Neon (or other Postgres) database credentials for `DATABASE_URL`, plus a production `SECRET_KEY`.
- Local workstation with SSH access to the new instance.

## 2. Launch the EC2 Instance
1. In the AWS Console, launch an EC2 instance using **Amazon Linux 2023** (ARM or x86; t3.micro or t4g.micro works for light traffic).
2. Create (or select) a key pair for SSH access.
3. Place the instance in a VPC/subnet with internet access.
4. Create a security group that allows:
   - TCP 22 (SSH) from your IP.
   - TCP 80 (HTTP) from `0.0.0.0/0` and `::/0`.
   - TCP 443 (HTTPS) from `0.0.0.0/0` and `::/0`.
5. Note the public IP or hostname for later DNS configuration.

## 3. Connect via SSH
```bash
ssh -i /path/to/key.pem ec2-user@EC2_PUBLIC_IP
```
Consider enabling session manager or SSM for future access hardening once initial setup is complete.

## 4. Update System Packages & Install Dependencies
```bash
sudo dnf update -y
sudo dnf install -y git nginx python3.11 python3.11-devel gcc
```
Install the latest [uv](https://astral.sh/uv) (Python package and environment manager):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
uv --version
```

## 5. Fetch the Application Code
```bash
cd ~
git clone https://github.com/PunitSubudhi/minimal-memorial-website.git
mv minimal-memorial-website memorial
cd memorial
```
If the repository is private, configure SSH or use a GitHub deploy token.

## 6. Configure Environment Variables
1. Copy `.env` (or create a new one) with production credentials:
   ```bash
   cp .env.example .env  # if provided; otherwise create manually
   ```
2. Ensure it contains at least:
   ```ini
   DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require
   SECRET_KEY=<long-random-string>
   NTFY_TOPIC=https://ntfy.sh/JAYDEVSUBUDHINOTIFICATIONS
   ```
   Avoid quoting values when the file is read by systemd; python-dotenv can handle bare values.

## 7. Create the Python Environment
Use uv to create an isolated virtual environment and install dependencies:
```bash
uv venv  # creates .venv/ tied to Python 3.11
source .venv/bin/activate
uv pip install --upgrade pip
uv sync --no-dev --frozen  # installs dependencies from pyproject.lock if present
uv pip install gunicorn    # ensure gunicorn is available in the venv
```
Run database migrations against the production database:
```bash
uv run flask --app main.py db upgrade
```
Deactivate when finished (optional):
```bash
deactivate
```

## 8. Create a Systemd Service for Gunicorn
1. Create a directory for the Gunicorn socket (if using a Unix socket) or use a TCP bind. This guide uses TCP on localhost:
   ```bash
   mkdir -p /home/ec2-user/memorial/logs
   ```
2. Create the unit file:
   ```bash
   sudo tee /etc/systemd/system/memorial.service > /dev/null <<'EOF'
[Unit]
Description=Gunicorn service for Memorial Flask app
After=network.target

[Service]
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/memorial
Environment="PATH=/home/ec2-user/memorial/.venv/bin:/usr/local/bin:/usr/bin"
Environment="FLASK_ENV=production"
ExecStart=/home/ec2-user/memorial/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 main:app
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/ec2-user/memorial/logs/gunicorn.log
StandardError=append:/home/ec2-user/memorial/logs/gunicorn.log

[Install]
WantedBy=multi-user.target
   EOF
   ```
3. Reload systemd and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now memorial.service
   sudo systemctl status memorial.service
   ```
   Check `logs/gunicorn.log` if the service fails to start.

## 9. Configure Nginx as a Reverse Proxy
1. Enable and start Nginx:
   ```bash
   sudo systemctl enable --now nginx
   ```
2. Create the Nginx server block (use `_` to catch all hosts until you have a domain):
    ```bash
    sudo tee /etc/nginx/conf.d/memorial.conf > /dev/null <<'EOF'
upstream memorial_app {
        server 127.0.0.1:8000;
}

server {
        listen 80;
        listen [::]:80;
        server_name _;

        location / {
            proxy_pass http://memorial_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /static/ {
            alias /home/ec2-user/memorial/static/;
            access_log off;
            expires 30d;
        }
}
    EOF
    ```
3. Test and reload Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```
4. Update DNS for your domain to point to the EC2 public IP. Allow time for propagation.

## 10. Secure the Site with Let's Encrypt (HTTPS)
1. Install Certbot and the Nginx plugin:
   ```bash
   sudo dnf install -y certbot python3-certbot-nginx
   ```
2. Request and install certificates (ensure DNS records are live):
   ```bash
   sudo certbot --nginx -d appstotest.co.uk -d www.appstotest.co.uk -d jayadevsubudhi.com -d www.jayadevsubudhi.com
   ```
   - Choose the option to redirect all HTTP traffic to HTTPS when prompted.
   - Certbot will create/adjust the TLS server block and reload Nginx automatically.
3. Confirm renewal automation:
   ```bash
   sudo systemctl status certbot-renew.timer
   ```
   Certificates renew automatically; test with `sudo certbot renew --dry-run`.

## 11. Verify the Deployment
- Visit `https://memorial.example.com` and confirm the site loads securely.
- Check systemd logs if issues appear:
  ```bash
  sudo journalctl -u memorial.service -f
  sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
  ```
- Ensure static assets load correctly via Nginx alias.

## 12. Ongoing Maintenance
- Pull code updates and restart Gunicorn:
  ```bash
  cd ~/memorial
  git pull
  source .venv/bin/activate
  uv sync --no-dev --frozen
  uv run flask --app main.py db upgrade
  sudo systemctl restart memorial.service
  ```
- Monitor certificate expiry with `sudo certbot certificates`.
- Keep the OS patched with `sudo dnf update -y` on a regular cadence.
- Rotate secrets (`SECRET_KEY`, database credentials) through AWS Systems Manager Parameter Store or AWS Secrets Manager for improved security.

Following these steps will provision a production-ready deployment with automatic Gunicorn startup, Nginx request handling, and HTTPS across your domain.
