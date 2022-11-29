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


## Limitations

- CareLink MFA is not supported
- Notification messages are in English

## Requirements

- CareLink account (with MFA NOT ENABLED)
- Guardian Connect CGM outside US: patient or care partner account
- Guardian Connect CGM inside US: **not tested yet!** (possibly a care partner account)
- 7xxG pump outside US: care partner account (same as for Medtronic CareLink Connect app)
- 7xxG pump inside US: care partner account (same as for Medtronic CareLink Connect app)
