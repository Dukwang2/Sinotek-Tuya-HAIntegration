# Sinotek Tuya Charger for Home Assistant

Development build for Sinotek Wi-Fi EV chargers based on the Sinotek DP definitions. The integration uses TinyTuya for the Tuya LAN protocol, active discovery and optional cloud key lookup. The setup and datapoint model are informed by the existing hass-localtuya installation. Protocol versions 3.1–3.5 are accepted, with 3.5 used by the Sinotek chargers tested so far.

## Install a development copy

Copy `custom_components/sinotek_tuya` into the HA config directory's `custom_components` directory, restart HA, then go to **Settings → Devices & services → Add integration → Sinotek Tuya Charger**. The integration uses a separate HA domain. For hardware testing use a dedicated charger or stop its existing LocalTuya connection so two clients do not compete for the same Tuya session.

## Add a charger

Choose **Add Tuya Cloud account** first. Enter a name, region, Access ID, Access Secret and the linked Tuya Smart or Smart Life account UID. The account is saved in a separate HA config entry. Then choose **Add device**. With one saved account, Sinotek uses it automatically; with several accounts, choose the one to use. **Other setup methods** lets you add another account or set up a charger with an existing key. To update or remove an account, use its **Reconfigure** or **Delete** menu. Chargers added through a saved account are listed under that account and use their own Local Keys on the LAN. Removing a cloud account also removes its charger subentries from HA. Standalone chargers can still be added with an imported or manual key.
- **Import existing TinyTuya keys** is an alternative when you have a TinyTuya `devices.json`. Paste its contents locally into HA. Discovery fills the address and protocol and the import fills the name, ID and key. Select the charger and confirm.
- **Discover on the local network** sends a Tuya 3.5 discovery request as well as listening for passive broadcasts. When a key is not already available, supply that device's 16-byte Local Key. You can also enter the IP and device details manually.

Tuya LAN broadcasts do not contain the Local Key. The TinyTuya and TuyAPI wizards obtain keys from Tuya Cloud. TuyAPI Smart Link also requires a developer project. Importing an existing export or entering an already provisioned key avoids requiring cloud credentials in Home Assistant. A first-time customer flow that never requires a Tuya developer project needs a supported Sinotek provisioning or key-delivery service, such as one tied to proof of device ownership.

The charger must be reachable from HA on the LAN. Discovery uses UDP 6666, 6667 and 7000; device communication uses TCP 6668. Use host networking for HA Container when broadcast discovery cannot cross the container network. If IP changes, the integration tries discovery again, authenticates the candidate with the device key and saves the new IP.

Open the existing charger entry's menu and select **Reconfigure** to change its local IP or protocol. Provide a replacement Local Key only when needed. Sinotek verifies the connection before saving and reloads the existing entry, retaining its device and entity IDs.

For upgrades from a deployment with standalone entries linked by cloud account ID, stop HA, back up the configuration directory and run `python tools/migrate_cloud_subentries.py CONFIG/.storage BACKUP_DIR` before starting HA with this version. This moves linked entries under the account while retaining the existing device and entity IDs.

## Entities

The existing LocalTuya DP and display mappings are implemented as native entities attached to the charger. Sensor names are relative to the device. Widgets and automations use readable states and numeric values with units. Raw DP values stay internal. Optional sensors appear after their source data is first reported. Start/pause and approval remain separate actions, and the charging current slider uses 1 A steps from 6 A up to 32 A, capped by reported device limits and the configured maximum. The maximum charging current setting uses the DP 107 presets. Start/pause displays unknown until the charger reports DP 140.

The device page shows both current settings in Controls above Sensors. Home Assistant fixes the order of its native sections. The integration uses the Tuya icons from the Home Assistant brands repository via the local brand directory (Home Assistant 2026.3+).

This is an unreleased development integration. Marketplace distribution, ownership-based key provisioning, and write-path hardware acceptance are separate release work.

### Datapoint coverage

The profile shows optional datapoints after they are reported. DP 122 creates the Single-phase Mode switch. Charge mode, currency, meter binding, load balancing, tariff and schedule are displayed as read-only settings. Schedule and tariff packets require a valid CRC. Reserved temperature mode and legacy NFC/current values are informational.

DPs 20/21 (lighting), 108 (NFC enrollment/removal), 141/142 (factory reset/reboot), 188 (heartbeat), and 189 (obsolete upload count) are intentionally excluded from user-facing entities. DP 121 displays reported meter currents; the integration does not send a recurring query write.


## References

- [TinyTuya](https://github.com/jasonacox/tinytuya)
- [hass-localtuya](https://github.com/xZetsubou/hass-localtuya)
