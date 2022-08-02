import asyncio
import os
import pathlib
import re
import shutil
from typing import Dict, List
import downloader, telethon
from telethon.tl.types import PeerUser
from telethon.tl.custom.message import Message
from enum import Enum, auto
import subprocess
import random
import platform
import logging


class UserState(Enum):
    NONE = 1
    RESPONSE_MUSIC_OR_VIDEO = 2


class User:
    state: UserState
    peer: PeerUser
    lastMessage: str
    link: str  # Youtube link to download
    toDelete: List[Message] = []
    lock: asyncio.Lock

    def __init__(self, peer):
        self.peer = peer
        self.state = UserState.NONE
        self.lock = asyncio.Lock()

    def sendMessage(self, *args, **kwargs):
        return client.send_message(self.peer, *args, **kwargs)

    def deleteMessages(self):
        for message in self.toDelete:
            asyncio.create_task(message.delete())
        print(self.toDelete)
        self.toDelete.clear()


API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

client = telethon.TelegramClient(session='myself', api_id=API_ID, api_hash=API_HASH)
users: Dict[int, User] = {}

commands = {
    "ping": ["ping"],
    "uptime": ["uptime"],
    "reboot": ["reboot"]
}


def getIp():
    import urllib.request
    return urllib.request.urlopen("https://checkip.amazonaws.com").read().decode("utf-8")


def removeColors(s):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', s)


async def sendFile(user: User, type):
    directory = random.randint(1, 1_000_000_000)
    if type == 'music':
        downloader.try_download_music(user.link, download=True, subdirectory=f'{directory}/')
    else:
        downloader.try_download_video(user.link, subdirectory=f'{directory}/')
    user.link = ""
    await user.sendMessage(file=next(pathlib.Path(f"./downloaded/{directory}").iterdir()))
    shutil.rmtree(pathlib.Path(f"./downloaded/{directory}"))


async def handleReboot(user: User):
    await user.sendMessage("Going to reboot in one minute")
    await asyncio.sleep(60)
    subprocess.run(commands["reboot"])


async def handleBeginDialog(user: User):
    if user.lastMessage.lower() == "alive":
        await handleAlive(user)
    elif user.lastMessage.lower().startswith('ping'):
        await handlePing(user)
    elif user.lastMessage.lower() == "reboot":
        await handleReboot(user)
    else:
        await handleYoutubeDownload(user)


async def handleAlive(user: User):
    uptime = removeColors(subprocess.check_output(commands["uptime"], text=True).strip())
    await user.sendMessage("I am **indeed** alive!\n"
                           f"```{uptime}```\n"
                           f"My IP is {getIp()}")


async def handlePing(user: User):
    target = user.lastMessage.split()[1]
    result = removeColors(subprocess.check_output([*commands["ping"], f"{target}"], text=True).strip())
    await user.sendMessage(result)


async def handleYoutubeDownload(user: User):
    if not downloader.isVideo(user.lastMessage): return
    user.toDelete.append(await user.sendMessage("Вы хотите скачать это как?\n"
                                                "> 1) Музыку\n"
                                                "2) Видео\n"
                                                "3) Не скачивать"))
    # Useless message
    user.state = UserState.RESPONSE_MUSIC_OR_VIDEO
    user.link = user.lastMessage
    await asyncio.sleep(30)
    if user.state == UserState.RESPONSE_MUSIC_OR_VIDEO:
        # User did not do anything
        await sendFile(user, type='music')
        user.deleteMessages()
        user.state = UserState.NONE


async def handleDecisionMusicOrVideo(user: User, event):
    user.toDelete.append(event.message)
    # Answer is digit 1-3 - useless
    if user.lastMessage == '1':
        await sendFile(user, type='music')
    elif user.lastMessage == '2':
        await sendFile(user, type='video')
    elif user.lastMessage != '3':
        user.toDelete.append(await user.sendMessage("Не понял, попробуй ещё."))
        # Useless message
        return
    user.deleteMessages()
    user.state = UserState.NONE
    # В конце всей цепочки подчищаем юзлесс сообщения


@client.on(telethon.events.NewMessage('me'))
async def mainHandler(event: telethon.events.newmessage.NewMessage.Event):
    peer = event.message.peer_id
    id = peer.user_id

    if id not in users:
        users[id] = User(peer)
    user = users[id]

    async with user.lock:
        user.lastMessage = event.message.message
        if user.state == UserState.NONE:
            await handleBeginDialog(user)
        elif user.state == UserState.RESPONSE_MUSIC_OR_VIDEO:
            await handleDecisionMusicOrVideo(user, event)


async def main():
    print("done")


with client:
    client.loop.set_debug(True)
    client.loop.run_until_complete(main())
    client.loop.run_forever()

# todo: read my own logs
# todo check logs for filesystem errors
