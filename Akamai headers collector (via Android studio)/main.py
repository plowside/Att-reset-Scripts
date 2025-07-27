import msvcrt
import subprocess
import getpass
import os
import threading
import time
from contextlib import contextmanager
import frida
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Tuple

# Конфигурация путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
sdk_path = fr"C:\Users\{getpass.getuser()}\AppData\Local\Android\Sdk"
avdmanager_path = os.path.join(sdk_path, "cmdline-tools", "latest", "bin", "avdmanager.bat")
emulator_path = os.path.join(sdk_path, "emulator", "emulator.exe")
adb_path = os.path.join(sdk_path, "platform-tools", "adb.exe")

if not os.path.exists(ASSETS_DIR):
    os.makedirs(ASSETS_DIR)

FRIDA_SERVER_PATH = os.path.join(ASSETS_DIR, "frida-server-16.7.0-android-x86_64")
FRIDA_SCRIPT_PATH = os.path.join(ASSETS_DIR, "fridas.js")
MITM_CERT_PATH = os.path.join(ASSETS_DIR, "mitmproxy-ca-cert.cer")
APK_PATH = os.path.join(ASSETS_DIR, "myATT.apk")

def check_assets_files():
    """Проверяет наличие необходимых файлов в папке assets"""
    required_files = {
        "Frida server": FRIDA_SERVER_PATH,
        "Frida script": FRIDA_SCRIPT_PATH,
        "MITM cert": MITM_CERT_PATH,
        "APK file": APK_PATH
    }

    missing_files = []
    for name, path in required_files.items():
        if not os.path.exists(path):
            missing_files.append(name)

    if missing_files:
        raise FileNotFoundError(
            f"Отсутствуют необходимые файлы в папке assets: {', '.join(missing_files)}\n"
            f"Пожалуйста, поместите их в: {ASSETS_DIR}"
        )


running_emulators_count = 0

class AndroidController:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.last_dump = None

    def run_adb_command(self, command: str, args: list = None, timeout: int = 30) -> Tuple[bool, str]:
        """Выполняет ADB команду с таймаутом"""
        cmd = [adb_path, "-s", self.device_id] + command.split() + (args or [])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def get_ui_dump(self, fresh: bool = False, max_retries: int = 10) -> ET.Element:
        """Получает XML-дамп интерфейса с повышенной надежностью"""
        if not fresh and self.last_dump:
            return self.last_dump

        temp_file = "temp_window.xml"
        remote_path = "/sdcard/window_dump.xml"

        for attempt in range(max_retries):
            try:
                self.run_adb_command(f"shell rm -f {remote_path}")

                success, output = self.run_adb_command(f"shell uiautomator dump {remote_path}")
                if not success:
                    time.sleep(1)
                    continue

                success, size_output = self.run_adb_command(f"shell stat -c %s {remote_path}")
                if not success or size_output.strip() == "0":
                    time.sleep(1)
                    continue

                if os.path.exists(temp_file):
                    os.remove(temp_file)

                success, _ = self.run_adb_command(f"pull {remote_path} {temp_file}")
                if not success or not os.path.exists(temp_file):
                    continue

                with open(temp_file, 'r', encoding='utf-8') as f:
                    content = f.read(100)
                    if not content.strip().startswith('<?xml'):
                        continue

                try:
                    tree = ET.parse(temp_file)
                    root = tree.getroot()
                    if len(root) > 0:
                        self.last_dump = root
                        return root
                except ET.ParseError:
                    continue

            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(1)

        raise Exception(f"Failed to get valid UI dump after {max_retries} attempts")


    def find_element(self, **kwargs) -> Optional[ET.Element]:
        """Находит элемент по атрибутам"""
        root = self.get_ui_dump(True)
        for node in root.iter('node'):
            match = True
            for attr, value in kwargs.items():
                if node.get(attr.replace('_', '-')) != value:
                    match = False
                    break
            if match:
                return node
        return None


    def get_element_bounds(self, element: ET.Element) -> Dict[str, int]:
        """Извлекает координаты элемента"""
        bounds = element.get('bounds')
        if not bounds:
            return None

        coords = list(map(int, bounds.replace('][', ',').replace('[', '').replace(']', '').split(',')))
        return {
            'x1': coords[0], 'y1': coords[1],
            'x2': coords[2], 'y2': coords[3],
            'center_x': (coords[0] + coords[2]) // 2,
            'center_y': (coords[1] + coords[3]) // 2
        }

    def tap(self, x: int, y: int):
        """Кликает по координатам"""
        self.run_adb_command(f"shell input tap {x} {y}")

    def tap_element(self, element: ET.Element):
        """Кликает по центру элемента"""
        bounds = self.get_element_bounds(element)
        if not bounds:
            raise ValueError("Element has no bounds")
        self.tap(bounds['center_x'], bounds['center_y'])

    def input_text(self, element: ET.Element, text: str):
        """Вводит текст в поле"""
        self.tap_element(element)
        print('tapped')
        time.sleep(0.3)
        text = text.replace(' ', '%s').replace('&', '\\&')
        self.run_adb_command(f"shell input text '{text}'")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """Свайп от (x1,y1) до (x2,y2)"""
        self.run_adb_command(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")

    def back(self):
        """Нажимает кнопку назад"""
        self.run_adb_command("shell input keyevent KEYCODE_BACK")

def check_magisk_root_screen(controller: AndroidController) -> bool:
    """Проверяет, активен ли экран Magisk (пустой дамп)"""
    try:
        dump = controller.get_ui_dump(fresh=True)
        return is_empty_magisk_dump(dump)
    except Exception as e:
        print(f"Ошибка при проверке экрана Magisk: {e}")
        return False

def is_empty_magisk_dump(dump: ET.Element) -> bool:
    """
    Проверяет, является ли дамп пустым с единственным элементом Magisk.
    Возвращает True, если это нужный нам экран Magisk.
    """
    if len(dump) != 1:
        return False

    node = dump.find('node')
    if node is None:
        return False

    return (
        node.get('package') == 'com.topjohnwu.magisk' and
        node.get('bounds') == '[0,0][0,0]' and
        all(not node.get(attr) or node.get(attr).lower() == 'false'
            for attr in ['text', 'resource-id', 'class', 'content-desc',
                       'checkable', 'checked', 'clickable', 'enabled',
                       'focusable', 'focused', 'scrollable', 'long-clickable',
                       'password', 'selected'])
    )


def setup_magisk_flow(device_id: str):
    controller = AndroidController(device_id)

    print("[*] Waiting for OK button in magisk...")
    ok_button = None
    for _ in range(25):
        ok_button = controller.find_element(
            resource_id="com.topjohnwu.magisk:id/dialog_base_button_1",
            text="OK"
        )
        if ok_button is not None:
            break
        time.sleep(1)

    if ok_button is None:
        raise Exception("OK button in magisk not found")

    return True


def forgot_password_flow(device_id: str):
    controller = AndroidController(device_id)
    steps_to_skip = {
        "sing_in_step": False,
        "forgot_password_step": False,
        "cancel_step": False
    }
    shit_skipped = skip_shit_step(controller)
    print(f'[!] Shit skipped: {shit_skipped}')

    if shit_skipped == 2:
        result = sing_in_step(controller, 'sign_in_btn2')
        if result:
            steps_to_skip['sing_in_step'] = True
            time.sleep(3)
            result = sing_in_step(controller, 'forgot_password_button')
            if result:
                steps_to_skip['sing_in_step'] = True
                time.sleep(5)

    if not steps_to_skip['sing_in_step']:
        result = sing_in_step(controller)
        if not result:
            if skip_shit_step(controller):
                return forgot_password_flow(device_id)
            return False
        time.sleep(5)

    if not steps_to_skip['forgot_password_step']:
        result = forgot_password_step(controller)
        if not result:
            return False

    if not steps_to_skip['cancel_step']:
        result = cancel_step(controller)
        if result: # Чтобы получить ещё один заголовок
            sing_in_step(controller, 'forgot_password_button')
            time.sleep(5)
            forgot_password_step(controller)
    return True


def skip_shit_step(controller: AndroidController, step: str = ''):
    print(f'[*] Searching for shit to skip')
    shit_skipped = 0
    if not step or step == 'want_notify_shit':
        want_notify_shit = controller.find_element(
            text='Want notifications?'
        )
        if want_notify_shit is not None:
            shit_skipped = 1
            continue_step(controller)

    if not step or step == 'want_notify_shit':
        want_location_shit = controller.find_element(
            text='Want to share your location?'
        )
        if want_location_shit is not None:
            shit_skipped = 2
            continue_step(controller)

    return shit_skipped

def sing_in_step(controller: AndroidController, step: str = '', check: bool = False):
    status = False
    if not step or step == 'show_more_btn':
        print("[*] Taping More button...")
        show_more_btn = None
        for _ in range(5):
            show_more_btn = controller.find_element(
                resource_id="test:id/myatt_more_main_page_tabs_id"
            )
            if show_more_btn is not None:
                break
            time.sleep(2)

        controller.tap_element(show_more_btn)
        time.sleep(2)
        status = True

    if not step or step == 'sign_in_btn':
        print("[*] Taping Sign in button...")
        sign_in_btn = controller.find_element(
            resource_id="test:id/myatt_sign_in_button_more_tab_settings_id"
        )
        if sign_in_btn is None:
            if check: return False
            raise Exception("Sign in button not found")

        controller.tap_element(sign_in_btn)
        time.sleep(2)
        status = True

    if step == 'sign_in_btn2':
        print("[*] Taping Sign in button...")
        sign_in_btn = controller.find_element(
            resource_id="test:id/myatt_sign_in_btn_login_id"
        )
        if sign_in_btn is None:
            if check: return False
            raise Exception("Sign in button not found")

        controller.tap_element(sign_in_btn)
        time.sleep(2)
        status = True

    if not step or step == 'forgot_password_button':
        print("[*] Waiting for Forgot password button...")
        forgot_password_button = None
        for _ in range(11):
            forgot_password_button = controller.find_element(
                text="Forgot password?"
            )
            if forgot_password_button is not None:
                break
            time.sleep(1)

        controller.tap_element(forgot_password_button)
        time.sleep(2)
        status = True
    return status

def forgot_password_step(controller: AndroidController, step: str = ''):
    if not step or step == 'user_id_field':
        print("[*] Waiting for User ID field...")
        user_id_field = None
        for _ in range(20):
            user_id_field = controller.find_element(
                resource_id="userId"
            )
            if user_id_field is not None:
                break
            time.sleep(2)

        if user_id_field is None:
            return False
            # raise Exception("User ID field not found")

        print("[*] Entering User ID and Last name...")
        controller.input_text(user_id_field, "someemail@gmail.com")

    if not step or step == 'last_name_field':
        last_name_field = controller.find_element(
            resource_id="lastName"
        )
        if last_name_field is None:
            raise Exception("Last name field not found")

        controller.input_text(last_name_field, "email")
        time.sleep(.5)

    if not step or step == 'continue_btn':
        print("[*] Tapping Continue...")
        continue_btn = controller.find_element(
            resource_id="submit",
            text="Continue"
        )
        if continue_btn is None:
            return False
            # raise Exception("Continue button not found")

        controller.tap_element(continue_btn)
        time.sleep(2)
    return True

def cancel_step(controller: AndroidController, step: str = ''):
    if not step or step == 'cancel_button':
        print("[*] Tapping Cancel...")
        cancel_button = controller.find_element(
            text="Cancel"
        )
        if cancel_button is None:
            raise Exception("Cancel button not found")

        controller.tap_element(cancel_button)
        time.sleep(2)

    if not step or step == 'yes_cancel_button':
        print("[*] Tapping Yes, Cancel...")
        controller.tap(540, 1200)

    return True

def continue_step(controller: AndroidController):
    print("[*] Tapping Continue...")
    continue_button = controller.find_element(
        text="Continue"
    )
    if continue_button is None:
        raise Exception("Continue button not found")

    controller.tap_element(continue_button)
    time.sleep(2)

    return True


@contextmanager
def change_directory(destination):
    """Контекстный менеджер для временного изменения рабочей директории"""
    original_dir = os.getcwd()
    try:
        os.chdir(destination)
        yield
    finally:
        os.chdir(original_dir)

def clear_input_buffer():
    while msvcrt.kbhit():
        msvcrt.getch()

def get_existing_emulators():
    """Получаем список всех подключенных эмуляторов до запуска"""
    result = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
    return set(line.split('\t')[0] for line in result.stdout.split('\n') if '\tdevice' in line)

def wait_for_boot_complete(device_id):
    """Ожидаем полной загрузки эмулятора через проверку sys.boot_completed"""
    timeout = 120  # Максимальное время ожидания (секунды)
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            result = subprocess.run(
                [adb_path, "-s", device_id, "shell", "getprop", "sys.boot_completed"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip() == "1":
                print('[*] Device started in', round(time.time() - start_time, 4), 'seconds')
                return True
        except subprocess.CalledProcessError:
            pass

        time.sleep(5)

    raise TimeoutError(f"Эмулятор {device_id} не загрузился в течение {timeout} секунд")

def find_new_emulator(existing_ids):
    """Находим ID нового эмулятора, которого не было в исходном списке"""
    timeout = 120  # Максимальное время ожидания (секунды)
    start_time = time.time()

    while time.time() - start_time < timeout:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
        current_devices = set(line.split('\t')[0] for line in result.stdout.split('\n') if '\tdevice' in line)
        new_devices = current_devices - existing_ids

        if new_devices:
            return new_devices.pop()  # Возвращаем первый новый эмулятор

        time.sleep(3)

    raise TimeoutError("Не удалось обнаружить новый эмулятор в течение 2 минут")

def create_emulator():
    avd_name = f"AutoAVD-{str(int(time.time()))[4:]}"
    subprocess.run([
        avdmanager_path,
        "create", "avd",
        "-n", avd_name,
        "-k", "system-images;android-32;google_apis;x86_64",
        "-d", "pixel_6"
    ], shell=True)
    return avd_name

def launch_emulator(avd_name, existing_ids):
    global running_emulators_count

    port = 5580 + 2 * running_emulators_count
    running_emulators_count += 1

    print(f'[*] Launching emulator: {avd_name} on port {port}')
    emulator_process = subprocess.Popen([
        emulator_path,
        "-avd", avd_name,
        "-writable-system",
        "-no-snapshot",
        "-no-boot-anim",
        "-no-audio",
        "-port", str(port)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
    time.sleep(10)

    device_id = find_new_emulator(existing_ids)
    print(f'[+] Emulator detected with ID: {device_id}')

    # Ждем полной загрузки эмулятора
    print('[*] Waiting for emulator to boot...')
    wait_for_boot_complete(device_id)
    print('[+] Emulator boot completed!')

    return device_id, emulator_process

def install_upload_things(device_id):
    # Установка прокси
    print('[*] Setting up proxy...')
    subprocess.run([adb_path, "-s", device_id, "shell", "settings", "put", "global", "http_proxy", "192.168.0.50:8082"])

    # Загрузка файлов
    print('[*] Uploading files...')
    subprocess.run([adb_path, "-s", device_id, "push", FRIDA_SERVER_PATH, "/data/local/tmp/frida-server"])
    subprocess.run([adb_path, "-s", device_id, "push", MITM_CERT_PATH, "/data/local/tmp/cert-der.crt"])

    # Установка APK
    print('[*] Installing APK...')
    subprocess.run([adb_path, "-s", device_id, "install", APK_PATH])

    # Выдача разрешений
    package_name = "com.att.myWireless"
    subprocess.run(
        ["adb", "-s", device_id, "shell", "pm", "grant", package_name, "android.permission.ACCESS_FINE_LOCATION"],
        check=True
    )
    print(f"[+] Granted ACCESS_FINE_LOCATION to {package_name}")

    print(f'[+] All components installed on {device_id}')
    return True

def root_device(device_id, avd_name):
    print('[*] Rooting device...')
    rootavd_path = "rootAVD.bat"
    ramdisk_path = r"system-images\android-32\google_apis\x86_64\ramdisk.img"

    with change_directory("rootAVD"):
        magisk_result = subprocess.run(
            [rootavd_path, ramdisk_path],
            input="\n",
            text=True,
            stdout=subprocess.PIPE,
            shell=True
        )
        time.sleep(2)

    # После рутирования выполняем пост-настройку
    post_root_setup(device_id, avd_name)
    return True

def post_root_setup(device_id, avd_name):
    """Выполняет все действия после рутирования"""
    print('[*] Starting post-root setup...')
    print('[*] Restarting emulator...')
    subprocess.run([adb_path, "-s", device_id, "emu", "kill"])
    time.sleep(5)

    port = device_id.split('-')[1]
    subprocess.Popen([
        emulator_path,
        "-avd", avd_name,
        "-port", port,
        "-no-snapshot",
        "-no-audio"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)

    wait_for_boot_complete(device_id)
    time.sleep(5)

    return root_last_part(device_id, avd_name)

def run_frida_script(device_id: str):
    target_app = "com.att.myWireless"
    try:
        device = frida.get_device(device_id)
        print(f"[+] Frida Connected to device: {device}")
    except Exception as e:
        print(f"[-] Frida Error connecting to device: {e}")
        return False

    with open(FRIDA_SCRIPT_PATH, "r", encoding="utf-8") as f:
        js_code = f.read()

    try:
        pid = device.spawn([target_app])
        session = device.attach(pid)
        device.resume(pid)
        script = session.create_script(js_code)
        script.load()
    except KeyboardInterrupt:
        print("[!] Script interrupted.")
    except Exception as e:
        print(f"[-] Frida Error ({type(e)}): {e}")
        raise e
        return False
    return True

def root_last_part(device_id, avd_name, retry: int = 0):
    print(f'[*] {"First" if not retry else "Retrying"} Magisk setup...')

    for x in range(3):
        try:
            subprocess.run([adb_path, "-s", device_id, "shell", "monkey", "-p", "com.topjohnwu.magisk", "1"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = setup_magisk_flow(device_id)
            if result:
                break
        except Exception as e:
            print(f'[-] Error when configuring magisk ({type(e)}): {e}')

    subprocess.run([adb_path, "-s", device_id, "shell", "input", "tap", "900", "1300"])

    print('[*] Waiting for reboot...')
    time_to_check = 20
    start_ts = time.time()
    while True:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True)
        if device_id not in result.stdout:
            break
        if time.time() - start_ts > time_to_check:
            if retry > 3:
                return cleanup_and_delete(None, None, device_id, avd_name)
            return root_last_part(device_id, avd_name, retry + 1)
        time.sleep(.5)

    wait_for_boot_complete(device_id)
    time.sleep(5)

    install_upload_things(device_id)
    time.sleep(1)

    print('[*] Starting frida-server...')
    frida_process = subprocess.Popen([
        adb_path, "-s", device_id, "shell",
        "su", "-c", "'chmod 755 /data/local/tmp/frida-server && /data/local/tmp/frida-server &'"
    ], stdout=subprocess.DEVNULL)
    controller = AndroidController(device_id)
    time.sleep(1)
    retries = 0
    while True:
        if retries > 100:
            return cleanup_and_delete(None, frida_process, device_id, avd_name)
        result = check_magisk_root_screen(controller)
        if result:
            subprocess.run([adb_path, "-s", device_id, "shell", "input", "tap", "727", "1505"])
            time.sleep(1)
            if not check_magisk_root_screen(controller):
                break
            continue
        retries += 1
        time.sleep(.5)
    time.sleep(1)

    print('[*] Starting Frida script...')
    frida_thread = threading.Thread(target=run_frida_script, args=[device_id], daemon=True)
    frida_thread.start()
    time.sleep(10)

    print('[*] Starting forgot password flow...')
    try:
        result = forgot_password_flow(device_id)
        if not result:
            frida_thread.join(timeout=2)
            print('[*] Restarting Frida script...')
            frida_thread = threading.Thread(target=run_frida_script, args=[device_id], daemon=True)
            frida_thread.start()
            forgot_password_flow(device_id)
    except Exception as e:
        print(f'[-] Error in forgot_password_flow: {str(e)}')

    cleanup_and_delete(frida_thread, frida_process, device_id, avd_name)

def cleanup_and_delete(frida_thread, frida_process, device_id, avd_name):
    print('[*] Cleaning up...')
    if frida_thread: frida_thread.join(timeout=2)
    if frida_process: frida_process.terminate()
    subprocess.run([adb_path, "-s", device_id, "emu", "kill"])
    time.sleep(1)

    print('[*] Deleting AVD...')
    subprocess.run([avdmanager_path, "delete", "avd", "-n", avd_name])
    print('[+] Device terminated and deleted')

if __name__ == "__main__":
    check_assets_files()
    try:
        existing_emulators = get_existing_emulators()
        print(f'[+] Existing emulators: {existing_emulators or "None"}')

        created_avd_name = create_emulator()
        print(f'[+] Created AVD: {created_avd_name}')

        device_id, emulator_process = launch_emulator(created_avd_name, existing_emulators)

        root_device(device_id, created_avd_name)
    except Exception as e:
        print(f'[-] Error: {str(e)}')