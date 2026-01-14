# Carelink Token Tool

A Docker-based tool to easily obtain your Carelink login tokens for the Home Assistant Carelink integration.

## Requirements

- Docker installed on your computer
- A Carelink account (patient or follower)

## Quick Start

### Option 1: With auto-fill credentials (Recommended)

1. Copy the example environment file and add your credentials:

```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:

```bash
CARELINK_USERNAME=your@email.com
CARELINK_PASSWORD=yourpassword
```

3. Run the tool:

```bash
docker compose up --build
```

Your credentials will be auto-filled - you only need to solve the CAPTCHA!

**Note:** The auto-fill has a few seconds delay after the page loads. Wait for the fields to be filled before clicking anything.

### Option 2: Manual entry

```bash
docker compose up --build
```

Open `http://localhost:6080/vnc.html?autoconnect=true` and enter credentials manually.

## Usage

1. **Start the container**
2. **Open your browser**: `http://localhost:6080/vnc.html?autoconnect=true`
3. **Wait a few seconds** for credentials to be auto-filled (if configured)
4. **Solve the CAPTCHA** and complete the login
5. **Download your tokens**: `http://localhost:8000/logindata.json` (or find in `./output/`)
6. **Copy to Home Assistant**: Place the file at `/config/carelink_logindata.json` (shared seed)

## Region Selection

For **US region**, add to your `.env` file:

```bash
CARELINK_REGION=us
```

## Output Path

By default the tool writes `logindata.json` locally. To write directly to a different
location (for example a mounted Home Assistant config directory), set:

```bash
CARELINK_OUTPUT_FILE=/config/carelink_logindata.json
```

## Docker Commands

```bash
# Start
docker compose up --build

# Stop
docker compose down

# View logs
docker compose logs -f
```

## Troubleshooting

### Login fails
- Make sure MFA is **disabled** on your Carelink account
- Try using a follower/care partner account
- Check that you're using the correct region (EU vs US)

### Browser doesn't appear
- Wait a few seconds for the container to start
- Refresh the noVNC page

### Token file not created
- Check terminal output for error messages
- Make sure you completed the login including CAPTCHA

## Security

- **Credentials are stored locally** in your `.env` file (which is gitignored)
- **Ports are bound to localhost only** - not accessible from other devices on your network
- The `logindata.json` contains sensitive tokens - keep it secure
- Delete your `.env` file after obtaining your tokens if desired
