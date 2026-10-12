"""Optional system segments. Standard library only; no agent usage or credentials."""
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from statusbar import atomic_json, execute


def percentage(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100


def linux_system(proc=Path('/proc'), sleep=time.sleep):
    def ticks():
        values = list(map(int, (proc / 'stat').read_text().splitlines()[0].split()[1:9]))
        if len(values) < 4 or any(value < 0 for value in values):
            raise ValueError('Invalid CPU counters')
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    total, idle = ticks()
    sleep(0.1)
    later, idle_later = ticks()
    delta = later - total
    cpu = 100 * (1 - (idle_later - idle) / delta) if delta > 0 else None
    memory = {}
    for line in (proc / 'meminfo').read_text().splitlines():
        name, _, value = line.partition(':')
        memory[name] = int(value.split()[0])
    size = memory['MemTotal']
    ram = 100 * (1 - memory['MemFree'] / size) if size > 0 else None
    return {'cpu': cpu, 'ram': ram}


def mac_system(run=execute):
    top = run(['top', '-l', '2', '-s', '1', '-n', '0'], None, timeout=3)
    size = run(['sysctl', '-n', 'hw.memsize'], None)
    if not top or top.returncode or not size or size.returncode:
        raise ValueError('System collection failed')
    text = top.stdout.decode(errors='replace')
    cpu = re.findall(r'CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys', text)
    used = re.findall(r'PhysMem:\s*([\d.]+)([KMGT]?) used', text)
    if not cpu or not used:
        raise ValueError('Invalid system sample')
    amount, unit = used[-1]
    physical = int(size.stdout)
    ram = float(amount) * 1024 ** (' KMGT'.index(unit) if unit else 0) / physical * 100
    return {'cpu': sum(map(float, cpu[-1])), 'ram': ram}


def battery(platform=sys.platform, run=execute, power=Path('/sys/class/power_supply')):
    if platform == 'darwin':
        result = run(['pmset', '-g', 'batt'], None)
        if not result or result.returncode:
            raise ValueError('Battery collection failed')
        match = re.search(rb'(\d+)%;', result.stdout)
        return {'level': int(match[1]) if match else None}
    if platform.startswith('linux'):
        values = []
        for device in sorted(power.glob('*')):
            if (device / 'type').read_text().strip() == 'Battery':
                if (device / 'present').exists() and (device / 'present').read_text().strip() == '0':
                    continue
                level = int((device / 'capacity').read_text())
                if percentage(level):
                    values.append(level)
        # Multiple batteries: average their reported percentages, not energy weights.
        return {'level': sum(values) / len(values) if values else None}
    return {'level': None}


def weather(latitude, longitude, fetch=urlopen):
    query = urlencode({'latitude': latitude, 'longitude': longitude,
                       'current': 'temperature_2m', 'temperature_unit': 'celsius'})
    with fetch('https://api.open-meteo.com/v1/forecast?' + query, timeout=2) as response:
        data = json.loads(response.read(65537))
    value = data['current']['temperature_2m']
    if type(value) not in (int, float) or not math.isfinite(value) or not -100 <= value <= 100:
        raise ValueError('Invalid temperature')
    return {'temperature': value}


class Dashboard:
    def __init__(self, state, settings, platform=sys.platform, clock=time.time,
                 system=None, get_battery=None, get_weather=None, now=datetime.now):
        self.state = Path(state)
        self.settings = settings
        self.clock = clock
        self.now = now
        self.system = system or (mac_system if platform == 'darwin' else linux_system)
        self.get_battery = get_battery or (lambda: battery(platform))
        self.get_weather = get_weather or (lambda: weather(settings.weather_latitude, settings.weather_longitude))

    def cached(self, key, ttl, collect, valid):
        directory = self.state / 'system'
        path = directory / (key + '.json')
        lock_path = path.with_suffix('.lock')
        try:
            if self.state.is_symlink() or directory.is_symlink() or path.is_symlink():
                raise ValueError('Unsafe state')
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return None
                now = self.clock()
                try:
                    stored = json.loads(path.read_text())
                    stamp = stored['observed_at']
                    data = stored['data']
                    age = now - stamp if type(stamp) in (int, float) and math.isfinite(stamp) else -1
                    interval = ttl if valid(data) else self.settings.failure_retry_seconds
                    if 0 <= age < interval:
                        return data if valid(data) else None
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                try:
                    data = collect()
                    if not valid(data):
                        data = None
                except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
                    data = None
                atomic_json(path, {'observed_at': now, 'data': data})
                return data
        except (OSError, ValueError):
            return None

    def collect(self):
        parts = []
        options = self.settings
        if options.show_cpu or options.show_ram:
            valid = lambda data: (isinstance(data, dict) and set(data) == {'cpu', 'ram'}
                                  and all(value is None or percentage(value) for value in data.values())
                                  and any(value is not None for value in data.values()))
            data = self.cached('usage', 10, self.system, valid)
            for enabled, field, title in ((options.show_cpu, 'cpu', 'CPU'), (options.show_ram, 'ram', 'RAM')):
                if enabled:
                    value = data.get(field) if data else None
                    if percentage(value):
                        parts.append(f'{title} {value:.0f}%')
                    elif options.show_errors:
                        parts.append(f'{title} ?')
        if options.show_battery:
            valid = lambda data: (isinstance(data, dict) and set(data) == {'level'}
                                  and (data['level'] is None or percentage(data['level'])))
            data = self.cached('battery', 30, self.get_battery, valid)
            if data and percentage(data['level']):
                parts.append(f"ϟ{data['level']:.0f}%")
            elif data is None and options.show_errors:
                parts.append('Battery ?')
        if options.show_weather:
            identity = json.dumps([options.weather_latitude, options.weather_longitude])
            key = 'weather-' + hashlib.sha256(identity.encode()).hexdigest()
            valid = lambda data: (isinstance(data, dict) and set(data) == {'temperature'}
                                  and type(data['temperature']) in (int, float)
                                  and math.isfinite(data['temperature']) and -100 <= data['temperature'] <= 100)
            data = self.cached(key, options.weather_refresh_seconds, self.get_weather, valid)
            if data:
                parts.append(f"{data['temperature']:.0f}°C")
            elif options.show_errors:
                parts.append('Weather ?')
        if options.show_datetime:
            # strftime directives such as %n can produce control characters.
            rendered = self.now().strftime(options.datetime_format)
            parts.append(''.join(char for char in rendered if char.isprintable())[:160])
        return ' · '.join(parts)
