import os
import pathlib
from typing import Literal

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


def try_download(link, kind: Literal['music', 'video'], download=False, subdirectory='', progress_callback=None):
    # download = False -> just prints out available formats
    # download = True -> downloads into  ./downloaded/
    # subdirectory is a string like: "subdir_name/"
    common = {
        'ffmpeg_location': FFMPEG_PATH,
        'outtmpl': {
            'default': f'downloaded/{subdirectory}%(artist)s - %(title)s.%(ext)s'
        },
        "noplaylist": 1,
        'progress_hooks': [progress_callback] if progress_callback is not None else '',
        'source_address': '0.0.0.0',  # Force IPv4, since Интерсвязь дебилы
    }
    ydl_opts_download_music = {
        **common,
        'format': 'bestaudio',
        'writethumbnail': True,
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0'
            },
            {'add_chapters': True,
             'add_infojson': 'if_exists',
             'add_metadata': True,
             'key': 'FFmpegMetadata'},
            {'key': 'EmbedThumbnail'},
        ],

    }

    ydl_opts_download_video = {
        'format': 'bestvideo*[height<=1080]+bestaudio/best[height<=1080]',
        **common
    }

    ydl_opts = {
        'video': ydl_opts_download_video,
        'music': ydl_opts_download_music
    }

    # with YoutubeDL({"noplaylist": 1}) as yt:
    #     info = yt.extract_info(link, download=False)
    #     for form in info['formats'][::-1]:
    #         if str(form['format_id']) == '251':
    #             break
    #     else:
    #         raise Exception("Format not found")

    with YoutubeDL(ydl_opts[kind]) as yt:
        if download:
            yt.download(link)
        else:
            info = yt.extract_info(link, download=False)
            yt.list_formats(info)


if __name__ == '__main__':
    was = False
    for line in open('downloader_script_input.txt'):
        if not was and line.strip() == '--start--':
            was = True
        elif was:
            link = line.strip().split('&')[0]
            try_download(link, 'music', True, subdirectory="7213129/")
            # isVideo("https://soundcloud.com/ihfmusic")
            # try_download_video(
            #     'https://www.youtube.com/watch?v=nNYGqJd-cHU&list=PL4_hYwCyhAvbPdTFj35Zg2_y30DzeOtvS&index=3')
            # try_download_video(link)
