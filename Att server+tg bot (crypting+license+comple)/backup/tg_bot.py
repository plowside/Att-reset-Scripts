import asyncio, aiohttp
import json
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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

USER_LIST = [
    {"name": "That kid", "user_key": "365cbd1d-b679-46e8-8f5a-3dc2411caf5b"}
]

class Form(StatesGroup):
    choosing_user = State()
    uploading_file = State()

# Start
@dp.message(CommandStart())
async def start(message: Message):
    await send_main_menu(message)

async def send_main_menu(target):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Akamai headers", callback_data="add_headers")],
        [InlineKeyboardButton(text="Get all hits as .txt", callback_data="get_hits")],
    ])
    await target.message.edit_text("<b>Att bot</b>\n\nChoose an option:", reply_markup=keyboard) if isinstance(target, CallbackQuery) else await target.answer("Welcome! Choose an option:", reply_markup=keyboard)

# Add Headers
@dp.callback_query(F.data == "add_headers")
async def add_headers(call: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for user in USER_LIST:
        builder.button(
            text=user["name"],
            callback_data=f"user_{user['user_key']}"
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="↪ Back", callback_data="back_to_main"))
    await call.message.edit_text("Choose a user:", reply_markup=builder.as_markup())
    await state.set_state(Form.choosing_user)

@dp.callback_query(F.data.startswith("user_"))
async def selected_user(call: CallbackQuery, state: FSMContext):
    user_key = call.data.replace("user_", "")
    await state.update_data(selected_user_key=user_key)
    builder = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↪ Back", callback_data="add_headers")]
    ])
    await call.message.edit_text("Send <b>curls.txt</b> file.", reply_markup=builder)
    await state.set_state(Form.uploading_file)

# Handle file
@dp.message(Form.uploading_file, F.document)
async def handle_file(message: Message, state: FSMContext):
    file = await bot.download(message.document)
    content = file.read().decode("utf-8")

    data = await state.get_data()
    user_key = data.get("selected_user_key")

    akamai_headers = parse_akamai_headers(content)
    status, error_msg = await send_akamai_headers(user_key, akamai_headers)
    print(status, error_msg)

    username = next((u["name"] for u in USER_LIST if u["user_key"] == user_key), "Unknown")

    if not status:
        text = f"❌ Failed to upload headers for <b>{username}</b>.\nError: <code>{error_msg[:30]}</code>"
    else:
        text = f"✅ Successfully uploaded  <code>{len(akamai_headers)}</code>  akamai headers for <b>{username}</b>."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↪ Back", callback_data="add_headers")]
    ])
    print(text)
    await message.answer(text, reply_markup=keyboard)
    await state.clear()

# Get hits
@dp.callback_query(F.data == "get_hits")
async def get_hits(call: CallbackQuery):
    hits = await get_hits_from_server()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↪ Back", callback_data="back_to_main")]
    ])

    if hits:
        content = "\n".join(hits)
        file = BufferedInputFile(content.encode(), filename="Att_Hits.txt")
        msg = await call.message.edit_text("Sending hits...")
        await call.message.answer_document(file, caption=f"Hits count:  <code>{len(hits)}</code>")
        await call.message.answer("Choose an option:", reply_markup=keyboard)
        await msg.delete()
    else:
        await call.message.edit_text("No hits found.", reply_markup=keyboard)

# Back
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_main_menu(call)


def parse_akamai_headers(text: str) -> list[dict]:
    curls = text.split("curl 'https://identity.att.com")
    parsed_headers = []
    for curl in curls:
        pattern = r"-H 'x-iozyazcd-([a-z0-9]+): ([^']+)'"
        matches = re.findall(pattern, curl)
        if len(matches) > 2:
            user_agent = re.findall("-H 'user-agent: ([^']+)'", curl)[0]
            sec_ch_ua = re.findall("-H 'sec-ch-ua: ([^']+)'", curl)[0]
            sec_ch_ua_platform = re.findall("-H 'sec-ch-ua-platform: ([^']+)'", curl)[0]
            att_convid = re.findall("-H 'x-att-conversationid: ([^']+)'", curl)[0]
            headers = {x: xx for x, xx in matches}
            parsed_headers.append({
                "headers": json.dumps(headers),
                "user_agent": user_agent,
                "sec_ch_ua": sec_ch_ua,
                "sec_ch_ua_platform": sec_ch_ua_platform,
                "att_convid": att_convid
            })
    return parsed_headers

async def send_akamai_headers(user_key: str, headers: list[dict]) -> tuple[bool, str]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.post(f'{BACKEND_URL}/headers', params={'key': user_key}, json={'akamai_headers': headers}) as response:
            response = await response.json()
            print(response)
            return response.get('status', False), response.get('error', False)


async def get_hits_from_server() -> list[str]:
    async with aiohttp.ClientSession(headers={SECRET_HEADER: SECRET_VALUE}) as session:
        async with session.get(f'{BACKEND_URL}/att_hits') as response:
            response = await response.json()
            return response.get('results', [])

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
