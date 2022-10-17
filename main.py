import pathlib
import asyncio
import datetime
import io
import os
import random
import re
import shutil
import subprocess
from enum import Enum
from typing import Dict, List

from telethon.tl.custom.message import Message
from telethon.tl.types import PeerUser

import downloader
import telethon

backgroundTasks = set()


def createBackgroundTask(coro):
    task = asyncio.create_task(coro)
    backgroundTasks.add(task)
    task.add_done_callback(backgroundTasks.discard)


class UserState(Enum):
    NONE = 1
    RESPONSE_MUSIC_OR_VIDEO = 2


class User:
    state: UserState
    peer: PeerUser
    lastMessage: str
    link: str  # YouTube link to download
    toDelete: List[Message] = []
    lock: asyncio.Lock
    messageCounter = 0

    def __init__(self, peer):
        self.peer = peer
        self.state = UserState.NONE
        self.lock = asyncio.Lock()

    def sendMessage(self, *args, **kwargs):
        return client.send_message(self.peer, *args, **kwargs)

    async def deleteMessages(self):
        await asyncio.gather(*(message.delete() for message in self.toDelete))
        print(self.toDelete)
        self.toDelete.clear()

    async def resetDialog(self):
        self.state = UserState.NONE
        await self.deleteMessages()


API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

client = telethon.TelegramClient(session='myself', api_id=API_ID, api_hash=API_HASH)
users: Dict[int, User] = {}

commands = {
    "ping": ["ping", "-c", "4"],
    "uptime": ["uptime"],
    "reboot": ["reboot"],
    "logs": ["journalctl", "-u", "piBot.service", "-b"]
}


def getIp():
    import urllib.request
    return urllib.request.urlopen("https://checkip.amazonaws.com").read().decode("utf-8")


def removeColors(s):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', s)


async def sendFile(user: User, kind):
    directory = random.randint(1, 1_000_000_000)
    if kind == 'music':
        downloader.try_download_music(user.link, download=True, subdirectory=f'{directory}/')
    else:
        downloader.try_download_video(user.link, subdirectory=f'{directory}/')
    user.link = ""
    file = next(pathlib.Path(f"./downloaded/{directory}").iterdir())
    file = file.rename(f"./downloaded/{directory}/{file.name.removeprefix('NA - ')}")
    await user.sendMessage(file=file)
    shutil.rmtree(pathlib.Path(f"./downloaded/{directory}"))


async def handleReboot(user: User):
    await user.sendMessage("Going to reboot in one minute")
    await asyncio.sleep(60)
    subprocess.run(commands["reboot"])


async def handleSendLogs(user: User):
    logs = subprocess.check_output(commands["logs"])
    asFile = io.BytesIO(logs)
    asFile.name = 'logs.txt'
    await user.sendMessage(file=asFile)


async def handleBeginDialog(user: User):
    message = user.lastMessage.lower()
    if message == "alive":
        await handleAlive(user)
    elif message.startswith('ping'):
        await handlePing(user)
    elif message.startswith("reboot"):
        await handleReboot(user)
    elif message.startswith("log"):
        await handleSendLogs(user)
    else:
        await handleYoutubeDownload(user)


async def handleAlive(user: User):
    uptime = removeColors(subprocess.check_output(commands["uptime"], text=True).strip())
    await user.sendMessage("I am **indeed** alive!\n"
                           f"```{uptime}```\n"
                           f"My IP is {getIp()}")


async def handlePing(user: User):
    target = user.lastMessage.split()[1]
    result = removeColors(subprocess.check_output([*commands["ping"], target], text=True).strip())
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

    async def responseTimeout(currentMessageCounter: int):
        await asyncio.sleep(30)
        if user.messageCounter == currentMessageCounter:
            # User did not do anything
            await sendFile(user, kind='music')
            await user.resetDialog()

    createBackgroundTask(responseTimeout(user.messageCounter))


async def handleDecisionMusicOrVideo(user: User, event):
    user.toDelete.append(event.message)
    # Answer is digit 1-3 - useless
    if user.lastMessage == '1':
        await sendFile(user, kind='music')
    elif user.lastMessage == '2':
        await sendFile(user, kind='video')
    elif user.lastMessage != '3':
        user.toDelete.append(await user.sendMessage("Не понял, попробуй ещё."))
        # Useless message
        return
    await user.resetDialog()


@client.on(telethon.events.NewMessage('me'))
async def mainHandler(event: telethon.events.newmessage.NewMessage.Event):
    peer = event.message.peer_id
    userId = peer.user_id

    if userId not in users:
        users[userId] = User(peer)
    user = users[userId]

    async with user.lock:
        user.messageCounter += 1
        user.lastMessage = event.message.message
        if user.state == UserState.NONE:
            await handleBeginDialog(user)
        elif user.state == UserState.RESPONSE_MUSIC_OR_VIDEO:
            await handleDecisionMusicOrVideo(user, event)


@client.on(telethon.events.NewMessage(from_users=["me", 1054391041, 844541477, 550712077]))
async def allHandler(event: telethon.events.newmessage.NewMessage.Event):
    if event.message.text == '@all':
        msg = ''
        participants = await client.get_participants(await event.get_input_chat(), limit=20)
        if participants.total <= 20:
            for part in participants:
                msg += f"[{part.first_name}](tg://user?id={part.id}) "
            await client.send_message(entity=event.message.to_id, message=msg)


async def main():
    if os.name != 'nt':
        currentTime = datetime.datetime.now()
        timeAlive = 0
        with open('/proc/uptime', 'r') as f:
            timeAlive = float(f.read().split()[0])
        bootTime = currentTime - datetime.timedelta(seconds=timeAlive + 60)
        with open('/var/log/syslog') as f:
            interestingEntries = list(
                filter(lambda entry: "verbatim" in entry.lower() or "mitabrev" in entry.lower(), f.read().split('\n'))
            )
            reallyInterestingEntries = []
            for entry in interestingEntries:
                timestamp = ' '.join(entry[:15].split())
                # Aug 2 17:25:01
                timestamp = datetime.datetime.strptime(timestamp, "%b %d %H:%M:%S").replace(
                    year=datetime.date.today().year
                )
                if timestamp >= bootTime and "fsck" in entry:
                    reallyInterestingEntries.append(entry)
            await client.send_message('me', "Disk logs:\n" + '\n'.join(reallyInterestingEntries))
    print("done")


with client:
    client.loop.run_until_complete(main())
    client.loop.run_forever()
