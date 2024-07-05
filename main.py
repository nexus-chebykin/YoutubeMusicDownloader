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
from typing import Dict, List, Optional, Literal

from telethon.tl.custom.message import Message
from telethon.tl.types import PeerUser
import grpc
import telegram_com_pb2
import telegram_com_pb2_grpc
import downloader
import telethon

backgroundTasks = set()


def createBackgroundTask(coro, loop=None):
    if loop is not None:
        task = asyncio.ensure_future(coro, loop=loop)
    else:
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
    progressMessage: Optional[Message]
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
        self.lastMessage = ""
        self.link = ""
        self.progressMessage = None
        await self.deleteMessages()


API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

client = telethon.TelegramClient(session='myself', api_id=API_ID, api_hash=API_HASH, connection_retries=None)
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


async def sendFile(user: User, kind: Literal['music', 'video']):
    directory = random.randint(1, 1_000_000_000)
    loop = asyncio.get_running_loop()
    download_progress = 0

    def download_progress_callback(d):
        nonlocal download_progress
        if user.progressMessage is None:
            return
        if 'total_bytes' in d:
            percent = d['downloaded_bytes'] / d['total_bytes']
        else:
            percent = 0
        if int(percent * 100) // 5 > download_progress // 5:
            download_progress = int(percent * 100)
            createBackgroundTask(user.progressMessage.edit(f"Downloading: {percent:.1%}\n"
                                                           f"Uploading: 0%"), loop=loop)

    await asyncio.to_thread(downloader.try_download, user.link, kind, download=True, subdirectory=f'{directory}/',
                            progress_callback=download_progress_callback)
    user.link = ""
    file = next(pathlib.Path(f"./downloaded/{directory}").iterdir())
    file = file.rename(f"./downloaded/{directory}/{file.name.removeprefix('NA - ')}")

    upload_progress = 0

    def upload_progress_callback(current, total):
        nonlocal upload_progress
        if user.progressMessage is None:
            return
        percent = current / total
        if int(percent * 100) // 5 > upload_progress // 5:
            upload_progress = int(percent * 100)
            createBackgroundTask(user.progressMessage.edit(f"Downloading: 100%\n"
                                                           f"Uploading {percent:.1%}"))

    uploaded_file = await client.upload_file(file, progress_callback=upload_progress_callback)
    await user.sendMessage(file=uploaded_file, force_document=True)
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
    if message == "help":
        await user.sendMessage("I can do the following:\n"
                               "1) `alive` - show uptime and IP\n"
                               "2) `ping <target>` - ping target\n"
                               "3) `reboot` - reboot the server\n"
                               "4) `log` - send logs\n"
                               "5) Send me a YouTube link to download it\n")
    elif message == "alive":
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
    user.progressMessage = await user.sendMessage("Вы хотите скачать это как?\n"
                                                  "> 1) Музыку\n"
                                                  "2) Видео\n"
                                                  "3) Не скачивать")
    user.toDelete.append(user.progressMessage)
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
    if user.lastMessage not in ['1', '2', '3']:
        user.toDelete.append(await user.sendMessage("Не понял, попробуй ещё."))
        # Useless message
        return
    await user.progressMessage.edit("Understandable")
    if user.lastMessage == '1':
        await sendFile(user, kind='music')
    elif user.lastMessage == '2':
        await sendFile(user, kind='video')
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
        try:
            if user.state == UserState.NONE:
                await handleBeginDialog(user)
            elif user.state == UserState.RESPONSE_MUSIC_OR_VIDEO:
                await handleDecisionMusicOrVideo(user, event)
        except Exception as e:
            await user.sendMessage(f"An error has occurred: {str(e)}")
            await user.resetDialog()


@client.on(telethon.events.NewMessage())
async def allHandler(event: telethon.events.newmessage.NewMessage.Event):
    good_chats = [1795578144, 1560916143]
    good_users = [242023883, 1054391041, 844541477, 550712077]
    chat_entity = await event.get_input_chat()
    user_entity = await event.get_input_sender()
    user_entity = await client.get_entity(user_entity)
    try:
        good = chat_entity.channel_id in good_chats or user_entity.id in good_users
    except AttributeError:
        return
    if not good:
        return
    if event.message.text != '@all':
        return

    msg = ''
    participants = await client.get_participants(await event.get_input_chat(), limit=30)
    if participants.total <= 30:
        for part in participants:
            msg += f"[{part.first_name}](tg://user?id={part.id}) "
        msg = await client.send_message(entity=event.message.to_id,
                                        message=msg)  # todo: make it work in private chats
        if event.message.from_id.user_id != 242023883:
            await client.send_message('me', f"You @all'ed: https://t.me/c/{msg.peer_id.channel_id}/{msg.id}",
                                      schedule=datetime.timedelta(minutes=1))


class TelegramRepeater(telegram_com_pb2_grpc.TelegramRepeaterServicer):
    async def SendMessage(self,
                          request: telegram_com_pb2.MessageRequest,
                          context: grpc.aio.ServicerContext):
        # check if request contains optional field edit_id:
        # if it does, edit message with that id; else, send a new message
        if request.HasField('edit_id'):
            message = await client.edit_message(4037730028, request.edit_id, request.message)
            id = getattr(message, 'id', -1)
            return telegram_com_pb2.MessageID(message_id=id)
        else:
            message = await client.send_message(4037730028, request.message)
            id = getattr(message, 'id', -1)
            return telegram_com_pb2.MessageID(message_id=id)


async def serve_repeater() -> None:
    server = grpc.aio.server()
    telegram_com_pb2_grpc.add_TelegramRepeaterServicer_to_server(TelegramRepeater(), server)
    listen_addr = "0.0.0.0:50051"
    server.add_insecure_port(listen_addr)
    await server.start()
    await server.wait_for_termination()


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
            # F Verbatim
            reallyInterestingEntries = []
            for entry in interestingEntries:
                timestamp = entry[:len('2024-07-03T00:22:14.686239+05:00')]
                timestamp = datetime.datetime.fromisoformat(timestamp)
                if timestamp >= bootTime and "fsck" in entry:
                    reallyInterestingEntries.append(entry)
            await client.send_message('me', "Disk logs:\n" + '\n'.join(reallyInterestingEntries))
    print("done")
    await serve_repeater()


with client:
    client.loop.run_until_complete(main())
    client.loop.run_forever()
