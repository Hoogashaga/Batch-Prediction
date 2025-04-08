# Batch-Prediction

A Python application for processing YouTube video transcripts and answering questions about their content using the Gemini API.

## Overview

Batch-Prediction is a tool that allows users to:
1. Download and process YouTube video transcripts
2. Ask questions about the video content
3. Get answers with relevant timestamps from the video
4. Cache results for efficient reuse

The application uses the Gemini API for natural language processing and provides a user-friendly interface for interacting with video content.


## Components

The project consists of several key components:

### 1. `yt_dl.py`
- Downloads YouTube video transcripts using `yt-dlp`
- Supports both manual and automatic subtitles
- Saves transcripts in VTT format

### 2. `parse_vtt.py`
- Parses VTT subtitle files into structured data
- Extracts timestamps and text content
- Chunks transcripts into manageable segments for API processing

### 3. `context_cache.py`
- Manages caching of transcripts and question-answer pairs
- Provides semantic search for related questions
- Handles persistence of data between sessions

### 4. `batch_processor.py`
- Core component that processes questions using the Gemini API
- Handles rate limiting and error recovery
- Extracts timestamps from answers
- Manages API caching for improved performance
- Implements asynchronous processing for better performance

### 5. `main.py`
- User interface for interacting with the system
- Handles video loading and question processing
- Provides options for batch or interactive question processing

## Asynchronous Processing

The application uses Python's `asyncio` library to implement asynchronous processing, which provides several benefits:

- **Improved Performance**: Multiple questions can be processed concurrently, reducing overall processing time
- **Rate Limiting**: Built-in rate limiting prevents API quota exhaustion
- **Resource Efficiency**: Better utilization of system resources during batch processing

The asynchronous implementation is particularly useful when processing multiple questions in batch mode, as it allows the application to make multiple API requests concurrently while respecting rate limits.

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/Hoogashaga/Batch-Prediction.git
   cd Batch-Prediction
   ```

2. Create and activate a virtual environment:
   ```
   python3 -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure your Gemini API key:
   - Obtain an API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create a `.env` file in the project root with the following content:
     ```
     GEMINI_API_KEY=your_api_key_here
     ```
   - To create the `.env` file, you can use one of these methods:
     ```
     # On Windows (Command Prompt)[Recommanded]
     echo GEMINI_API_KEY=your_api_key_here > .env
     
     # On Windows (PowerShell)
     Set-Content -Path .env -Value "GEMINI_API_KEY=your_api_key_here"
     
     # On macOS/Linux
     echo "GEMINI_API_KEY=your_api_key_here" > .env
     ```
   - Alternatively, you can create the file using any text editor and save it as `.env` in the project root directory.

## Usage

### Running the Application

```
python3 src/main.py
```

> **Note for Windows users**: It's recommended to use Windows Command Prompt or Windows Terminal for better experience, especially for clickable timestamps in the output.

### Loading a YouTube Video

1. Select **option 1** from the main menu to load a YouTube video
2. Enter the YouTube URL when prompted
3. The application will download and process the transcript

### Asking Questions

1. Select **option 2** from the main menu to ask questions
2. Enter your questions (one per line, press Enter twice to finish)
3. The application will process your questions sequentially, with each question having access to the answers of previous questions
4. The application will provide answers with relevant timestamps

### Batch Processing

1. Select **option 5** from the main menu to use default questions
2. The application will process all questions and save the results to `results.json`

## Example Questions and Expected Outputs

### Example Question:
"What does the speaker say about machine learning at the beginning of the video?"

### Expected Output:
```
Answer: The speaker mentions at [00:01:30] that machine learning is a subset of artificial intelligence that focuses on developing systems that can learn from and make decisions based on data. They go on to explain at [00:02:15] that this approach differs from traditional programming where rules are explicitly defined.
Relevant timestamps: ['00:01:30', '00:02:15']
```

## Advanced Features

### Caching
- The application automatically caches transcripts and question-answer pairs
- Cached data is stored in the `cache` directory
- Each video gets its own cache directory named after the video title

### Google API Caching
- The application supports Google API caching for improved performance
- For longer transcripts (over 32,768 tokens), the application can create a cache on Google's servers
- This reduces the need to repeatedly upload the transcript with each question
- Note: The free version of the Gemini API has limitations on caching. For optimal performance with longer videos, consider upgrading to a paid plan.

### Semantic Search
- The application uses semantic search to find related questions
- This helps provide more context for answering new questions

### Timestamp Extraction
- The application automatically extracts timestamps from answers
- Timestamps are formatted as [HH:MM:SS] and can be used to navigate to specific parts of the video
- On **Windows** Command Prompt or Windows Terminal, timestamps are **clickable** links
- **For macOS users**: Plain URLs are provided in the output for easy copying and pasting into a browser

## Troubleshooting

### Common Issues

1. **API Key Issues**
   - Ensure your API key is correctly set in the `.env` file
   - Check that the key has not expired

2. **Transcript Download Failures**
   - Verify that the YouTube video has captions available
   - Try using a different video URL

3. **Empty or "None" Answers**
   - The video transcript may not contain information related to your question
   - Try rephrasing your question or asking about a different aspect of the video

4. **Caching Limitations**
   - If you see a message like "Content too small for caching", this is normal for shorter videos
   - For longer videos, ensure you have sufficient API quota for caching operations

5. **Clickable Timestamps**
   - On Windows Command Prompt or Windows Terminal, timestamps are clickable links
   - On macOS Terminal, timestamps are not clickable, but plain URLs are provided in the output
   - If you're using macOS, you can copy and paste the plain URLs into your browser

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube video processing
- [Google Gemini API](https://ai.google.dev/) for natural language processing
- [sentence-transformers](https://www.sbert.net/) for semantic search capabilities
- [Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks](https://arxiv.org/abs/1908.10084) for the underlying semantic search technology
