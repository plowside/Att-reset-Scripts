from cryptography.fernet import Fernet
import platform, subprocess, uuid

cipher = Fernet(b'2AzrIjh3M1A5IeESjNnfE-8tmKBDEIXXi50caCVPF8s=')

def get_machine_id():
    try:
        if platform.system() == 'Linux':
            return subprocess.check_output(['cat', '/sys/class/dmi/id/product_uuid']).decode().strip()
        elif platform.system() == 'Windows':
            try: return subprocess.check_output('wmic csproduct get uuid').decode().split('\n')[1].strip()
            except: return subprocess.check_output('powershell -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"').decode().strip()
    except:
        return "unknown"

this_mac = str(uuid.getnode())
this_hwid = get_machine_id()
key = "20aef5c7-af7c-4eec-8642-820aff4a1999"

hwid = f"{key}:{this_mac}:{this_hwid}"
encrypted = cipher.encrypt(hwid.encode()).decode()
print(encrypted)