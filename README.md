# Carelink Integration - Home Assistant

Custom component for Home Assistant to interact the [Carelink platform by Medtronic](https://carelink.minimed.eu) with integrated Nightscout uploader. The api is mostly the works of [@ondrej1024](https://github.com/ondrej1024) who made
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

## Integration Setup

### Carelink Login Data
The needed information for the authentification process can either be provided as file (=logindata.json), or entered during the initial setup of the integration.
#### Get the data
The Home Assistant Carelink Integration needs the initial login data stored in the `logindata.json` file. This file can be created **by running the login script on a PC with a screen**.
The login script from [@ondrej1024](https://github.com/ondrej1024)'s Carelink Python API, written by @palmarci (Pal Marci), was slightly modified and can be found here ["carelink_carepartner_api_login.py"](https://github.com/sedy89/Home-Assistant-Carelink/blob/json_login/utils/carelink_carepartner_api_login.py).

Simply run:
```
python carelink_carepartner_api_login.py 
```

You might need to install the following Python packages to satisfy the script's dependencies:

```
- requests
- OpenSSL (pip install pyOpenSSL)
- seleniumwire (pip install selenium-wire)
```

The script opens a Firefox web browser with the Carelink login page. You have to provide your Carelink patients or follower credentials (recommended) and solve the reCapcha.
On successful completion of the login, the data file will be created with the following structure:

![grafik](https://github.com/sedy89/Home-Assistant-Carelink/assets/65983953/35a60542-03fc-4deb-a14c-c96b0155bdd4)

#### Provide the data
Either the content of the `logindata.json` file can be taken over into the setup of the HA Carelink integration, or the entire file can be uploaded into the custom_componend/carelink folder (recommended).

![grafik](https://github.com/sedy89/Home-Assistant-Carelink/assets/65983953/0a1d8773-7905-4fec-9bff-b3a0f01817b9)

All parameters during setup are optional and a provided file will have a higher priority and overwrite the manual configuration.
If the file was copied to `custom_components/carelink` before the integration setup was started in Home Assistant, all parameters during the setup can stay empty.
With those information, the Home Assistant Carelink Integration will be able to automatically refresh the login data when it expires.
It should be able to do so within one week of the last refresh.

### Scan Interval
The scan interval of the integration can be configured during the integration setup.
User can configure anything between 30 and 300 seconds. Default is 60 seconds.

### Nightscout
To use the Nightscout uploader, it is mandatory to provide the Nightscout URL and the Nightscout API secret.
The Nightscout uploader can upload all SG data and add Treatments with the amount of carbs and insulin.
In order to be able to show the active insulin reported by the pump, the remaining reservoir amount parameter of the nightscout pump plugin has been reused.
![grafik](https://github.com/sedy89/Home-Assistant-Carelink/assets/65983953/2b0297b9-f33f-40ab-89e1-6cef69bf0445)

#### Uploaded data
- DeviceStatus
- Glucose entries
- Basal
- Bolus
- AutoBolus
- Alarms
- Alerts
- Messages

## Enable debug logging

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
