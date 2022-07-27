import os

from yt_dlp import YoutubeDL
# Change Me!
FFMPEG_PATH = os.environ['FFMPEG_PATH']
ydl_opts_download_music = {
    'ffmpeg_location': FFMPEG_PATH,
    'format': 'bestaudio',
    'outtmpl': {
        'default': 'downloaded/%(artist)s - %(title)s.%(ext)s'
    },
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

ydl_opts_download_video = {
    'ffmpeg_location': FFMPEG_PATH,
    'format': 'bestvideo*+bestaudio/best',
    'outtmpl': {
        'default': 'downloaded/%(uploader)s - %(title)s.%(ext)s'
    },
}


def try_download_music(link, download=False):
    # download = False -> just prints out available formats
    # download = True -> downloads into  ./downloaded/
    with YoutubeDL() as yt:
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


def try_download_video(link):
    with YoutubeDL(ydl_opts_download_video) as yt:
        yt.download(link)


was = False
for line in open('downloader_script_input.txt'):
    if not was and line.strip() == '--start--':
        was = True
    elif was:
        link = line.strip().split('&')[0]
        # try_download_music(link, download=True)
        try_download_video(link)
