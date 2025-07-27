import base64
import subprocess, warnings, platform, time, uuid, sys

need_exit = 'false'
warnings.simplefilter('ignore', RuntimeWarning)
try:
	from cryptography.fernet import Fernet
	import requests
except ImportError:
	subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography requests httpx"])
	from cryptography.fernet import Fernet
	import requests


WEBSITE_URL = requests.get('https://raw.githubusercontent.com/plowside/plowside/refs/heads/main/assets/lc.json').json()['att']

SECRET_HEADER = "X-Secret-Key"
SECRET_VALUE = "g8hooZf_rjTNcydfWZK5Z9APlAUvlrT4NGqkTaPVaMc="

cipher = Fernet(base64.b64decode('MkF6cklqaDNNMUE1SWVFU2pObmZFLTh0bUtCREVJWFhpNTBjYUNWUEY4cz0='))

def get_machine_id():
	try:
		if platform.system() == 'Linux':
			return subprocess.check_output(['cat', '/sys/class/dmi/id/product_uuid']).decode().strip()
		elif platform.system() == 'Windows':
			try: return subprocess.check_output('wmic csproduct get uuid').decode().split('\n')[1].strip()
			except: return subprocess.check_output('powershell -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"').decode().strip()
	except:
		return "unknown"

this_key = "HERE_USER_KEY"
this_mac = str(uuid.getnode())
this_hwid = get_machine_id()
this_ts = int(time.time())

hwid = f"{this_key}:{this_mac}:{this_hwid}:{this_ts}"
encrypted = cipher.encrypt(hwid.encode()).decode()
req = requests.post(f'{WEBSITE_URL}/register_device', json={'action': 'check', 'key': encrypted})
resp = req.json()

if not resp.get('status', False):
	need_exit = 'true'
	sys.exit()
	exit()
try:
	decrypted_text = cipher.decrypt(resp['key'].encode()).decode()
	resp_key, resp_hwid, resp_mac, resp_ts, resp_server_ts = decrypted_text.split(':')
	if this_key != resp_key or this_mac != resp_hwid or this_hwid != resp_mac or this_ts != int(resp_ts) or (int(resp_server_ts) - this_ts) > 600 or (int(resp_server_ts) - int(resp_ts)) > 600 :
		need_exit = 'true'
		sys.exit()
		exit()
except:
	need_exit = 'true'
	sys.exit()
	exit()

if need_exit == 'true':
	while True:
		while True:
			while True:
				while True:
					while True:
						sys.exit()
						exit()




