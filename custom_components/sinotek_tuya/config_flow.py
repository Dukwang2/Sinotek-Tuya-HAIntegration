"""Guided setup of a Sinotek charger."""

from hashlib import sha256
from types import MappingProxyType

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from . import client
from .const import DOMAIN, VERSIONS
from .discovery import discover, interfaces
from .accounts import configured_devices

_SECRET = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


async def connection_error(hass, data):
    if len(data["local_key"].encode()) != 16:
        return "invalid_key"
    try:
        await hass.async_add_executor_job(
            client.read, *(data[key] for key in ("device_id", "host", "local_key", "version"))
        )
    except (client.DeviceError, ValueError, OSError):
        return "cannot_connect"
    return None

class SinotekFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Discover a charger and establish its local connection."""

    VERSION = 1

    def __init__(self):
        self.credentials = {}
        self.discovered = {}
        self.selected = {}
        self.account_id = None

    def cloud_accounts(self):
        return [
            entry for entry in self._async_current_entries()
            if entry.data.get("kind") == "cloud" and entry.disabled_by is None
        ]

    async def async_step_user(self, user_input=None):
        if self.cloud_accounts():
            return self.async_show_menu(
                step_id="user", menu_options=["saved_cloud", "methods"]
            )
        return await self.async_step_methods()

    async def async_step_saved_cloud(self, user_input=None):
        accounts = self.cloud_accounts()
        if len(accounts) == 1:
            return await self.use_account(accounts[0])
        if accounts:
            return await self.async_step_account()
        return await self.async_step_methods()


    async def async_step_methods(self, user_input=None):
        self.credentials = {}
        self.selected = {}
        self.account_id = None
        return self.async_show_menu(
            step_id="methods", menu_options=["cloud", "discover", "import", "manual"]
        )

    async def async_step_account(self, user_input=None, errors=None):
        accounts = {entry.entry_id: entry for entry in self.cloud_accounts()}
        if user_input:
            account = accounts.get(user_input["account"])
            if account:
                return await self.use_account(account)
            return await self.async_step_methods()
        choices = [{"value": key, "label": entry.title} for key, entry in accounts.items()]

        return self.async_show_form(
            step_id="account", errors=errors or {},
            data_schema=vol.Schema({vol.Required("account"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=choices)
            )}),
        )

    async def fetch_keys(self, data):
        return await self.hass.async_add_executor_job(
            client.cloud_devices, *(data[k] for k in ("region", "access_id", "access_secret", "user_id"))
        )

    async def use_account(self, entry):
        try:
            self.credentials = await self.fetch_keys(entry.data)
        except Exception:
            return await self.async_step_account(errors={"base": "cloud_failed"})
        self.account_id = entry.entry_id
        return await self.async_step_discover()

    async def async_step_import(self, user_input=None):
        errors = {}
        if user_input:
            try:
                self.credentials = client.import_devices(user_input["devices_json"])
                return await self.async_step_discover()
            except ValueError:
                errors["base"] = "invalid_import"
        return self.async_show_form(
            step_id="import", errors=errors,
            data_schema=vol.Schema({vol.Required("devices_json"): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            )}),
        )

    async def async_step_cloud(self, user_input=None):
        return await self.cloud_form(user_input)

    async def cloud_form(self, user_input, entry=None):
        errors = {}
        if user_input is not None:
            data = {key: value.strip() for key, value in user_input.items()}
            if entry and not data.get("access_secret"):
                data["access_secret"] = entry.data["access_secret"]
            try:
                await self.fetch_keys(data)
            except Exception:
                errors["base"] = "cloud_failed"
            else:
                account_id = sha256(
                    "\0".join(data[k] for k in ("region", "access_id", "user_id")).encode()
                ).hexdigest()
                await self.async_set_unique_id(f"cloud:{account_id}")
                if entry:
                    for other in self._async_current_entries():
                        if other.entry_id != entry.entry_id and other.unique_id == f"cloud:{account_id}":
                            return self.async_abort(reason="already_configured")
                if not entry:
                    self._abort_if_unique_id_configured()
                payload = {"kind": "cloud", **data}
                if entry:
                    return self.async_update_reload_and_abort(
                        entry, data=payload, unique_id=f"cloud:{account_id}",
                        title=f'{data["name"]} ({data["region"]})',
                    )
                return self.async_create_entry(
                    title=f'{data["name"]} ({data["region"]})', data=payload
                )
        schema = vol.Schema({
            vol.Required("name", default="Tuya Cloud"): str,
            vol.Required("region", default="cn"): vol.In(("cn", "us", "us-e", "eu", "eu-w", "sg", "in")),
            vol.Required("access_id"): str,
            (vol.Optional if entry else vol.Required)("access_secret"): _SECRET,
            vol.Required("user_id"): str,
        })
        suggested = {k: v for k, v in entry.data.items() if k != "access_secret"} if entry else {}
        return self.async_show_form(
            step_id="reconfigure_cloud" if entry else "cloud", errors=errors,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    async def async_step_reconfigure_cloud(self, user_input=None):
        return await self.cloud_form(user_input, self._get_reconfigure_entry())

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        if entry.data.get("kind") == "cloud":
            return await self.async_step_reconfigure_cloud(user_input)
        errors = {}
        suggested = {k: entry.data[k] for k in ("host", "version")}
        if user_input is not None:
            suggested = {k: user_input[k] for k in ("host", "version")}
            data = {**entry.data, **suggested}
            if user_input.get("local_key"):
                data["local_key"] = user_input["local_key"]
            error = await connection_error(self.hass, data)
            if not error:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure", errors=errors,
            data_schema=self.add_suggested_values_to_schema(vol.Schema({
                vol.Required("host"): str,
                vol.Required("version"): vol.In(VERSIONS),
                vol.Optional("local_key"): _SECRET,
            }), suggested),
        )

    async def async_step_discover(self, user_input=None):
        if user_input:
            device_id = user_input["device"]
            if device_id == "manual":
                return await self.async_step_manual()
            self.selected = {
                "device_id": device_id,
                **self.credentials.get(device_id, {}),
                **self.discovered.get(device_id, {}),
            }
            if self.account_id and device_id in self.credentials:
                self.selected["cloud_entry_id"] = self.account_id
            if self.selected.get("local_key") and self.selected.get("host") and self.selected.get("version") in VERSIONS:
                return await self.async_step_confirm()
            return await self.async_step_manual()
        self.discovered = await self.hass.async_add_executor_job(
            discover, await interfaces(self.hass)
        )
        configured = configured_devices(self.hass)
        options = []
        for device_id in dict.fromkeys((*self.discovered, *self.credentials)):
            if device_id in configured:
                continue
            record = self.credentials.get(device_id, {}) | self.discovered.get(device_id, {})
            label = record.get("name") or ("Device " + device_id[-6:])
            options.append({"value": device_id, "label": f"{label} ({record.get('host') or 'IP needed'})"})
        options.append({"value": "manual", "label": "Enter device manually"})
        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema({vol.Required("device"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options)
            )}),
        )

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            error = await self.validate(self.selected)
            if not error:
                return self.save_charger(self.selected)
            return await self.async_step_manual(errors={"base": error})
        return self.async_show_form(
            step_id="confirm", data_schema=vol.Schema({}),
            description_placeholders={k: self.selected[k] for k in ("name", "host", "version")},
        )

    async def async_step_manual(self, user_input=None, errors=None):
        if user_input:
            candidate = self.selected | user_input
            error = await self.validate(candidate)
            if not error:
                return self.save_charger(candidate)
            errors = {"base": error}
            self.selected = {k: v for k, v in candidate.items() if k != "local_key"}
        fields = {
            vol.Required("name", default="Sinotek Charger"): str,
            vol.Required("host"): str,
            vol.Required("version", default="3.5"): vol.In(VERSIONS),
        }
        if not self.selected.get("device_id"):
            fields[vol.Required("device_id")] = str
        if not self.selected.get("local_key"):
            fields[vol.Required("local_key")] = _SECRET
        schema = self.add_suggested_values_to_schema(
            vol.Schema(fields), {k: v for k, v in self.selected.items() if k != "local_key"}
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors or {})

    @staticmethod
    def async_get_supported_subentry_types(config_entry):
        return {"charger": ChargerSubentryFlow} if config_entry.data.get("kind") == "cloud" else {}

    def save_charger(self, data):
        if data["device_id"] in configured_devices(self.hass):
            return self.async_abort(reason="already_configured")
        account_id = data.get("cloud_entry_id")
        if not account_id:
            return self.async_create_entry(title=data["name"], data=data)
        account = self.hass.config_entries.async_get_entry(account_id)
        if account is None:
            return self.async_abort(reason="account_removed")
        child = config_entries.ConfigSubentry(
            data=MappingProxyType({k: v for k, v in data.items() if k != "cloud_entry_id"}),
            subentry_type="charger", title=data["name"], unique_id=data["device_id"],
        )
        if not self.hass.config_entries.async_add_subentry(account, child):
            return self.async_abort(reason="already_configured")
        return self.async_abort(reason="charger_added")


    async def validate(self, data):
        if error := await connection_error(self.hass, data):
            self.selected.pop("local_key", None)
            return error
        await self.async_set_unique_id(data["device_id"])
        self._abort_if_unique_id_configured()
        return None


class ChargerSubentryFlow(config_entries.ConfigSubentryFlow):
    """Add or update a charger directly from its account."""

    async def async_step_user(self, user_input=None):
        account = self._get_entry()
        if user_input is None:
            try:
                self.devices = await self.hass.async_add_executor_job(
                    client.cloud_devices, *(account.data[k] for k in ("region", "access_id", "access_secret", "user_id"))
                )
            except Exception:
                return self.async_abort(reason="cloud_failed")
            existing = configured_devices(self.hass)
            found = await self.hass.async_add_executor_job(discover, await interfaces(self.hass))
            self.devices = {
                key: {**data, **found.get(key, {}), "device_id": key}
                for key, data in self.devices.items() if key not in existing
            }
        else:
            self.selected = self.devices[user_input["device"]]
            return await self.async_step_connection()
        if not self.devices:
            return self.async_abort(reason="no_devices")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("device"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    {"value": key, "label": f'{data["name"]} ({data["host"] or "IP needed"})'}
                    for key, data in self.devices.items()
                ])
            )}),
        )

    async def async_step_connection(self, user_input=None):
        return await self.connection_form(user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self.connection_form(user_input, self._get_reconfigure_subentry())

    async def connection_form(self, user_input, child=None):
        original = child.data if child else self.selected
        suggested = {"host": original["host"], "version": original.get("version") or "3.5"}
        errors = {}
        if user_input is not None:
            data = {**original, "host": user_input["host"], "version": user_input["version"]}
            if user_input.get("local_key"):
                data["local_key"] = user_input["local_key"]
            suggested = {k: data[k] for k in ("host", "version")}
            error = await connection_error(self.hass, data)
            if not error:
                if child:
                    return self.async_update_and_abort(self._get_entry(), child, data=data)
                if data["device_id"] in configured_devices(self.hass):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(title=data["name"], data=data, unique_id=data["device_id"])
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure" if child else "connection", errors=errors,
            data_schema=self.add_suggested_values_to_schema(vol.Schema({
                vol.Required("host"): str,
                vol.Required("version"): vol.In(VERSIONS),
                vol.Optional("local_key"): _SECRET,
            }), suggested),
        )
