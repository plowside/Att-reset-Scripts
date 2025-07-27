import asyncio
import aiohttp
import json
import re
import os
from typing import Optional
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

API_TOKEN = "7965745832:AAHCM6nQoHJ4O84lpMgAlpyR6L6GOSkCWB0"
BACKEND_URL = "https://plowside.pythonanywhere.com"

SECRET_HEADER = "X-Secret-Key"
SECRET_VALUE = "g8hooZf_rjTNcydfWZK5Z9APlAUvlrT4NGqkTaPVaMc="

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class KeyStates(StatesGroup):
    waiting_for_key_name = State()
    waiting_for_max_devices = State()
    waiting_for_new_name = State()

def set_working_dir():
    try:
        target_dir = Path(__file__).parent
        target_dir.mkdir(exist_ok=True)
        os.chdir(target_dir)
        print(f"Рабочая директория изменена на: {os.getcwd()}")
    except Exception as e:
        print(f"Ошибка смены директории: {e}")
        raise
set_working_dir()

KEYS_PER_PAGE = 6
MAX_DEVICES_OPTIONS = [1, 2, 5, 10, 999]


class Form(StatesGroup):
    choosing_user = State()
    uploading_file = State()

# ====================== Main Menu ======================
@dp.message(CommandStart())
async def start(message: Message):
    await send_main_menu(message)

async def send_main_menu(target):
    total_keys, active_keys = await get_key_stats()
    hits_count = len(await get_hits_from_server())  # Получаем количество hits

    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Add Akamai Headers", callback_data="add_headers")
    builder.button(text=f"📤 Export Hits ({hits_count})", callback_data="get_hits")  # Добавляем количество hits
    builder.button(text=f"🔑 Keys ({active_keys}/{total_keys})", callback_data="manage_keys")
    builder.adjust(1)

    text = """<b>🏠 Main Menu</b>

📊 <b>Statistics:</b>
• Active keys: <code>{active_keys}</code>
• Total keys: <code>{total_keys}</code>
• Available hits: <code>{hits_count}</code>""".format(
        active_keys=active_keys,
        total_keys=total_keys,
        hits_count=hits_count
    )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await target.answer(text, reply_markup=builder.as_markup())


# ====================== Key Management ======================
@dp.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data == "manage_keys")
async def manage_keys(call: CallbackQuery):
    await show_keys_page(call, 0)

async def show_keys_page(call: CallbackQuery, page: int):
    keys = await get_all_keys()
    print(keys)
    total_pages = max(1, (len(keys) + KEYS_PER_PAGE - 1) // KEYS_PER_PAGE)

    builder = InlineKeyboardBuilder()
    builder.button(text="✨ CREATE NEW KEY", callback_data="add_new_key")
    builder.adjust(1)

    if keys:
        for key in keys[page*KEYS_PER_PAGE : (page+1)*KEYS_PER_PAGE]:
            status = "🟢" if not key['disabled'] else "🔴"
            name = key['custom_name'] or key['key'][:8] + "..."  # Показываем первые 8 символов если нет имени
            devices = f"{len(key.get('devices', []))}/{key['max_devices']}"

            builder.button(
                text=f"{status} {name} | Devices: {devices}",
                callback_data=f"key_detail_{key['key']}"
            )
            builder.adjust(1)
    else:
        builder.button(text="📭 NO KEYS AVAILABLE", callback_data="noop")
        builder.adjust(1)

    if keys:
        pagination = []
        if page > 0:
            pagination.append(InlineKeyboardButton(text="◀️", callback_data=f"keys_page_{page-1}"))
        pagination.append(InlineKeyboardButton(text=f"Page {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            pagination.append(InlineKeyboardButton(text="▶️", callback_data=f"keys_page_{page+1}"))

        builder.row(*pagination)

    builder.button(text="🔙 BACK TO MENU", callback_data="back_to_main")
    builder.adjust(1)

    await call.message.edit_text(
        "🔑 <b>KEY MANAGEMENT</b>\n\n"
        "Below are your active license keys:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("keys_page_"))
async def handle_keys_pagination(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await show_keys_page(call, page)

@dp.callback_query(F.data == "add_new_key")
async def add_new_key(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        """<b>✨ Create New Key</b>

Please send a custom name for this key (or click Skip):""",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Skip Naming", callback_data="skip_key_name")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="manage_keys")]
        ])
    )
    await state.set_state(KeyStates.waiting_for_key_name)

@dp.callback_query(F.data == "skip_key_name", KeyStates.waiting_for_key_name)
async def skip_key_name(call: CallbackQuery, state: FSMContext):
    await state.update_data(custom_name="")
    await ask_max_devices(call, state)

@dp.message(KeyStates.waiting_for_key_name)
async def process_key_name(message: Message, state: FSMContext):
    await state.update_data(custom_name=message.text)
    await ask_max_devices(message, state)

async def ask_max_devices(target, state: FSMContext):
    builder = InlineKeyboardBuilder()
    options = [
        ("👤 Personal (1)", 1),
        ("👥 Team (2)", 2),
        ("👪 Family (5)", 5),
        ("🏢 Enterprise (10)", 10),
        ("♾️ Unlimited", 9999)
    ]

    for text, num in options:
        builder.button(text=text, callback_data=f"max_devices_{num}")

    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="manage_keys"))

    text = """<b>🔢 Select Device Limit</b>

Choose how many devices can use this key:"""

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await target.answer(text, reply_markup=builder.as_markup())

    await state.set_state(KeyStates.waiting_for_max_devices)

@dp.callback_query(F.data.startswith("max_devices_"), KeyStates.waiting_for_max_devices)
async def process_max_devices(call: CallbackQuery, state: FSMContext):
    max_devices = int(call.data.split("_")[2])
    data = await state.get_data()

    key_data = {
        "max_devices": max_devices,
        "custom_name": data.get("custom_name", "")
    }

    success, key_info = await create_key(key_data)

    if success:
        key_text = (
            "🎉 <b>New Key Created</b>\n\n"
            f"🔑 <b>Key:</b> <code>{key_info['key']}</code>\n"
            f"👥 <b>Device Limit:</b> {key_info['max_devices']}\n"
        )
        if key_info.get('custom_name'):
            key_text += f"🏷️ <b>Name:</b> {key_info['custom_name']}\n"

        key_text += "\nYou can now distribute this key to your users."

        await call.message.edit_text(
            key_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔑 Manage Keys", callback_data="manage_keys")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
                ]
            )
        )
    else:
        await call.message.edit_text(
            "❌ <b>Key Creation Failed</b>\n\n"
            "Please try again or check your backend connection.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Try Again", callback_data="add_new_key")]
                ]
            )
        )

    await state.clear()

@dp.callback_query(F.data.startswith("key_detail_"))
async def show_key_detail(call: CallbackQuery):
    key_id = call.data.split("_")[2]
    key_info = await get_key_info(key_id)

    if not key_info:
        await call.answer("❌ Key not found", show_alert=True)
        return

    headers_count = await get_headers_count_for_key(key_id)
    created_at = datetime.fromtimestamp(key_info['created_at']).strftime('%d.%m.%Y %H:%M')
    status = "🟢 ACTIVE" if not key_info['disabled'] else "🔴 DISABLED"

    text = f"""<b>🔐 Key Details</b>

<b>ID:</b> <code>{key_info['key']}</code>
<b>Status:</b> {status}
<b>Created:</b> {created_at}
<b>Devices:</b> {len(key_info.get('devices', []))}/{key_info['max_devices']}
<b>Headers:</b> <code>{headers_count}</code>

<b>Custom Name:</b> {key_info['custom_name'] or "Not set"}"""

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Rename", callback_data=f"edit_name_{key_id}")
    builder.button(
        text="🚫 Disable" if not key_info['disabled'] else "✅ Enable",
        callback_data=f"toggle_key_{key_id}"
    )
    builder.button(text="🔄 Clear Devices", callback_data=f"clear_devices_{key_id}")
    builder.button(text="🧹 Clear Headers", callback_data=f"clear_headers_{key_id}")  # Новая кнопка
    builder.button(text="🗑 Delete Key", callback_data=f"delete_key_{key_id}")
    builder.adjust(2)
    builder.button(text="🔙 Back to Keys", callback_data="manage_keys")

    try:
        await call.message.edit_text(text, reply_markup=builder.as_markup())
    except:
        pass


# Key actions
@dp.callback_query(F.data.startswith("edit_name_"))
async def edit_key_name(call: CallbackQuery, state: FSMContext):
    key_id = call.data.split("_")[2]
    await state.update_data(key_id=key_id)
    await call.message.edit_text(
        "Enter new name for this key:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Cancel", callback_data=f"key_detail_{key_id}")]
            ]
        )
    )
    await state.set_state(KeyStates.waiting_for_new_name)

@dp.message(KeyStates.waiting_for_new_name)
async def process_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    key_id = data.get("key_id")

    if not key_id:
        await message.answer("Error: Key not found in state")
        await state.clear()
        return

    success = await update_key(key_id, {"custom_name": message.text})

    if success:
        text = "Key name updated successfully."
    else:
        text = "Failed to update key name."

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Back to key", callback_data=f"key_detail_{key_id}")]
            ]
        )
    )
    await state.clear()

@dp.callback_query(F.data.startswith("clear_devices_"))
async def clear_devices(call: CallbackQuery):
    key_id = call.data.split("_")[2]
    success = await update_key(key_id, {"clear_devices": True})

    if success:
        text = "All device activations have been cleared."
    else:
        text = "Failed to clear activations."

    await call.answer(text, show_alert=True)
    await show_key_detail(call)

@dp.callback_query(F.data.startswith("clear_headers_"))
async def clear_headers(call: CallbackQuery):
    key_id = call.data.split("_")[2]

    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.delete(
            f'{BACKEND_URL}/headers',
            params={'key': key_id}
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('status'):
                    await call.answer("✅ Headers cleared successfully", show_alert=True)
                else:
                    await call.answer("❌ Failed to clear headers", show_alert=True)
            else:
                await call.answer("⚠️ Server error during headers clearing", show_alert=True)

    await show_key_detail(call)

@dp.callback_query(F.data.startswith("toggle_key_"))
async def toggle_key(call: CallbackQuery):
    key_id = call.data.split("_")[2]
    key_info = await get_key_info(key_id)

    if not key_info:
        await call.answer("Key not found", show_alert=True)
        return

    success = await update_key(key_id, {"disabled": not key_info['disabled']})

    if success:
        text = f"Key has been {'disabled' if not key_info['disabled'] else 'enabled'}."
    else:
        text = "Failed to update key status."

    await call.answer(text, show_alert=True)
    await show_key_detail(call)

@dp.callback_query(F.data.startswith("delete_key_"))
async def delete_key(call: CallbackQuery):
    key_id = call.data.split("_")[2]
    success = await delete_key_backend(key_id)

    if success:
        text = "Key has been deleted."
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Back to keys", callback_data="manage_keys")]
                ]
            )
        )
    else:
        text = "Failed to delete key."
        await call.answer(text, show_alert=True)
        await show_key_detail(call)

# ====================== Akamai Headers ======================
@dp.callback_query(F.data == "add_headers")
async def add_headers(call: CallbackQuery, state: FSMContext):
    keys = await get_all_keys()

    if not keys:
        await call.message.edit_text(
            "🔑 <b>No Keys Available</b>\n\n"
            "You don't have any active keys yet. "
            "Please create a key first in the Keys Management section.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔑 Create Key", callback_data="add_new_key")],
                    [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
                ]
            )
        )
        return

    builder = InlineKeyboardBuilder()
    for key in keys:
        status = "🟢" if not key['disabled'] else "🔴"
        name = key['custom_name'] or key['key'][:8] + "..."
        headers_count = await get_headers_count_for_key(key['key'])
        builder.button(
            text=f"{status} {name} | Headers: {headers_count}",
            callback_data=f"user_{key['key']}"
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main"))

    await call.message.edit_text(
        "🔑 <b>Select License Key</b>\n\n"
        "Choose which key to associate with these headers:\n"
        "• 🟢 = Active key\n"
        "• 🔴 = Disabled key\n"
        "• Number shows existing headers count",
        reply_markup=builder.as_markup()
    )
    await state.set_state(Form.choosing_user)

@dp.callback_query(F.data.startswith("user_"))
async def selected_user(call: CallbackQuery, state: FSMContext):
    key_id = call.data.split("_")[1]
    key_info = await get_key_info(key_id)

    if not key_info:
        await call.answer("❌ Key no longer exists", show_alert=True)
        await state.clear()
        return

    await state.update_data(selected_user_key=key_id)

    await call.message.edit_text(
        "📤 <b>Upload Headers File</b>\n\n"
        "Please send a <b>curl.txt</b> file containing the headers data.\n\n"
        "<i>Note: The file should contain raw curl commands from network requests.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Change Key", callback_data="add_headers")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ]
        )
    )
    await state.set_state(Form.uploading_file)

# Handle file
@dp.message(Form.uploading_file, F.document)
async def handle_file(message: Message, state: FSMContext):
    data = await state.get_data()
    user_key = data.get("selected_user_key")
    key_info = await get_key_info(user_key)

    if not key_info:
        await message.answer(
            "❌ <b>Error</b>\n\n"
            "The selected key no longer exists. "
            "Please select another key.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔑 Select Key", callback_data="add_headers")]
                ]
            )
        )
        await state.clear()
        return

    try:
        file = await bot.download(message.document)
        content = file.read().decode("utf-8")
        akamai_headers = parse_akamai_headers(content)

        if not akamai_headers:
            await message.answer(
                "❌ <b>Invalid File Format</b>\n\n"
                "The file doesn't contain valid curl commands. "
                "Please check the file and try again.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Try Again", callback_data=f"user_{user_key}")]
                    ]
                )
            )
            return

        status, error_msg = await send_akamai_headers(user_key, akamai_headers)
        display_name = key_info['custom_name'] or user_key[:8] + "..."

        if status:
            await message.answer(
                f"✅ <b>Success!</b>\n\n"
                f"Added <code>{len(akamai_headers)}</code> headers to key:\n"
                f"<code>{display_name}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Add More", callback_data="add_headers")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
                    ]
                )
            )
        else:
            await message.answer(
                f"❌ <b>Upload Failed</b>\n\n"
                f"Error processing headers for key <code>{display_name}</code>:\n"
                f"<code>{error_msg[:100]}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Try Again", callback_data=f"user_{user_key}")]
                    ]
                )
            )

    except Exception as e:
        await message.answer(
            "⚠️ <b>Processing Error</b>\n\n"
            f"Failed to process file: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Try Again", callback_data="add_headers")]
                ]
            )
        )

    await state.clear()

# ====================== Get Hits ======================
@dp.callback_query(F.data == "get_hits")
async def get_hits(call: CallbackQuery):
    temp_msg = await call.message.answer("⏳ Processing your request...")

    try:
        await call.message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")
        await temp_msg.edit_text("Failed to delete message, continuing...")

    hits = await get_hits_from_server()

    try:
        await temp_msg.delete()
    except:
        pass

    if hits:
        content = "\n".join(hits)
        file = BufferedInputFile(content.encode(), filename="Att_Hits.txt")
        await call.message.answer_document(
            file,
            caption="✅ <b>Hits exported successfully!</b>\n\n"
                   f"• Total hits: <code>{len(hits)}</code>\n"
                   "• File attached above"
        )
        await delete_hits_from_server()
    else:
        await call.message.answer(
            "📭 <b>No Hits Available</b>\n\n"
            "The hits database is currently empty. "
            "Check back later or add new hits through the system."
        )

    await send_main_menu(call.message)

# ====================== Back Button ======================
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_main_menu(call)

# ====================== Backend API Functions ======================
async def get_key_stats() -> tuple[int, int]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/key') as response:
            if response.status == 200:
                data = await response.json()
                total_keys = len(data.get('keys', []))
                active_keys = sum(1 for key in data.get('keys', []) if not key.get('disabled', True))
                return total_keys, active_keys
    return 0, 0

async def get_all_keys() -> list[dict]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/key') as response:
            if response.status == 200:
                data = await response.json()
                return data.get('keys', [])
    return []

async def get_key_info(key: str) -> Optional[dict]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/key', params={'key': key}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('key')
    return None

async def create_key(key_data: dict) -> tuple[bool, dict]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.post(f'{BACKEND_URL}/key', json=key_data) as response:
            if response.status == 200:
                data = await response.json()
                return True, data
    return False, {}

async def update_key(key: str, update_data: dict) -> bool:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.patch(
            f'{BACKEND_URL}/key',
            params={'key': key},
            json=update_data
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('status', False)
    return False

async def clear_headers_for_key(key: str) -> bool:
    """Clear headers for specific key"""
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.delete(f'{BACKEND_URL}/headers', params={'key': key}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('status', False)
    return False

async def delete_key_backend(key: str) -> bool:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.delete(f'{BACKEND_URL}/key', params={'key': key}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('status', False)
    return False

async def send_akamai_headers(user_key: str, headers: list[dict]) -> tuple[bool, str]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.post(
            f'{BACKEND_URL}/headers',
            params={'key': user_key},
            json={'akamai_headers': headers}
        ) as response:
            response_data = await response.json()
            return response_data.get('status', False), response_data.get('error', '')

async def get_hits_from_server() -> list[str]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/att_hits') as response:
            response_data = await response.json()
            return response_data.get('results', [])

async def delete_hits_from_server() -> bool:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.delete(f'{BACKEND_URL}/att_hits') as response:
            response_data = await response.json()
            return response_data.get('status', False)

async def get_headers_count_for_key(key: str) -> int:
    """Get count of headers for specific key"""
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/headers', params={'key': key}) as response:
            if response.status == 200:
                data = await response.json()
                return len(data.get('headers', []))
    return 0

def parse_akamai_headers(text: str) -> list[dict]:
    curls = text.split("curl 'https://identity.att.com")
    parsed_headers = []
    for curl in curls:
        pattern = r"-H (?:'|\$')x-iozyazcd-([a-z0-9]+): ([^']+)'"
        matches = re.findall(pattern, curl, re.IGNORECASE)
        if len(matches) > 2:
            user_agent = re.findall(r"-H (?:'|\$')user-agent: ([^']+)'", curl, re.IGNORECASE)[0]
            sec_ch_ua_raw = re.findall(r"-H (?:'|\$')sec-ch-ua: ([^']+)'", curl, re.IGNORECASE)[0]
            sec_ch_ua_platform_raw = re.findall(r"-H (?:'|\$')sec-ch-ua-platform: ([^']+)'", curl, re.IGNORECASE)[0]
            try: att_convid = re.findall(r"-H (?:'|\$')x-att-conversationid: ([^']+)'", curl, re.IGNORECASE)[0]
            except:
                att_convid = 'HALOILM~unauthenticated~41c6baba-b35d-46d9-bfba-fd798d7cbf01'

            sec_ch_ua = sec_ch_ua_raw.replace('\\"', '"')
            sec_ch_ua_platform = sec_ch_ua_platform_raw.replace('\\"', '"')

            headers = {key.lower(): value for key, value in matches}
            parsed_headers.append({
                "headers": json.dumps(headers),
                "user_agent": user_agent,
                "sec_ch_ua": sec_ch_ua,
                "sec_ch_ua_platform": sec_ch_ua_platform,
                "att_convid": att_convid
            })
    return parsed_headers

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))