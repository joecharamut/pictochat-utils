import json
from datetime import datetime, timezone
import sys
import os
import gzip
import time

import websockets
import asyncio
import pyotp

def timestamp():
    return datetime.now(timezone.utc).timestamp()

class Logger:
    def __init__(self):
        if os.path.exists("log.json"):
            print("compressing old log...")
            mtime = os.path.getmtime("log.json")
            timestr = time.strftime("%Y%m%d-%H%M%S", time.localtime(mtime))

            if not os.path.exists("logs"):
                os.mkdir("logs")
            with open("log.json", "rb") as log:
                with gzip.open(f"logs/log-{timestr}.json.gz", "wb") as gz:
                    gz.write(log.read())

            print(f"log saved as 'logs/log-{timestr}.json.gz'")

        self.LOG_FILE = open("log.json", "w+")
        self.LOG_QUEUE = asyncio.Queue()

    def close(self):
        self.LOG_FILE.close()

    def _log(self, msg):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
        sys.stdout.flush()

    async def log(self, message):
        if isinstance(message, dict):
            message["timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self.LOG_QUEUE.put(message)
        else:
            message_dict = {
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "log_message": message
            }
            await self.LOG_QUEUE.put(message_dict)

    async def log_loop(self):
        while True:
            while not self.LOG_QUEUE.empty():
                message = await self.LOG_QUEUE.get()
                if "log_message" in message.keys():
                    self._log(message["log_message"])
                else:
                    self._log(json.dumps(message))
                self.LOG_FILE.write(json.dumps(message))
                self.LOG_FILE.write("\n")
                await asyncio.sleep(0.1)
            self.LOG_FILE.flush()
            await asyncio.sleep(0.5)


ADMIN_TOTP = pyotp.TOTP(open("admin.secret", "r").read().strip())
def check_totp(p):
    return ADMIN_TOTP.verify(p)

async def check_ban(ip):
    if not os.path.exists("banlist.txt"):
        with open("banlist.txt", "w") as f:
            f.write("{}")

    with open("banlist.txt", "r") as f:
        bans = json.loads(f.read())

    if ip in bans:
        expire = bans[ip]
        if timestamp() > expire:
            del bans[ip]
            with open("banlist.txt", "w") as f:
                f.write(json.dumps(bans))
            return False
        return True
    return False

async def set_ban(ip):
    if not os.path.exists("banlist.txt"):
        with open("banlist.txt", "w") as f:
            f.write("{}")

    with open("banlist.txt", "r") as f:
        bans = json.loads(f.read())

    bans[ip] = timestamp() + (24 * 60 * 60) # 1 day

    with open("banlist.txt", "w") as f:
        f.write(json.dumps(bans))

LOGGER = Logger()
USERS = set()
USERNAMES = {}
AUTH_USERS = {}

ROOM_A = set()
ROOM_B = set()
ROOM_C = set()
ROOM_D = set()

async def send_menu(websocket):
    await websocket.send(json.dumps({
        "type":"status",
        "roomA":len(ROOM_A),
        "roomB":len(ROOM_B),
        "roomC":len(ROOM_C),
        "roomD":len(ROOM_D),
    }))

async def check_username(websocket, username):
    valid = True
    if username.lower() == "invalid":
        valid = False
    for user, name in USERNAMES.items():
        if name == username:
            valid = False
    if valid:
        USERNAMES[websocket] = username
    await websocket.send(json.dumps({
        "type": "username",
        "valid": valid
    }))

async def join_room(websocket, room):
    success = True
    if room not in "ABCD":
        success = False
    else:
        if room == "A":
            if len(ROOM_A) == 16:
                success = False
            else:
                ROOM_A.add(websocket)
                await room_join("A", USERNAMES[websocket])
        elif room == "B":
            if len(ROOM_B) == 16:
                success = False
            else:
                ROOM_B.add(websocket)
                await room_join("B", USERNAMES[websocket])
        elif room == "C":
            if len(ROOM_C) == 16:
                success = False
            else:
                ROOM_C.add(websocket)
                await room_join("C", USERNAMES[websocket])
        elif room == "D":
            if len(ROOM_D) == 16:
                success = False
            else:
                ROOM_D.add(websocket)
                await room_join("D", USERNAMES[websocket])
    await websocket.send(json.dumps({
        "type": "join",
        "success": success
    }))

async def leave_room(websocket, room):
    if room in "ABCD":
        if room == "A":
            await room_leave("A", USERNAMES[websocket])
            ROOM_A.remove(websocket)
        elif room == "B":
            await room_leave("B", USERNAMES[websocket])
            ROOM_B.remove(websocket)
        elif room == "C":
            await room_leave("C", USERNAMES[websocket])
            ROOM_C.remove(websocket)
        elif room == "D":
            await room_leave("D", USERNAMES[websocket])
            ROOM_D.remove(websocket)

join_codes = {"A":0, "B":2, "C":4, "D":6}
async def room_join(room, username):
    await send_message(room, {
        "type": join_codes[room],
        "data": username
    }, None)

leave_codes = {"A":1, "B":3, "C":5, "D":7}
async def room_leave(room, username):
    await send_message(room, {
        "type": leave_codes[room],
        "data": username
    }, None)

async def send_message(room, message, author):
    try:
        _ = message["user"]
    except KeyError:
        message["user"] = "" if not author else USERNAMES[author]

    messageJson = json.dumps({
        "type": "message",
        "message": message
    })

    if room == "A":
        for user in ROOM_A:
            await user.send(messageJson)
    elif room == "B":
        for user in ROOM_B:
            await user.send(messageJson)
    elif room == "C":
        for user in ROOM_C:
            await user.send(messageJson)
    elif room == "D":
        for user in ROOM_D:
            await user.send(messageJson)
    else:
        await log(f"send_message: unknown room ({room.__repr__()})")

async def register(websocket):
    USERS.add(websocket)

async def unregister(websocket):
    username = ""
    for user, name in USERNAMES.items():
        if user == websocket:
            username = USERNAMES.pop(user)
            break

    if websocket in AUTH_USERS:
        AUTH_USERS.pop(websocket)

    if websocket in ROOM_A:
        ROOM_A.remove(websocket)
        await room_leave("A", username)
    if websocket in ROOM_B:
        ROOM_B.remove(websocket)
        await room_leave("B", username)
    if websocket in ROOM_C:
        ROOM_C.remove(websocket)
        await room_leave("C", username)
    if websocket in ROOM_D:
        ROOM_D.remove(websocket)
        await room_leave("D", username)

    if websocket in USERS:
        USERS.remove(websocket)

async def send_sys_message(websocket, message):
    await websocket.send(json.dumps({
        "type": "message",
        "message": {
            "type": 10,
            "user": "",
            "data": message
        }
    }))

async def admin_command(websocket, data):
    message = data["message"]["data"]
    if not message.startswith("%admin"):
        return False

    try:
        auth = AUTH_USERS[websocket]
    except KeyError:
        auth = False

    _, command, *args = message.split(" ")

    if not auth:
        if command == "auth":
            if check_totp(args[0]):
                AUTH_USERS[websocket] = True
                await send_sys_message(websocket, "Authenticated")
            return True
    else:
        if command == "deauth":
            AUTH_USERS[websocket] = False
            await send_sys_message(websocket, "Deauthenticated")
            return True
        elif command == "bcast":
            bmsg = " ".join(args)
            m_json = {"type": 8, "user": "[SYSTEM]", "data": bmsg}
            await send_message("A", m_json, None)
            await send_message("B", m_json, None)
            await send_message("C", m_json, None)
            await send_message("D", m_json, None)
            return True
        elif command == "kick":
            for sock, name in USERNAMES.items():
                if name == args[0]:
                    await unregister(sock)
                    await abort_connection(sock, 1000, "Kicked by an admin")
                    await send_sys_message(websocket, "Success")
                    break
            else:
                await send_sys_message(websocket, "User not found")
            return True
        elif command == "ban":
            for sock, name in USERNAMES.items():
                if name == args[0]:
                    await finish_him(sock)
                    await send_sys_message(websocket, "Success")
                    break
            else:
                await send_sys_message(websocket, "User not found")
            return True
    return False

async def preflight_ws_message(message):
    try:
        message.encode().decode('ascii')
    except UnicodeDecodeError:
        return False

    try:
        m_json = json.loads(message)
    except ValueError:
        return False

    try:
        if len(m_json["action"]) > 32:
            return False
    except KeyError:
        return False

    return m_json

async def preflight_picto_message(message):
    if len(message["room"]) != 1:
        return False
    if len(message["message"]["data"]) > 532:
        return False
    ilen = len(message["message"]["image"])
    if ilen != 3068 and ilen != 0:
        return False
    if message["message"]["type"] > 16:
        return False
    return True

async def preflight_picto_join(message):
    if len(message["room"]) != 1:
        return False
    return True

async def preflight_picto_leave(message):
    if len(message["room"]) != 1:
        return False
    return True

async def preflight_picto_username(message):
    if len(message["username"]) > 10:
        return False
    return True

async def abort_connection(websocket, code=1008, reason="Policy violation"):
    await websocket.close(code, reason)
    await LOGGER.log({"action": "abort", "remote": websocket.remote_address, "reason": f"{code}: {reason}"})

async def finish_him(websocket):
    await unregister(websocket)
    await set_ban(websocket.remote_address[0])
    await abort_connection(websocket)

async def check_and_terminate(the_check, data, websocket):
    if not await the_check(data):
        await finish_him(websocket)
        return True
    return False

async def app(websocket, path):
    ipaddr = websocket.remote_address[0]
    if await check_ban(ipaddr):
        # smh
        await abort_connection(websocket, 1008, "Banned for 1 day")
        return

    await LOGGER.log({"action": "connect", "remote": websocket.remote_address})
    await register(websocket)
    try:
        async for message in websocket:
            data = await preflight_ws_message(message)
            if data is False:
                await finish_him(websocket)
                return

            data["remote"] = websocket.remote_address
            await LOGGER.log(data)

            action = data["action"]

            if action == "status":
                await send_menu(websocket)
            elif action == "username":
                if await check_and_terminate(preflight_picto_username, data, websocket): return
                await check_username(websocket, data["username"])
            elif action == "join":
                if await check_and_terminate(preflight_picto_join, data, websocket): return
                await join_room(websocket, data["room"])
            elif action == "leave":
                if await check_and_terminate(preflight_picto_leave, data, websocket): return
                await leave_room(websocket, data["room"])
            elif action == "message":
                if await check_and_terminate(preflight_picto_message, data, websocket): return
                if not await admin_command(websocket, data):
                    await send_message(data["room"], data["message"], websocket)
            else:
                await finish_him(websocket)
                return
    finally:
        await unregister(websocket)
    await LOGGER.log({"action": "disconnect", "remote": websocket.remote_address})

address = ("0.0.0.0", 8069)
start_server = websockets.serve(app, address[0], address[1])

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(LOGGER.log_loop())
    loop.run_until_complete(LOGGER.log(f"running server on {address[0]}:{address[1]}"))
    loop.run_until_complete(start_server)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        LOGGER.close()
        raise
