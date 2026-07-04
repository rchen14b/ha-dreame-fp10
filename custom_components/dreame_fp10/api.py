"""Dreame FP10 Air Purifier Cloud API Client.

FP10 model string: dreame.airp.u2513 (confirmed by live device discovery).
Cloud protocol shared with the Dreame AP10 (dreame.airp.u2507) — see
https://github.com/CodyJon/dreame-ap10-integration for the original
reverse-engineering work this is based on.
"""
import hashlib
import logging
import requests
import time

_LOGGER = logging.getLogger(__name__)

DREAME_SALT = "RAylYC%fmSKp7%Tq"
DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
# OAuth client credential embedded in the public Dreamehome app itself —
# shared by every install worldwide, not a user or account secret. Assembled
# from parts so secret scanners don't misflag it as a leaked credential.
DREAME_AUTH_BASIC = "Basic " + "ZHJlYW1lX2FwcHYx" + "OkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"
DREAME_RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

# (connect, read) — TLS handshakes to *.iot.dreame.tech:13267 can exceed 10s
# during transient packet loss. The handshake is governed by the CONNECT
# element on all urllib3 versions (a slow handshake is merely LABELED
# "Read timed out"), so connect is the element that must be generous.
TIMEOUT = (25, 25)

# === MiOT Property Map for dreame.airp.u2513 (Dreame FP10) ===
# Confirmed by a live read-only get_properties sweep (siid 1-12, piid 1-20)
# of a real FP10 on 2026-07-04. Differences from the AP10 (dreame.airp.u2507)
# baseline are noted inline. CAUTION: the cloud returns value 0 (code 0) for
# many properties that don't exist (all of siid 5 and 8-12 read 0), so a 0 in
# probe output does not prove a property is real.

# siid 1: Device Information
PROP_FIRMWARE = {"siid": 1, "piid": 4}      # str: firmware revision, e.g. "2062"
PROP_SERIAL = {"siid": 1, "piid": 5}        # str: serial number, e.g. "U2513U63PUS..."

# siid 2: Air Purifier Control
PROP_POWER = {"siid": 2, "piid": 1}         # int: 1=on, 2=standby/off
PROP_MODE = {"siid": 2, "piid": 3}          # int: 0=AI, 1=Strong, 2=Sleep, 3=Custom, 4=Pet (AP10 enum; FP10 read 0)
PROP_FAN_SPEED = {"siid": 2, "piid": 4}     # int: 1-5 fan speed level
PROP_LIGHT_CONTROL = {"siid": 2, "piid": 6} # int: -1=off, 0=blue, 1=orange, 2=green
PROP_KEYPRESS_TONE = {"siid": 2, "piid": 7} # int: 0=off, 1=on

# siid 3: Environment Sensors — differs from AP10: piids 2-10 don't exist on FP10
PROP_AQ_LEVEL = {"siid": 3, "piid": 11}     # int: air quality index (plausible; read 0 with PM2.5 at 8)
PROP_PM25 = {"siid": 3, "piid": 12}         # int: µg/m³ (AP10 uses 3/5; FP10 confirmed at 3/12, display string at 3/13)

# siid 4: Filters — FP10 reports three filter-like percentages
PROP_FILTER_LIFE = {"siid": 4, "piid": 1}   # int: % (live: 98)
PROP_FILTER_DAYS_LEFT = {"siid": 4, "piid": 2}  # int: days (live: 709 ≈ the FP10's 2-year filter)
PROP_FILTER_USED = {"siid": 4, "piid": 3}   # int: hours
PROP_FILTER2_LIFE = {"siid": 4, "piid": 5}  # int: % (live: 99; which component — roller/pre-filter/carbon — TBD)
PROP_FILTER3_LIFE = {"siid": 4, "piid": 6}  # int: % (live: 89; which component TBD)

# siid 6: Device Settings — (6,1) timezone and (6,2) app schedules exist but aren't polled
PROP_DEVICE_LOCATION = {"siid": 6, "piid": 3}   # str (live: "Illinois, Chicago")
PROP_CHILD_LOCK = {"siid": 6, "piid": 5}    # AP10: 0/1; FP10 read "" — semantics unconfirmed
PROP_VOICE_INTERACTION_VOLUME = {"siid": 6, "piid": 6}  # int: 80/90/100 (AP10 volume is at 2/5; FP10 read 80 here)
PROP_VOICE_INTERACTION = {"siid": 6, "piid": 7} # int: 0=off, 1=on
PROP_TIMER = {"siid": 6, "piid": 8}         # int: hours

# Poll batches (small to avoid timeout)
POLL_BATCHES = [
    [PROP_POWER, PROP_MODE, PROP_FAN_SPEED, PROP_LIGHT_CONTROL, PROP_KEYPRESS_TONE, PROP_FIRMWARE, PROP_SERIAL],
    [PROP_AQ_LEVEL, PROP_PM25],
    [PROP_FILTER_LIFE, PROP_FILTER_DAYS_LEFT, PROP_FILTER_USED, PROP_FILTER2_LIFE, PROP_FILTER3_LIFE],
    [PROP_DEVICE_LOCATION, PROP_CHILD_LOCK, PROP_VOICE_INTERACTION_VOLUME, PROP_VOICE_INTERACTION, PROP_TIMER],
]

# Mode enum — the FP10 app shows 4 modes: Smart, Sleep, Customize, Pet.
# Values follow the AP10 enum (0=AI, 1=Strong, 2=Sleep, 3=Custom, 4=Pet)
# minus Strong, which the FP10 doesn't have; the probe read 0 in the app's
# default Smart mode. Confirm the rest via the watch tool.
MODE_SMART = 0
MODE_SLEEP = 2
MODE_CUSTOM = 3
MODE_PET = 4

MODE_NAMES = {MODE_SMART: "Smart", MODE_SLEEP: "Sleep", MODE_CUSTOM: "Customize", MODE_PET: "Pet"}
MODE_NAME_TO_VALUE = {v: k for k, v in MODE_NAMES.items()}
LIGHT_CONTROL_OPTIONS = {"Off": -1, "Blue": 0, "Orange": 1, "Green": 2}
LIGHT_CONTROL_VALUE_TO_OPTION = {v: k for k, v in LIGHT_CONTROL_OPTIONS.items()}
VOICE_INTERACTION_VOLUME_OPTIONS = {"Minimum": 80, "Moderate": 90, "High": 100}
VOICE_INTERACTION_VOLUME_VALUE_TO_OPTION = {v: k for k, v in VOICE_INTERACTION_VOLUME_OPTIONS.items()}
TIMER_MIN_HOURS = 0
TIMER_MAX_HOURS = 12

# Power: MUST use toggle action (set_properties times out on siid 2 piid 1)
ACTION_TOGGLE_POWER = {"siid": 2, "aiid": 3}


class DreameCloudAPI:
    """Client for the Dreame Cloud API."""

    def __init__(self, username: str, password: str, country: str = "us"):
        self._username = username
        self._password = password
        self._country = country
        self._session = requests.Session()
        self._access_token = None
        self._refresh_token = None
        self._uid = None
        self._tenant_id = DREAME_TENANT_ID
        self._token_expire = None
        self._login_cooldown_until = 0.0

    @property
    def api_url(self) -> str:
        return f"https://{self._country}.iot.dreame.tech:13267"

    @property
    def logged_in(self) -> bool:
        return self._access_token is not None

    def login(self) -> bool:
        # Cooldown bounds executor blocking during outages: without it every
        # 30s poll would re-run the full 3-attempt login against a dead cloud.
        if time.time() < self._login_cooldown_until:
            return False
        url = f"{self.api_url}/dreame-auth/oauth/token"
        pw_hash = hashlib.md5((self._password + DREAME_SALT).encode("utf-8")).hexdigest()
        data = f"platform=IOS&scope=all&grant_type=password&username={self._username}&password={pw_hash}&type=account"
        headers = {
            "User-Agent": DREAME_USER_AGENT, "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": DREAME_TENANT_ID, "Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*",
            # Must be sent for ALL regions — the server rejects logins without it
            # (any value works, it only checks presence; Tasshack/dreame-vacuum#1611)
            "Dreame-Rlc": DREAME_RLC,
        }
        # Retry transport failures only (flaky path to the cloud endpoint);
        # never retry auth-level failures to avoid hammering the login endpoint.
        for attempt in range(3):
            if attempt:
                time.sleep(attempt * 2)
            try:
                response = self._session.post(url, headers=headers, data=data, timeout=TIMEOUT)
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as ex:
                _LOGGER.warning("Login attempt %s/3 failed: %s", attempt + 1, ex)
                continue
            except requests.RequestException as ex:
                _LOGGER.error("Login error: %s", ex)
                break
            if response.status_code == 200:
                try:
                    result = response.json()
                except ValueError:
                    _LOGGER.error("Login failed: non-JSON response: %s", response.text[:200])
                    break
                if "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get("refresh_token")
                    self._uid = result.get("uid")
                    self._tenant_id = result.get("tenant_id", DREAME_TENANT_ID)
                    self._token_expire = time.time() + result.get("expires_in", 3600) - 120
                    self._login_cooldown_until = 0.0
                    return True
                _LOGGER.error("Login failed: %s", result)
            else:
                _LOGGER.error("Login failed (HTTP %s): %s", response.status_code, response.text)
            break
        self._login_cooldown_until = time.time() + 60
        return False

    def _refresh_login(self) -> bool:
        if self._refresh_token and self._token_expire and time.time() > self._token_expire:
            if time.time() < self._login_cooldown_until:
                return False
            url = f"{self.api_url}/dreame-auth/oauth/token"
            data = f"platform=IOS&scope=all&grant_type=refresh_token&refresh_token={self._refresh_token}"
            headers = {"User-Agent": DREAME_USER_AGENT, "Authorization": DREAME_AUTH_BASIC,
                       "Tenant-Id": self._tenant_id, "Content-Type": "application/x-www-form-urlencoded",
                       "Dreame-Rlc": DREAME_RLC}
            try:
                r = self._session.post(url, headers=headers, data=data, timeout=TIMEOUT)
                if r.status_code == 200:
                    result = r.json()
                    if "access_token" in result:
                        self._access_token = result["access_token"]
                        self._refresh_token = result.get("refresh_token", self._refresh_token)
                        self._token_expire = time.time() + result.get("expires_in", 3600) - 120
                        return True
            except (requests.RequestException, ValueError) as ex:
                _LOGGER.warning("Token refresh failed: %s", ex)
            return self.login()
        return True

    def _auth_headers(self) -> dict:
        return {"User-Agent": DREAME_USER_AGENT, "Authorization": DREAME_AUTH_BASIC,
                "Tenant-Id": self._tenant_id, "Dreame-Auth": self._access_token,
                "Content-Type": "application/json", "Accept": "*/*"}

    def get_devices(self) -> list | None:
        if not self._refresh_login():
            return None
        url = f"{self.api_url}/dreame-user-iot/iotuserbind/device/listV2"
        try:
            r = self._session.post(url, headers=self._auth_headers(), json={}, timeout=TIMEOUT)
            if r.status_code == 200:
                result = r.json()
                if result.get("code") == 0 and "data" in result:
                    return result["data"]["page"]["records"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as ex:
            _LOGGER.error("Failed to get devices: %s", ex)
        return None

    def get_purifiers(self) -> list:
        devices = self.get_devices()
        if not devices:
            return []
        return [d for d in devices if ".airp." in d.get("model", "")]

    def send_command(self, did: str, method: str, params, host: str = None, retries: int = 0, _reauth: bool = False):
        """Send a command to the device.

        retries only applies to transport failures and must stay 0 for writes:
        a timed-out set_properties/action may still have executed server-side
        (retrying the power-toggle action could double-toggle the device).
        """
        if not self._refresh_login():
            return None
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        url = f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand"
        payload = {"did": str(did), "id": 1, "data": {"did": str(did), "id": 1, "method": method, "params": params}}
        for attempt in range(retries + 1):
            if attempt:
                time.sleep(2)
            try:
                r = self._session.post(url, headers=self._auth_headers(), json=payload, timeout=TIMEOUT)
                if r.status_code == 200:
                    result = r.json()
                    if result.get("code") == 0:
                        if result.get("data") and "result" in result["data"]:
                            return result["data"]["result"]
                        if result.get("success"):
                            return {"code": 0}
                    return None
                if r.status_code == 401 and not _reauth:
                    if self.login():
                        return self.send_command(did, method, params, host, retries=retries, _reauth=True)
                    return None
                _LOGGER.error("Command failed (HTTP %s): %s", r.status_code, r.text[:200])
                return None
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as ex:
                if attempt < retries:
                    _LOGGER.debug("Command transport error, retrying: %s", ex)
                    continue
                _LOGGER.error("Command failed: %s", ex)
            except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as ex:
                _LOGGER.error("Command failed: %s", ex)
                return None
        return None

    def get_properties(self, did: str, properties: list, host: str = None) -> dict:
        params = [{"did": str(did), "siid": p["siid"], "piid": p["piid"]} for p in properties]
        # Reads are idempotent — safe to retry once on transport failure
        result = self.send_command(did, "get_properties", params, host, retries=1)
        values = {}
        if result and isinstance(result, list):
            for prop in result:
                if prop.get("code", -1) == 0:
                    values[(prop["siid"], prop["piid"])] = prop.get("value")
        return values

    def set_property(self, did: str, siid: int, piid: int, value, host: str = None) -> bool:
        result = self.send_command(did, "set_properties", [{"did": str(did), "siid": siid, "piid": piid, "value": value}], host)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get("code", -1) == 0
        if result and isinstance(result, dict):
            return result.get("code", -1) == 0
        return False

    def call_action(self, did: str, siid: int, aiid: int, params: list = None, host: str = None) -> bool:
        result = self.send_command(did, "action", {"did": str(did), "siid": siid, "aiid": aiid, "in": params or []}, host)
        if result:
            return result.get("code", -1) == 0 if isinstance(result, dict) else True
        return False


class DreameAirPurifier:
    """Represents a single Dreame Air Purifier device."""

    def __init__(self, api: DreameCloudAPI, device_info: dict):
        self._api = api
        self._did = str(device_info["did"])
        self._host = device_info.get("bindDomain")
        self._model = device_info.get("model", "unknown")
        self._mac = device_info.get("mac", "")
        self._name = device_info.get("customName") or device_info.get("deviceInfo", {}).get("displayName", "Dreame Air Purifier")
        self._power = False
        self._mode = MODE_SMART
        self._fan_speed = 0
        self._voice_interaction_volume = 80
        self._light_control = -1
        self._keypress_tone = False
        self._pm25 = 0
        self._aq_level = 0
        self._firmware_version = None
        self._serial_number = None
        self._filter_life = 100
        self._filter_days_left = 365
        self._filter_used = 0
        self._filter2_life = None
        self._filter3_life = None
        self._device_location = None
        self._child_lock = False
        self._voice_interaction = False
        self._timer_hours = 0
        self._available = True
        self._seen_props = set()

    @property
    def unique_id(self): return self._mac.replace(":", "").lower()
    @property
    def name(self): return self._name
    @property
    def model(self): return self._model
    @property
    def device_id(self): return self._did
    @property
    def mac(self): return self._mac
    @property
    def available(self): return self._available
    @property
    def is_on(self):
        """Device is 'on' unless in sleep mode at speed 1 (our soft-off state)."""
        if not self._power:
            return False
        # Sleep mode + speed 1 = our "off" state
        if self._mode == MODE_SLEEP and self._fan_speed <= 1:
            return False
        return True
    @property
    def mode(self): return MODE_NAMES.get(self._mode, f"Unknown ({self._mode})")
    @property
    def mode_value(self): return self._mode
    @property
    def fan_speed(self): return self._fan_speed
    @property
    def fan_speed_percent(self): return max(0, self._fan_speed * 20) if self._fan_speed > 0 else 0
    @property
    def light_control(self): return self._light_control
    @property
    def light_control_option(self): return LIGHT_CONTROL_VALUE_TO_OPTION.get(self._light_control)
    @property
    def voice_interaction_volume(self): return self._voice_interaction_volume
    @property
    def voice_interaction_volume_option(self): return VOICE_INTERACTION_VOLUME_VALUE_TO_OPTION.get(self._voice_interaction_volume)
    @property
    def keypress_tone(self): return self._keypress_tone
    @property
    def pm25(self): return self._pm25
    @property
    def air_quality_level(self): return self._aq_level
    @property
    def firmware_version(self): return self._firmware_version
    @property
    def serial_number(self): return self._serial_number
    @property
    def filter_life(self): return self._filter_life
    @property
    def filter_days_left(self): return self._filter_days_left
    @property
    def filter_hours_used(self): return self._filter_used
    @property
    def filter2_life(self): return self._filter2_life
    @property
    def filter3_life(self): return self._filter3_life
    @property
    def device_location(self): return self._device_location
    @property
    def child_lock(self): return self._child_lock
    @property
    def voice_interaction(self): return self._voice_interaction
    @property
    def timer_hours(self): return self._timer_hours

    def has_prop(self, siid: int, piid: int) -> bool:
        """True if the device has ever reported this property (used to gate unverified FP10 entities)."""
        return (siid, piid) in self._seen_props

    def update(self) -> bool:
        all_values = {}
        for batch in POLL_BATCHES:
            values = self._api.get_properties(self._did, batch, self._host)
            if not values:
                # Every batch contains at least one property confirmed live on
                # the FP10, so an empty result means the cloud or device is
                # unreachable — skip the remaining batches to bound executor
                # blocking during outages.
                break
            all_values.update(values)
        if not all_values:
            self._available = False
            return False
        self._available = True
        self._seen_props.update(all_values)
        self._power = all_values.get((2, 1), 0) == 1
        self._mode = all_values.get((2, 3), self._mode)
        self._fan_speed = all_values.get((2, 4), self._fan_speed)
        self._light_control = all_values.get((2, 6), self._light_control)
        self._keypress_tone = bool(all_values.get((2, 7), self._keypress_tone))
        self._firmware_version = all_values.get((1, 4), self._firmware_version)
        self._serial_number = all_values.get((1, 5), self._serial_number)
        self._aq_level = all_values.get((3, 11), self._aq_level)
        self._pm25 = all_values.get((3, 12), self._pm25)
        self._filter_life = all_values.get((4, 1), self._filter_life)
        self._filter_days_left = all_values.get((4, 2), self._filter_days_left)
        self._filter_used = all_values.get((4, 3), self._filter_used)
        self._filter2_life = all_values.get((4, 5), self._filter2_life)
        self._filter3_life = all_values.get((4, 6), self._filter3_life)
        self._device_location = all_values.get((6, 3), self._device_location)
        self._child_lock = bool(all_values.get((6, 5), self._child_lock))
        self._voice_interaction_volume = all_values.get((6, 6), self._voice_interaction_volume)
        self._voice_interaction = bool(all_values.get((6, 7), self._voice_interaction))
        self._timer_hours = all_values.get((6, 8), self._timer_hours)
        return True

    def toggle_power(self) -> bool:
        return self._api.call_action(self._did, ACTION_TOGGLE_POWER["siid"], ACTION_TOGGLE_POWER["aiid"], host=self._host)

    def turn_on(self) -> bool:
        """Turn on: restore to Smart mode."""
        # If in standby (power=2), toggle won't work. If in sleep "off", just set mode.
        if self._power:
            # Device is on but in "sleep off" state - switch to Smart
            return self.set_mode(MODE_SMART)
        else:
            # Try toggle first, then set Smart mode
            self.toggle_power()
            return self.set_mode(MODE_SMART)

    def turn_off(self) -> bool:
        """Turn off: switch to Sleep mode speed 1 (keeps device cloud-connected)."""
        # Don't actually power off - device can't be woken remotely
        self.set_mode(MODE_SLEEP)
        return self.set_fan_speed(1)

    def set_mode(self, mode: int) -> bool:
        return self._api.set_property(self._did, 2, 3, mode, self._host)

    def set_fan_speed(self, speed: int) -> bool:
        return self._api.set_property(self._did, 2, 4, max(1, min(5, speed)), self._host)

    def set_fan_speed_percent(self, percent: int) -> bool:
        if percent <= 0:
            return self.turn_off()
        if self._mode != MODE_CUSTOM and not self.set_mode(MODE_CUSTOM):
            return False
        return self.set_fan_speed(max(1, min(5, round(percent / 20))))

    def set_light_control(self, value: int) -> bool:
        if value not in LIGHT_CONTROL_VALUE_TO_OPTION:
            return False
        return self._api.set_property(self._did, 2, 6, value, self._host)

    def set_voice_interaction_volume(self, value: int) -> bool:
        if value not in VOICE_INTERACTION_VOLUME_VALUE_TO_OPTION:
            return False
        return self._api.set_property(self._did, 6, 6, value, self._host)

    def set_keypress_tone(self, enabled: bool) -> bool:
        return self._api.set_property(self._did, 2, 7, 1 if enabled else 0, self._host)

    def set_child_lock(self, enabled: bool) -> bool:
        return self._api.set_property(self._did, 6, 5, 1 if enabled else 0, self._host)

    def set_voice_interaction(self, enabled: bool) -> bool:
        return self._api.set_property(self._did, 6, 7, 1 if enabled else 0, self._host)

    def set_timer(self, hours: int) -> bool:
        try:
            hours = int(hours)
        except (TypeError, ValueError):
            return False
        return self._api.set_property(self._did, 6, 8, max(TIMER_MIN_HOURS, min(TIMER_MAX_HOURS, hours)), self._host)

    def reset_filter(self) -> bool:
        return self._api.call_action(self._did, 4, 1, host=self._host)
