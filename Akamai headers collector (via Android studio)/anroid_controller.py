import os
import time
import xml.etree.ElementTree as ET
import subprocess
from typing import Optional, Dict, List, Tuple

# Конфигурация путей
sdk_path = r"C:\Users\LUCKYBANANA5894\AppData\Local\Android\Sdk"
adb_path = os.path.join(sdk_path, "platform-tools", "adb.exe")

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


    def find_element(self, fresh=True, **kwargs) -> Optional[ET.Element]:
        """Находит элемент по атрибутам"""
        root = self.get_ui_dump(fresh)
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
        for _ in range(5):
            forgot_password_button = controller.find_element(
                text="Forgot password?"
            )
            if forgot_password_button is not None:
                break
            time.sleep(2)

        controller.tap_element(forgot_password_button)
        time.sleep(2)
        status = True
    return status

def forgot_password_step(controller: AndroidController, step: str = ''):
    if not step or step == 'user_id_field':
        print("[*] Waiting for User ID field...")
        user_id_field = None
        for _ in range(10):
            user_id_field = controller.find_element(
                resource_id="userId"
            )
            if user_id_field is not None:
                break
            time.sleep(2)

        if user_id_field is None:
            raise Exception("User ID field not found")

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
            raise Exception("Continue button not found")

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



def main():
    device_id = "emulator-5554"

    try:
        # Проверяем подключение устройства
        print("[*] Checking device connection...")
        controller = AndroidController(device_id)
        success, output = controller.run_adb_command("get-state")
        if not success or "device" not in output:
            raise Exception(f"Device {device_id} not connected")

        print(f"[+] Connected to device: {device_id}")

        # Получение xml дампа
        controller = AndroidController(device_id)
        dump = controller.get_ui_dump(True)
        time.sleep(5)

        # Запускаем сценарий
        # setup_magisk_flow(device_id)
    except Exception as e:
        print(f"[-] Error: {str(e)}")
    finally:
        print("[*] Cleaning up...")
        if os.path.exists("temp_window.xml"):
            os.remove("temp_window.xml")

if __name__ == "__main__":
    main()
