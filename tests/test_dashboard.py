import json
from pathlib import Path
import tempfile
import unittest

from dashboard import Dashboard, battery, linux_system, mac_system, weather
from statusbar import Settings


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [100.0]
        self.system_calls = []
        self.battery_calls = []
        self.weather_calls = []
        def system():
            self.system_calls.append(1)
            return {"cpu": 37.2, "ram": 63.7}
        def get_battery():
            self.battery_calls.append(1)
            return {"level": 93}
        def get_weather():
            self.weather_calls.append(1)
            return {"temperature": 12.4}
        self.dashboard = Dashboard(self.root / 'state', Settings(show_cpu=True, show_ram=True,
            show_battery=True, show_datetime=True, show_weather=True, weather_latitude=49.0,
            weather_longitude=8.0), clock=lambda:self.now[0], system=system,
            get_battery=get_battery, get_weather=get_weather,
            now=lambda: __import__('datetime').datetime(2026,10,12,11,29))

    def test_segments_format_and_cache(self):
        self.assertEqual(self.dashboard.collect(), 'CPU 37% · RAM 64% · ϟ93% · 12°C · 12.10.2026 11:29')
        self.assertEqual(self.dashboard.collect(), 'CPU 37% · RAM 64% · ϟ93% · 12°C · 12.10.2026 11:29')
        self.assertEqual((len(self.system_calls),len(self.battery_calls),len(self.weather_calls)),(1,1,1))

    def test_failed_metric_is_independent(self):
        dash=Dashboard(self.root/'failure',Settings(show_cpu=True,show_ram=True,show_battery=True,
            show_errors=True,show_datetime=False),system=lambda:(_ for _ in ()).throw(OSError()),
            get_battery=lambda:{'level':71})
        self.assertEqual(dash.collect(),'CPU ? · RAM ? · ϟ71%')

    def test_no_repository_context_still_shows_system_status(self):
        result=__import__('subprocess').run([__import__('sys').executable,'-B',str(Path(__file__).parents[1]/'cli.py'),
            'bar','--settings',str(self.root/'settings.toml'),'--state',str(self.root/'state')],
            capture_output=True,text=True,env={**__import__('os').environ,'HOME':str(self.root)})
        self.assertEqual((result.returncode,result.stderr),(0,''))
        self.assertTrue(result.stdout.startswith('CPU '),result.stdout)
        self.assertIn('RAM ',result.stdout)
        # An explicit setting file can disable or adjust each segment.
        (self.root/'settings.toml').write_text('show_cpu=true\n')
        result=__import__('subprocess').run([__import__('sys').executable,'-B',str(Path(__file__).parents[1]/'cli.py'),
            'bar','--settings',str(self.root/'settings.toml'),'--state',str(self.root/'state')],
            capture_output=True,text=True,env={**__import__('os').environ,'HOME':str(self.root)})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(result.stdout.startswith('CPU '),result.stdout)

    def test_weather_is_opt_in_and_coordinates_required(self):
        with self.assertRaisesRegex(ValueError,'requires latitude and longitude'):
            Settings.load(self._settings('show_weather=true\n'))
        self.assertEqual(Settings().show_weather,False)
        self.assertEqual(Settings(weather_latitude=90,weather_longitude=-180).weather_longitude,-180)

    def _settings(self,text):
        path=self.root/'settings.toml';path.write_text(text);return path

    def test_weather_bounds_request_and_validates_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,limit):
                self.assert_limit=limit
                return b'{"current":{"temperature_2m":12.5}}'
        calls=[]
        data=weather(49.4,8.7,lambda url,timeout:(calls.append((url,timeout)) or Response()))
        self.assertEqual(data,{'temperature':12.5})
        self.assertIn('latitude=49.4',calls[0][0])
        self.assertEqual(calls[0][1],2)

    def test_macos_system_parser(self):
        def run(argv, cwd, timeout=1):
            if argv[0] == 'sysctl':
                return __import__('subprocess').CompletedProcess(argv,0,b'1073741824',b'')
            return __import__('subprocess').CompletedProcess(argv,0,
                b'CPU usage: 10.0% user, 2.0% sys, 88.0% idle\\n'
                b'CPU usage: 20.0% user, 5.0% sys, 75.0% idle\\n'
                b'PhysMem: 512M used (100M wired), 512M unused.\\n',b'')
        self.assertEqual(mac_system(run),{'cpu':25.0,'ram':50.0})

    def test_battery_percent_parse_and_missing_battery(self):
        root=self.root/'power';root.mkdir()
        device=root/'BAT0';device.mkdir()
        (device/'type').write_text('Battery\n');(device/'capacity').write_text('82\n')
        self.assertEqual(battery(platform='linux',power=root),{'level':82})
        for file in device.iterdir():file.unlink()
        device.rmdir()
        self.assertEqual(battery(platform='linux',power=root),{'level':None})

    def test_macos_battery_parser(self):
        completed=__import__('subprocess').CompletedProcess([],0,
            b'Now drawing from \'Battery Power\'\\n -InternalBattery-0 (id=123) 93%; discharging; 1:42 remaining\\n',b'')
        self.assertEqual(battery(platform='darwin',run=lambda *args,**kwargs:completed),{'level':93})

    def test_linux_cpu_and_ram_parser(self):
        proc=self.root/'proc';proc.mkdir()
        stats=iter(['cpu 100 0 50 850 0 0 0 0','cpu 120 0 60 920 0 0 0 0'])
        (proc/'stat').write_text(next(stats))
        (proc/'meminfo').write_text('MemTotal: 1000 kB\nMemFree: 200 kB\n')
        values=[(proc/'stat').read_text(),next(stats)]
        # Update /proc/stat at the second sample.
        original=(proc/'stat').read_text()
        def sleep(_): (proc/'stat').write_text(values[1])
        measured=linux_system(proc,sleep)
        self.assertAlmostEqual(measured['cpu'],30.0)
        self.assertEqual(measured['ram'],80.0)
        (proc/'stat').write_text(original)

    def test_cache_permissions_and_location_isolation(self):
        self.dashboard.collect()
        cache=list((self.root/'state/system').glob('weather-*.json'))
        self.assertEqual(len(cache),1)
        self.assertEqual(cache[0].stat().st_mode&0o777,0o600)
        record=json.loads(cache[0].read_text())
        self.assertNotIn('latitude',json.dumps(record))
        other=Dashboard(self.root/'state',Settings(show_weather=True,weather_latitude=48.0,
            weather_longitude=8.0),get_weather=lambda:{'temperature':10})
        other.collect()
        self.assertEqual(len(list((self.root/'state/system').glob('weather-*.json'))),2)
