import os
import sys
import json
import asyncio
import time
import re
import webbrowser
import subprocess
from dotenv import load_dotenv

# Add src directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from parse_vtt import parse_vtt, chunk_transcript
from context_cache import ContextCache
from batch_processor import BatchProcessor

# YouTube video URL - initially set to None, will be updated by user input
YOUTUBE_VIDEO_URL = None

# Default questions for quick testing
default_questions = [
    "What is the main topic of this video?",
    "What are the key points discussed in the video?",
    "What are the conclusions or takeaways from the video?"
]

def extract_video_id(url):
    """
    Extract the video ID from a YouTube URL
    
    Args:
        url: YouTube URL
        
    Returns:
        Video ID
    """
    # Regular expression to extract video ID from various YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/shorts\/([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def get_video_title(url):
    """
    Get the title of a YouTube video
    
    Args:
        url: YouTube URL
        
    Returns:
        Video title or None if failed
    """
    try:
        import yt_dlp
        
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('title')
    except Exception as e:
        print(f"Error getting video title: {e}")
        return None

def sanitize_filename(filename):
    """
    Sanitize a string to be used as a filename
    
    Args:
        filename: String to sanitize
        
    Returns:
        Sanitized string
    """
    # Replace invalid characters with underscores
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Limit length to avoid issues with long filenames
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    
    return sanitized

def timestamp_to_youtube_url(timestamp):
    """
    Convert a timestamp in format HH:MM:SS to YouTube URL with time parameter
    
    Args:
        timestamp: Timestamp in format HH:MM:SS
        
    Returns:
        YouTube URL with time parameter
    """
    # Extract hours, minutes, seconds from timestamp
    match = re.match(r'(\d{2}):(\d{2}):(\d{2})', timestamp)
    if not match:
        return YOUTUBE_VIDEO_URL
    
    hours, minutes, seconds = map(int, match.groups())
    
    # Convert to seconds
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    # Create YouTube URL with time parameter
    return f"{YOUTUBE_VIDEO_URL}&t={total_seconds}"

def format_results(results):
    """
    Format the results in a structured and user-friendly way
    
    Args:
        results: List of result dictionaries containing question, answer, and timestamps
        
    Returns:
        Formatted string to display
    """
    formatted_output = "\n" + "=" * 80 + "\n"
    formatted_output += "📋 PROCESSING RESULTS\n"
    formatted_output += "=" * 80 + "\n\n"
    
    for i, result in enumerate(results):
        # Question block
        formatted_output += f"❓ QUESTION {i+1}:\n"
        formatted_output += f"{result['question']}\n"
        formatted_output += "-" * 80 + "\n"
        
        if result['success']:
            # Answer block
            formatted_output += "💬 ANSWER:\n"
            answer = result['answer']
            
            # Process answer to add clickable timestamp links
            if result.get('timestamps') and len(result['timestamps']) > 0:
                # Create a mapping of timestamps to their positions in the answer
                timestamp_positions = {}
                for timestamp in result['timestamps']:
                    # Find all occurrences of this timestamp in the answer
                    start_pos = 0
                    while True:
                        pos = answer.find(f"[{timestamp}]", start_pos)
                        if pos == -1:
                            break
                        timestamp_positions[pos] = timestamp
                        start_pos = pos + 1
                
                # Sort positions in reverse order to avoid index shifting
                sorted_positions = sorted(timestamp_positions.keys(), reverse=True)
                
                # Replace timestamps with clickable links
                for pos in sorted_positions:
                    timestamp = timestamp_positions[pos]
                    # Create a clickable link using ANSI escape sequences
                    youtube_url = timestamp_to_youtube_url(timestamp)
                    # ANSI escape sequence for clickable link: \e]8;;URL\e\\text\e]8;;\e\\
                    link = f"\033]8;;{youtube_url}\033\\\033[1;34m[{timestamp}]\033[0m\033]8;;\033\\"
                    answer = answer[:pos] + link + answer[pos + len(f"[{timestamp}]"):]
            
            formatted_output += f"{answer}\n\n"
            
            # Timestamps block with clickable links - only show if there are timestamps
            if result.get('timestamps') and len(result['timestamps']) > 0:
                formatted_output += "⏱️ RELEVANT TIMESTAMPS:\n"
                for timestamp in result['timestamps']:
                    # Create a clickable link for each timestamp
                    youtube_url = timestamp_to_youtube_url(timestamp)
                    # ANSI escape sequence for clickable link
                    link = f"\033]8;;{youtube_url}\033\\\033[1;34m{timestamp}\033[0m\033]8;;\033\\"
                    formatted_output += f"  • {link}\n"
                
                # Add note about clickable timestamps
                formatted_output += "\n\033[3mNote: Timestamps in blue are clickable links to jump to that point in the YouTube video.\033[0m\n"
                
                # Add a section with plain URLs for macOS users
                formatted_output += "\n🔗 PLAIN URLS FOR MACOS USERS:\n"
                for timestamp in result['timestamps']:
                    youtube_url = timestamp_to_youtube_url(timestamp)
                    formatted_output += f"  • {timestamp}: {youtube_url}\n"
                formatted_output += "\n\033[3mNote: For macOS users, you can copy and paste these URLs into your browser.\033[0m\n"
        else:
            # Error block
            formatted_output += "❌ ERROR:\n"
            formatted_output += f"{result['error']}\n"
        
        formatted_output += "=" * 80 + "\n\n"
    
    return formatted_output

def display_progress(current, total, prefix="Processing", suffix="Complete", length=50, fill="█"):
    """
    Display a progress bar in the console
    
    Args:
        current: Current progress value
        total: Total number of items
        prefix: Prefix string
        suffix: Suffix string
        length: Bar length
        fill: Bar fill character
    """
    # Skip progress bar for model loading
    if "Loading model" in prefix:
        print(f"{prefix}... {suffix}")
        return
        
    percent = ("{0:.1f}").format(100 * (current / float(total)))
    filled_length = int(length * current // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='\r')
    # Print new line on complete
    if current == total:
        print()

async def process_questions_async(processor, questions):
    """Process questions asynchronously and return results"""
    print("Processing questions in batch...")
    print("Note: Each question will have access to the answers of previous questions")
    
    # Display initial progress
    display_progress(0, len(questions), prefix="Processing questions", suffix="Started")
    
    # Process questions and update progress
    results = []
    all_answers = []  # Store all answers to be referenced by subsequent questions
    
    for i, question in enumerate(questions):
        # Create a prompt that includes previous answers for context
        prompt = processor._create_interconnected_prompt(question, all_answers)
        
        # Process the question with the enhanced prompt
        result = await processor._process_single_question_with_prompt_async(question, prompt)
        results.append(result)
        
        # If successful, add the answer to the context for subsequent questions
        if result['success']:
            all_answers.append({
                'question': question,
                'answer': result['answer'],
                'timestamps': result.get('timestamps', [])
            })
        
        # Update progress
        display_progress(i + 1, len(questions), prefix="Processing questions", suffix="Complete")
    
    # Save results
    output_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results.json')
    processor.save_results(results, output_file)
    
    print("Processing complete!")
    
    # Return results without displaying them (main function will handle display)
    return results

# Synchronous version as a wrapper
def process_questions(processor, questions):
    """Process questions synchronously (wraps async method)"""
    asyncio.run(process_questions_async(processor, questions))

def display_qa_history(cache):
    """Display QA history from cache"""
    if not cache.qa_cache:
        print("\nNo QA history found")
        return
        
    print("\n" + "=" * 80)
    print("📚 QA HISTORY")
    print("=" * 80)
    
    for i, qa in enumerate(cache.qa_cache):
        print(f"\n📝 ENTRY {i+1}:")
        print(f"⏰ Time: {qa['time']}")
        print(f"❓ Question: {qa['question']}")
        
        # Truncate long answers for display
        answer_display = qa['answer'][:200] + "..." if len(qa['answer']) > 200 else qa['answer']
        print(f"💬 Answer: {answer_display}")
        
        if qa.get('timestamps'):
            print("⏱️ Relevant timestamps:")
            for timestamp in qa['timestamps']:
                print(f"  • {timestamp}")
        
        print("-" * 80)

async def process_interconnected_questions_async(processor, questions):
    """Process interconnected questions asynchronously and return results"""
    print("Processing interconnected questions...")
    print("Note: Each question will have access to the answers of previous questions")
    
    # Display initial progress
    display_progress(0, len(questions), prefix="Processing interconnected questions", suffix="Started")
    
    # Process questions and update progress
    results = []
    all_answers = []  # Store all answers to be referenced by subsequent questions
    
    for i, question in enumerate(questions):
        # Create a prompt that includes previous answers for context
        prompt = processor._create_interconnected_prompt(question, all_answers)
        
        # Process the question with the enhanced prompt
        result = await processor._process_single_question_with_prompt_async(question, prompt)
        results.append(result)
        
        # If successful, add the answer to the context for subsequent questions
        if result['success']:
            all_answers.append({
                'question': question,
                'answer': result['answer'],
                'timestamps': result.get('timestamps', [])
            })
        
        # Update progress
        display_progress(i + 1, len(questions), prefix="Processing interconnected questions", suffix="Complete")
    
    # Save results
    output_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results.json')
    processor.save_results(results, output_file)
    
    print("Processing complete!")
    
    # Return results without displaying them (main function will handle display)
    return results

# Synchronous version as a wrapper
def process_interconnected_questions(processor, questions):
    """Process interconnected questions synchronously (wraps async method)"""
    asyncio.run(process_interconnected_questions_async(processor, questions))

def get_cached_videos():
    """
    Get a list of cached videos from the cache directory
    
    Returns:
        List of dictionaries containing video information
    """
    cache_dir = os.path.join(project_root, 'cache')
    if not os.path.exists(cache_dir):
        return []
    
    cached_videos = []
    for item in os.listdir(cache_dir):
        item_path = os.path.join(cache_dir, item)
        if os.path.isdir(item_path):
            # Check if the directory contains a transcript cache file
            transcript_cache_file = os.path.join(item_path, 'transcript_cache.json')
            if os.path.exists(transcript_cache_file) and os.path.getsize(transcript_cache_file) > 0:
                # Try to get video title from directory name
                video_title = item
                # Check if there's a video_info.json file with more details
                video_info_file = os.path.join(item_path, 'video_info.json')
                if os.path.exists(video_info_file):
                    try:
                        with open(video_info_file, 'r', encoding='utf-8') as f:
                            video_info = json.load(f)
                            video_title = video_info.get('title', item)
                            video_url = video_info.get('url', '')
                    except:
                        video_url = ''
                else:
                    video_url = ''
                
                cached_videos.append({
                    'title': video_title,
                    'cache_dir': item_path,
                    'url': video_url
                })
    
    return cached_videos

def save_video_info(cache_dir, video_title, video_url):
    """
    Save video information to a JSON file
    
    Args:
        cache_dir: Path to the cache directory
        video_title: Title of the video
        video_url: URL of the video
    """
    video_info = {
        'title': video_title,
        'url': video_url,
        'date_added': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    video_info_file = os.path.join(cache_dir, 'video_info.json')
    with open(video_info_file, 'w', encoding='utf-8') as f:
        json.dump(video_info, f, ensure_ascii=False, indent=2)

async def main_async():
    """Main asynchronous function"""
    # Load environment variables
    load_dotenv()
    
    # Check for API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        print("Please create a .env file with your API key.")
        return
    
    # Initialize variables
    global YOUTUBE_VIDEO_URL, cache, processor
    YOUTUBE_VIDEO_URL = None
    cache = None
    processor = None
    
    # Default questions for testing
    default_questions = [
        "What is the main topic of this video?",
        "What are the key points discussed in the video?",
        "What examples or demonstrations are provided?",
        "What conclusions or recommendations are made?"
    ]
    
    # Main menu loop
    while True:
        print("\n" + "=" * 80)
        print("🎥 YOUTUBE TRANSCRIPT QA SYSTEM")
        print("=" * 80)
        print("1. Load YouTube video")
        print("2. Process questions (with context)")
        print("3. Display QA history")
        print("4. Clear cache")
        print("5. Use default questions")
        print("6. Exit")
        print("=" * 80)
        
        choice = input("Enter your choice (1-6): ")
        
        if choice == "1":
            # Check for cached videos
            cached_videos = get_cached_videos()
            
            if cached_videos:
                print("\n📁 CACHED VIDEOS:")
                for i, video in enumerate(cached_videos):
                    print(f"{i+1}. {video['title']}")
                print(f"{len(cached_videos)+1}. Load a new video")
                
                video_choice = input(f"\nSelect a video (1-{len(cached_videos)+1}) or enter a new YouTube URL: ")
                
                # Check if user selected a cached video
                try:
                    video_index = int(video_choice) - 1
                    if 0 <= video_index < len(cached_videos):
                        # User selected a cached video
                        selected_video = cached_videos[video_index]
                        cache_dir = selected_video['cache_dir']
                        video_title = selected_video['title']
                        YOUTUBE_VIDEO_URL = selected_video['url']
                        
                        print(f"\nLoading cached video: {video_title}")
                        
                        # Initialize context cache with the video-specific directory
                        cache = ContextCache(cache_dir=cache_dir)
                        
                        # Initialize batch processor
                        processor = BatchProcessor(api_key=api_key, cache=cache)
                        # Set video_id for clickable timestamps
                        processor.video_id = extract_video_id(YOUTUBE_VIDEO_URL)
                        
                        # Create Google API cache for the transcript
                        print("Creating Google API cache for the transcript...")
                        cache_id = processor.create_google_cache()
                        if cache_id:
                            print(f"Successfully created Google API cache with ID: {cache_id}")
                        else:
                            print("Failed to create Google API cache. Will use standard API calls.")
                        
                        print(f"Video loaded successfully: {video_title}")
                        continue
                    elif video_index == len(cached_videos):
                        # User selected "Load a new video" option
                        print("\nEnter the YouTube video URL:")
                        youtube_url = input().strip()
                    else:
                        print("Invalid selection. Returning to main menu.")
                        continue
                except ValueError:
                    # User entered a URL instead of a number
                    youtube_url = video_choice.strip()
            else:
                # No cached videos, ask for a new URL
                print("\nEnter the YouTube video URL:")
                youtube_url = input().strip()
            
            if not youtube_url:
                print("No URL entered. Returning to main menu.")
                continue
            
            # Extract video ID
            video_id = extract_video_id(youtube_url)
            if not video_id:
                print("Invalid YouTube URL. Please try again.")
                continue
            
            # Set global YouTube URL
            YOUTUBE_VIDEO_URL = youtube_url
            
            # Get video title
            video_title = get_video_title(youtube_url)
            if not video_title:
                print("Could not get video title. Using video ID instead.")
                cache_dir_name = video_id
            else:
                # Sanitize the title for use as a directory name
                cache_dir_name = sanitize_filename(video_title)
                print(f"Video title: {video_title}")
            
            # Create a unique cache directory for this video
            video_cache_dir = os.path.join(project_root, 'cache', cache_dir_name)
            os.makedirs(video_cache_dir, exist_ok=True)
            
            # Initialize context cache with the video-specific directory
            cache = ContextCache(cache_dir=video_cache_dir)
            
            # Check if transcript already exists in cache
            transcript_cache_file = os.path.join(video_cache_dir, 'transcript_cache.json')
            if os.path.exists(transcript_cache_file) and os.path.getsize(transcript_cache_file) > 0:
                print(f"Found existing transcript for video: {youtube_url}")
                use_cached = input("Do you want to use the cached transcript? (y/n): ")
                
                if use_cached.lower() == 'y':
                    print(f"Loading existing transcript for video: {youtube_url}")
                    # Load transcript from cache
                    with open(transcript_cache_file, 'r', encoding='utf-8') as f:
                        transcript_data = json.load(f)
                    
                    # Initialize batch processor
                    processor = BatchProcessor(api_key=api_key, cache=cache)
                    # Set video_id for clickable timestamps
                    processor.video_id = video_id
                    
                    # Create Google API cache for the transcript
                    print("Creating Google API cache for the transcript...")
                    cache_id = processor.create_google_cache()
                    if cache_id:
                        print(f"Successfully created Google API cache with ID: {cache_id}")
                    else:
                        print("Failed to create Google API cache. Will use standard API calls.")
                    
                    # Save video info
                    save_video_info(video_cache_dir, video_title, youtube_url)
                    
                    print(f"Video loaded successfully: {youtube_url}")
                    continue
                else:
                    print("Downloading fresh transcript...")
            
            # Download transcript
            print(f"Downloading transcript for video: {youtube_url}")
            try:
                # Run yt_dl.py with the YouTube URL as an argument
                subprocess.run([sys.executable, os.path.join(project_root, 'src', 'yt_dl.py'), youtube_url], check=True)
                
                # Parse VTT file
                data_dir = os.path.join(project_root, 'data')
                vtt_file = os.path.join(data_dir, 'transcript.en.vtt')
                
                if not os.path.exists(vtt_file):
                    print(f"Error: VTT file does not exist: {vtt_file}")
                    continue
                
                print(f"Parsing VTT file: {vtt_file}")
                segments = parse_vtt(vtt_file)
                chunks = chunk_transcript(segments, max_chunk_size=4000)
                print(f"Parsed {len(segments)} segments, divided into {len(chunks)} chunks")
                
                # Add transcript chunks to cache
                cache.add_transcript_chunks(chunks)
                print("Transcript added to cache")
                
                # Save video info
                save_video_info(video_cache_dir, video_title, youtube_url)
                
                # Initialize batch processor
                processor = BatchProcessor(api_key=api_key, cache=cache)
                # Set video_id for clickable timestamps
                processor.video_id = video_id
                
                # Create Google API cache for the transcript
                print("Creating Google API cache for the transcript...")
                cache_id = processor.create_google_cache()
                if cache_id:
                    print(f"Successfully created Google API cache with ID: {cache_id}")
                else:
                    print("Failed to create Google API cache. Will use standard API calls.")
            except Exception as e:
                print(f"Error downloading or processing transcript: {e}")
                continue
            
            print(f"Video loaded successfully: {youtube_url}")
            
        elif choice == "2":
            # Check if a video is loaded
            if not YOUTUBE_VIDEO_URL or not cache or not processor:
                print("Please load a YouTube video first (option 1)")
                continue
                
            # Get questions from user
            print("\nEnter your questions (one per line, press Enter twice to finish):")
            print("Note: Later questions can reference answers from earlier questions.")
            questions = []
            while True:
                question = input()
                if not question:
                    break
                questions.append(question)
            
            if not questions:
                print("No questions entered. Returning to main menu.")
                continue
            
            # Process questions
            results = await process_questions_async(processor, questions)
            
            # Display results
            print(format_results(results))
            
        elif choice == "3":
            # Check if a video is loaded
            if not cache:
                print("Please load a YouTube video first (option 1)")
                continue
                
            # Display QA history
            display_qa_history(cache)
            
        elif choice == "4":
            # Check if a video is loaded
            if not cache:
                print("Please load a YouTube video first (option 1)")
                continue
                
            # Clear cache
            confirm = input("Are you sure you want to clear the cache? This will delete all QA history. (y/n): ")
            if confirm.lower() == 'y':
                cache.clear_cache()
                print("Cache cleared successfully.")
            else:
                print("Cache clearing cancelled.")
                
        elif choice == "5":
            # Check if a video is loaded
            if not YOUTUBE_VIDEO_URL or not cache or not processor:
                print("Please load a YouTube video first (option 1)")
                continue
                
            # Use default questions
            print("\nUsing default questions:")
            for i, question in enumerate(default_questions):
                print(f"{i+1}. {question}")
            
            # Process default questions
            results = await process_questions_async(processor, default_questions)
            
            # Display results
            print(format_results(results))
                
        elif choice == "6":
            print("Exiting program. Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")

def main():
    """Synchronous entry function (wraps async method)"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()