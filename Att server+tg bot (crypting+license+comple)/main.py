import os
import asyncio
import aiofiles
import aiofiles.os
from pathlib import Path
import json
import time
import uuid
import aiosqlite
import uvicorn
from fastapi import FastAPI, Request, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from cryptography.fernet import Fernet
from contextlib import asynccontextmanager

FERNET_KEY = b'2AzrIjh3M1A5IeESjNnfE-8tmKBDEIXXi50caCVPF8s='
cipher = Fernet(FERNET_KEY)

DATABASE = "licenses.db"

SECRET_HEADER = "X-Secret-Key"
SECRET_VALUE = "g8hooZf_rjTNcydfWZK5Z9APlAUvlrT4NGqkTaPVaMc="


async def check_secret_key(request: Request):
    if request.headers.get(SECRET_HEADER) != SECRET_VALUE:
        raise HTTPException(status_code=404, detail="Not Found")

def set_working_dir():
    try:
        target_dir = Path(__file__).parent
        target_dir.mkdir(exist_ok=True)
        os.chdir(target_dir)
        print(f"Рабочая директория изменена на: {os.getcwd()}")
    except Exception as e:
        print(f"Ошибка смены директории: {e}")
        raise



class DeviceRequest(BaseModel):
    action: str
    key: str  # encrypted

class CreateKeyRequest(BaseModel):
    key: str | None = None
    max_devices: int = 1
    disabled: bool = False
    custom_name: str | None = ""

class UpdateKeyRequest(BaseModel):
    max_devices: int | None = None
    disabled: bool | None = None
    custom_name: str | None = None
    clear_devices: bool = False

class AttHitCreate(BaseModel):
    capture_string: str
    key: str

class AkamaiHeadersCreate(BaseModel):
    akamai_headers: list[dict]

# 🌱 Lifespan вместо on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    set_working_dir()
    app.state.db = await aiosqlite.connect(DATABASE)
    await app.state.db.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            key TEXT PRIMARY KEY,
            max_devices INTEGER,
            disabled BOOLEAN DEFAULT False,
            custom_name TEXT DEFAULT '',
            created_at INTEGER
        )
    """)
    await app.state.db.execute("""
        CREATE TABLE IF NOT EXISTS device_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            mac TEXT,
            hwid TEXT,
            blocked BOOLEAN DEFAULT False,
            bound_at INTEGER,
            FOREIGN KEY(key) REFERENCES user_keys(key)
        )
    """)
    await app.state.db.execute("""
        CREATE TABLE IF NOT EXISTS att_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capture_string TEXT,
            user_key TEXT,
            create_date INTEGER
        )
    """)
    await app.state.db.execute("""
        CREATE TABLE IF NOT EXISTS akamai_headers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            akamai_header TEXT,
            user_key TEXT,
            already_checked BOOL DEFAULT False,
            create_date INTEGER
        )
    """)
    await app.state.db.commit()
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)



# Exceptions handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"status": False, "error": exc.errors()})

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"status": False, "error": str(exc)})



# REGISTER DEVICE
@app.post("/register_device")
async def register_device(data: DeviceRequest, request: Request):
    if data.action != "check":
        return JSONResponse(status_code=400, content={"status": False, "error": "Invalid action"})

    try:
        decrypted = cipher.decrypt(data.key.encode()).decode()
        user_key, mac, hwid, client_timestamp = decrypted.split(":")
    except Exception:
        return JSONResponse(status_code=400, content={"status": False, "error": "Invalid key or format"})
    print(f'user_key={user_key}, mac={mac}, hwid={hwid}, client_timestamp={client_timestamp}')
    db = request.app.state.db

    cursor = await db.execute("SELECT max_devices, disabled FROM user_keys WHERE key = ?", (user_key,))
    row = await cursor.fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"status": False, "error": "License key not found"})

    max_devices, disabled = row
    if disabled:
        return JSONResponse(status_code=403, content={"status": False, "error": "License key is disabled"})

    cursor = await db.execute("""
        SELECT blocked FROM device_bindings 
        WHERE key = ? AND mac = ? AND hwid = ?
    """, (user_key, mac, hwid))
    row = await cursor.fetchone()

    if row:
        if row[0]:
            return JSONResponse(status_code=403, content={"status": False, "error": "Device is blocked"})
    else:
        cursor = await db.execute("SELECT COUNT(*) FROM device_bindings WHERE key = ?", (user_key,))
        bound_count = (await cursor.fetchone())[0]

        if bound_count >= max_devices:
            return JSONResponse(status_code=403, content={"status": False, "error": "Device limit exceeded"})

        await db.execute("""
            INSERT INTO device_bindings (key, mac, hwid, blocked, bound_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_key, mac, hwid, False, int(time.time())))
        await db.commit()

    server_timestamp = int(time.time())
    response_payload = f"{user_key}:{mac}:{hwid}:{client_timestamp}:{server_timestamp}"
    encrypted_response = cipher.encrypt(response_payload.encode()).decode()

    return JSONResponse(content={
        "status": True,
        "key": encrypted_response
    })


# MANAGE USER KEYS
@app.get("/key")
async def get_keys(key: str | None = Query(None), request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    if key:
        cursor = await db.execute("""
            SELECT key, max_devices, disabled, custom_name, created_at
            FROM user_keys
            WHERE key = ?
        """, (key,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"status": False, "error": "Key not found"})

        cursor = await db.execute("""
            SELECT mac, hwid, blocked, bound_at FROM device_bindings WHERE key = ?
        """, (key,))
        devices = [
            {"mac": r[0], "hwid": r[1], "blocked": r[2], "bound_at": r[3]}
            for r in await cursor.fetchall()
        ]

        return {
            "status": True,
            "key": {
                "key": row[0],
                "max_devices": row[1],
                "disabled": row[2],
                "custom_name": row[3],
                "created_at": row[4],
                "devices": devices
            }
        }

    else:
        cursor = await db.execute("""
            SELECT key, max_devices, disabled, custom_name, created_at FROM user_keys
        """)
        rows = await cursor.fetchall()

        keys = []
        for row in rows:
            cursor = await db.execute("""
                SELECT mac, hwid, blocked, bound_at FROM device_bindings WHERE key = ?
            """, (row[0],))
            key = {
                "key": row[0],
                "max_devices": row[1],
                "disabled": row[2],
                "custom_name": row[3],
                "created_at": row[4],
                "devices": [
                    {"mac": r[0], "hwid": r[1], "blocked": r[2], "bound_at": r[3]}
                    for r in await cursor.fetchall()
                ]
            }
            keys.append(key)

        return {
            "status": True,
            "keys": keys
        }

@app.post("/key")
async def create_key(data: CreateKeyRequest, request: Request, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    new_key = data.key or str(uuid.uuid4())
    created_at = int(time.time())

    try:
        await db.execute("""
            INSERT INTO user_keys (key, max_devices, disabled, custom_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (new_key, data.max_devices, data.disabled, data.custom_name or "", created_at))
        await db.commit()

        return {
            "status": True,
            "key": new_key,
            "max_devices": data.max_devices,
            "disabled": data.disabled,
            "created_at": created_at
        }

    except aiosqlite.IntegrityError:
        return JSONResponse(status_code=400, content={"status": False, "error": "Key already exists"})



@app.delete("/key")
async def delete_key(key: str = Query(...), request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    cursor = await db.execute("DELETE FROM user_keys WHERE key = ?", (key,))
    await db.commit()

    if cursor.rowcount == 0:
        return JSONResponse(status_code=404, content={"status": False, "error": "Key not found"})

    return {"status": True, "deleted_key": key}

@app.patch("/key")
async def update_key(key: str = Query(...), data: UpdateKeyRequest = None, request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    updates = []
    values = []

    if data.max_devices is not None:
        updates.append("max_devices = ?")
        values.append(data.max_devices)
    if data.disabled is not None:
        updates.append("disabled = ?")
        values.append(data.disabled)
    if data.custom_name is not None:
        updates.append("custom_name = ?")
        values.append(data.custom_name)

    if updates:
        values.append(key)
        await db.execute(f"""
            UPDATE user_keys SET {", ".join(updates)} WHERE key = ?
        """, values)

    if data.clear_devices:
        await db.execute("DELETE FROM device_bindings WHERE key = ?", (key,))

    await db.commit()
    return JSONResponse(content={"status": True})


# HITS
@app.get("/att_hits")
async def get_att_hits(request: Request, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    cursor = await db.execute("SELECT capture_string FROM att_hits ORDER BY create_date ASC")
    rows = await cursor.fetchall()
    return JSONResponse(content={"status": True, "results": [row[0] for row in rows]})

@app.post("/att_hits")
async def add_att_hit(payload: AttHitCreate, request: Request, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    await db.execute("""
        INSERT INTO att_hits (capture_string, user_key, create_date)
        VALUES (?, ?, ?)
    """, (payload.capture_string, payload.key, int(time.time())))
    await db.commit()
    return JSONResponse(content={"status": True})

@app.delete("/att_hits")
async def delete_att_hits(request: Request, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    await db.execute("DELETE FROM att_hits")
    await db.commit()
    return JSONResponse(content={"status": True})


# HEADERS
@app.get("/headers")
async def get_akamai_headers(key: str = Query(...), request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    cursor = await db.execute("""
        SELECT akamai_header FROM akamai_headers
        WHERE user_key = ? AND already_checked = False
        ORDER BY create_date ASC
    """, (key,))
    rows = await cursor.fetchall()
    await db.execute("UPDATE akamai_headers SET already_checked = False WHERE user_key = ?", (key,))
    await db.commit()
    return JSONResponse(content={"status": True, "headers": [row[0] for row in rows]})

@app.post("/headers")
async def add_akamai_headers(key: str = Query(...), payload: AkamaiHeadersCreate = None, request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    now = int(time.time())
    for header in payload.akamai_headers:
        await db.execute("""
            INSERT INTO akamai_headers (akamai_header, user_key, create_date)
            VALUES (?, ?, ?)
        """, (cipher.encrypt(json.dumps(header).encode()).decode(), key, now))
    await db.commit()
    return JSONResponse(content={"status": True})

@app.delete("/headers")
async def delete_akamai_headers(key: str = Query(...), request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    await db.execute("DELETE FROM akamai_headers WHERE user_key = ?", (key,))
    await db.commit()
    return JSONResponse(content={"status": True})

@app.patch("/headers")
async def delete_akamai_headers(key: str = Query(...), request: Request = None, _: None = Depends(check_secret_key)):
    db = request.app.state.db
    await db.execute("UPDATE akamai_headers SET already_checked = False WHERE user_key = ?", (key,))
    await db.commit()
    return JSONResponse(content={"status": True})



if __name__ == "__main__":
    uvicorn.run(app)