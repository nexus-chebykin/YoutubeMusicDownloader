from yt_dlp import YoutubeDL

# Change Me!
FFMPEG_PATH = r'C:\Users\Simon\Desktop\мм\ffmpeg-2021-10-18-git-d04c005021-full_build\ffmpeg-2021-10-18-git-d04c005021-full_build\bin'


def try_download(link, download=False):
    # download = False -> just prints out avalible formats
    # download = True -> downloads into  ./downloaded/
    with YoutubeDL() as yt:
        info = yt.extract_info(link, download=False)
        for form in info['formats'][::-1]:
            if str(form['format_id']) == '251':
                break
        else:
            raise Exception("Format not found")

    ydl_opts_download = {
        'ffmpeg_location': FFMPEG_PATH,
        'format': 'bestaudio',
        'outtmpl': {
            'default': 'downloaded/%(title)s.%(ext)s'
        },
        'writethumbnail': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '0'
        },
            {'key': 'EmbedThumbnail'}
        ],
    }

    with YoutubeDL(ydl_opts_download) as yt:
        if download:
            yt.download(link)
        else:
            info = yt.extract_info(link, download=False)
            yt.list_formats(info)


was = False
for line in open('downloader_script_input.txt'):
    if not was and line.strip() == '--start--':
        was = True
    elif was:
        link = line.strip().split('&')[0]
        try_download(link, download=True)
        # print(link)
