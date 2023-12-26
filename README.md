# Carelink Integration - Home Assistant

Custom component for Home Assistant to interact the [Carelink platform by Medtronic](https://carelink.minimed.eu). The api is mostly the works of [@ondrej1024](https://github.com/ondrej1024) who made
the [Python port](https://github.com/ondrej1024/carelink-python-client) from another JAVA api.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/yohangithub)

![Carelink integration preview](https://github.com/yo-han/Home-Assistant-Carelink/blob/develop/carelink-integration-preview.png?raw=true)

## Supported devices

- [Medtronic Guardian Connect CGM](https://hcp.medtronic-diabetes.com.au/guardian-connect) (*to be confirmed*)
- [Medtronic MiniMed 770G pump](https://www.medtronicdiabetes.com/products/minimed-770g-insulin-pump-system) (*to be confirmed*)
- [Medtronic MiniMed 780G pump](https://www.medtronic-diabetes.co.uk/insulin-pump-therapy/minimed-780g-system)

## Installation using HACS

HACS is a community store for Home Assistant. You can install [HACS](https://github.com/custom-components/hacs) and then install `Carelink Integration` from the HACS store.

Then you can install the integration [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=carelink)

### Manual

Copy the `custom_components/carelink` to your `custom_components` folder. Reboot Home Assistant and configure the 'Carelink' integration via the integrations page or press the blue button below.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=carelink)

### Integration Setup

## Session Token
In order to authenticate to the Carelink server, the Carelink client needs a valid access token. This can be obtained by manually logging into a Carelink follower account via Carelink web page. After successful login, the access token (plus country code) can be shown and copied using the Cookie Quick Manager Firefox plugin as follows:

- With the Carelink web page still active, open Cookie Quick Manger from the extensions menu
- Select option "Search Cookies: carelink.minimed.eu"
- Copy value of auth temp token and use it as Session token for initial setup of the Homeassistant Carelink integration 


### Enable debug logging

The [logger](https://www.home-assistant.io/integrations/logger/) integration lets you define the level of logging activities in Home Assistant. Turning on debug mode will show more information about unsupported devices in your logbook.

```yaml
logger:
  default: critical
  logs:
    custom_components.carelink: debug
```

## Limitations

- CareLink MFA is not supported
- Notification messages are in English

## Requirements

- CareLink follower account (with MFA NOT ENABLED)
- Guardian Connect CGM outside US: patient or care partner account
- Guardian Connect CGM inside US: **not tested yet!** (possibly a care partner account)
- 7xxG pump outside US: care partner account (same as for Medtronic CareLink Connect app)
- 7xxG pump inside US: care partner account (same as for Medtronic CareLink Connect app)
