import yt_dlp as youtube_dl
import os
import sys


data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)
output_path = os.path.join(data_dir, 'transcript')

# Get YouTube URL from command line arguments
if len(sys.argv) < 2:
    print("Error: Please provide a YouTube URL as a command-line argument")
    print("Usage: python yt_dl.py <youtube_url>")
    sys.exit(1)

youtube_url = sys.argv[1]

ydl_opts = {
    'skip_download': True,
    'writesubtitles': True,
    'writeautomaticsub': True,
    'subtitleslangs': ['en', 'zh-TW'],
    'outtmpl': output_path
}

with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    ydl.download([youtube_url])
    
print("vtt files had been downloaded")