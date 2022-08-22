import os
import pathlib

from yt_dlp import YoutubeDL
from subprocess import check_output

# Change Me!
FFMPEG_PATH = os.environ['FFMPEG_PATH']
print(FFMPEG_PATH)


def isVideo(link: str):
    if 'playlist' in link or ' ' in link or 'youtu' not in link.lower():
        return False
    try:
        with YoutubeDL({'quiet': 1, "noplaylist": 1}) as yt:
            info = yt.extract_info(link, download=False)
        return True
    except Exception as exc:
        print(exc)
        return False


def try_download_music(link, download=False, subdirectory=''):
    # download = False -> just prints out available formats
    # download = True -> downloads into  ./downloaded/
    # subdirectory is a string like: "subdir_name/"
    ydl_opts_download_music = {
        'ffmpeg_location': FFMPEG_PATH,
        'format': 'bestaudio',
        'outtmpl': {
            'default': f'downloaded/{subdirectory}%(artist)s - %(title)s.%(ext)s'
        },
        "noplaylist": 1,
        'writethumbnail': True,
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0'
            },
            {'key': 'EmbedThumbnail'}
        ],
    }

    with YoutubeDL({"noplaylist": 1}) as yt:
        info = yt.extract_info(link, download=False)
        for form in info['formats'][::-1]:
            if str(form['format_id']) == '251':
                break
        else:
            raise Exception("Format not found")

    with YoutubeDL(ydl_opts_download_music) as yt:
        if download:
            yt.download(link)
        else:
            info = yt.extract_info(link, download=False)
            yt.list_formats(info)


def try_download_video(link, subdirectory=''):
    # subdirectory is a string like: "subdir_name/"
    ydl_opts_download_video = {
        'ffmpeg_location': FFMPEG_PATH,
        "noplaylist": 1,
        'format': 'bestvideo*+bestaudio/best',
        'outtmpl': {
            'default': f'downloaded/{subdirectory}%(uploader)s - %(title)s.%(ext)s'
        },
    }
    with YoutubeDL(ydl_opts_download_video) as yt:
        yt.download(link)


if __name__ == '__main__':
    was = False
    for line in open('downloader_script_input.txt'):
        if not was and line.strip() == '--start--':
            was = True
        elif was:
            link = line.strip().split('&')[0]
            # isVideo("https://soundcloud.com/ihfmusic")
            try_download_music(
                'https://soundcloud.com/ihfmusic/dont-miss-out?utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing')
            # try_download_video(link)
