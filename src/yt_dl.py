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
print(f"Downloading transcript for: {youtube_url}")

ydl_opts = {
    'skip_download': True,
    'writesubtitles': True,
    'writeautomaticsub': True,
    'subtitleslangs': ['en', 'zh-TW'],
    'outtmpl': output_path,
    'verbose': True,  # Add verbose output
    'quiet': False,   # Don't be quiet
    'no_warnings': False,  # Show warnings
}

try:
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        print("Starting download with yt-dlp...")
        ydl.download([youtube_url])
        print("Download completed")
        
        # Check if files were created
        vtt_files = [f for f in os.listdir(data_dir) if f.endswith('.vtt')]
        if vtt_files:
            print(f"Successfully downloaded {len(vtt_files)} VTT files:")
            for vtt_file in vtt_files:
                file_path = os.path.join(data_dir, vtt_file)
                file_size = os.path.getsize(file_path)
                print(f"  - {vtt_file} ({file_size} bytes)")
        else:
            print("Warning: No VTT files were downloaded")
except Exception as e:
    print(f"Error downloading transcript: {e}")
    sys.exit(1)
    
print("VTT files have been downloaded")