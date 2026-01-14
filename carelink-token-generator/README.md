# Carelink Token Generator

A Home Assistant add-on that provides a web interface for generating Carelink login tokens.

## About

This add-on makes it easy for non-technical users to generate the `/config/carelink_logindata.json` shared seed file required by the [Carelink Integration](https://github.com/yo-han/Home-Assistant-Carelink). No Python or Docker knowledge required.

## Features

- Simple web-based interface accessible from the Home Assistant sidebar
- Support for both EU and US Carelink regions
- Automatic token file placement in your Home Assistant config directory
- Secure OAuth authentication flow using headless Firefox

## Installation

1. Add this repository to your Home Assistant add-on store:
   ```
   https://github.com/yo-han/Home-Assistant-Carelink
   ```

2. Find "Carelink Token Generator" in the add-on store and click **Install**

3. Configure your region (EU or US) in the add-on configuration

4. Start the add-on

5. Click **Open Web UI** or find "Carelink Tokens" in your sidebar

## Usage

1. Open the add-on web interface
2. Click **Start Login Process**
3. A browser window will handle the Carelink OAuth flow
4. Log in with your Carelink credentials when prompted
5. Complete any CAPTCHA verification if required
6. The token will be saved automatically to your Home Assistant config directory

After generating the token:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Carelink"
3. Leave the username and password fields empty
4. The integration will automatically use the generated token file and copy it to an entry-specific file

## Configuration

| Option | Description |
|--------|-------------|
| `region` | Your Carelink region: `eu` (Europe) or `us` (United States) |

## Troubleshooting

### Login times out

The login process has a 5-minute timeout. If you encounter a timeout:
- Make sure you complete the login within 5 minutes
- Check that your Carelink credentials are correct
- Try again with the "Start Over" button

### Token file not found

If the Carelink integration can't find the token file:
- Ensure the add-on completed successfully (green checkmark)
- Check that the file exists at `/config/carelink_logindata.json`
- Restart Home Assistant and try adding the integration again

## Technical Details

This add-on runs:
- Flask web server on port 8099 (accessed via Home Assistant ingress)
- Xvfb virtual display for headless browser operation
- Firefox with Selenium for OAuth flow automation

The generated token file is saved to `/config/carelink_logindata.json` which is the Home Assistant config directory.
The integration will copy this shared seed to `/config/carelink_logindata_<entry_id>.json` on first setup.
If you regenerate tokens, the integration will update the entry-specific file when the shared seed is newer.

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/yo-han/Home-Assistant-Carelink/issues).
