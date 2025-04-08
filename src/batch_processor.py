import os
import json
import time
import asyncio
import tempfile
from typing import List, Dict, Any, Optional
from google import genai
import aiohttp
from aiolimiter import AsyncLimiter

from context_cache import ContextCache

class BatchProcessor:
    """Class for batch processing questions, utilizing context caching and long context capabilities"""
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash-001", cache: ContextCache = None, 
                 requests_per_minute: int = 60):
        """
        Initialize the batch processor
        
        Args:
            api_key: Gemini API key
            model: Name of the model to use
            cache: Context cache instance, if None creates a new instance
            requests_per_minute: Maximum number of requests allowed per minute
        """
        # Initialize Gemini client
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.api_key = api_key
        
        # Initialize context cache
        self.cache = cache if cache else ContextCache()
        
        # Batch processing settings
        self.max_batch_size = 10  # Maximum number of questions per batch
        self.max_context_length = 16000  # Maximum context length
        
        # Rate limiting
        self.rate_limiter = AsyncLimiter(requests_per_minute, 60)  # X requests per minute
        
        # Google API cache ID
        self.google_cache_id = None
        
        # Check if model supports caching
        self.supports_caching = False
        try:
            # List of models known to support caching
            caching_models = ["gemini-1.5-flash-001", "gemini-1.5-pro-001"]
            
            # Check if current model is in the list of known caching models
            if self.model in caching_models:
                self.supports_caching = True
            else:
                # Try to check model capabilities
                for m in self.client.models.list():
                    if m.name == self.model:
                        for action in m.supported_actions:
                            if action == "createCachedContent":
                                self.supports_caching = True
                                break
                        break
        except Exception as e:
            print(f"Warning: Could not check if model supports caching: {e}")
            # Default to True for known models
            if self.model in ["gemini-1.5-flash-001", "gemini-1.5-pro-001"]:
                self.supports_caching = True
    
    def create_google_cache(self, transcript_chunks=None):
        """
        Create a Google API cache for the transcript
        
        Args:
            transcript_chunks: List of transcript chunks to cache. If None, will use the cache.
            
        Returns:
            Cache ID if successful, None otherwise
        """
        if not self.supports_caching:
            print("Warning: Current model does not support caching")
            return None
            
        try:
            # If no transcript chunks provided, get them from the cache
            if transcript_chunks is None:
                # Get all transcript chunks from the cache
                transcript_chunks = []
                for chunk in self.cache.transcript_cache.values():
                    transcript_chunks.append({
                        'start_time': chunk['start_time'],
                        'end_time': chunk['end_time'],
                        'text': chunk['text']
                    })
            
            # Combine transcript chunks into a single document
            transcript_text = ""
            for chunk in transcript_chunks:
                transcript_text += f"[{chunk['start_time']} - {chunk['end_time']}] {chunk['text']}\n\n"
            
            # Check if the content is too small for caching (less than 32,768 tokens)
            # Rough estimate: 1 token ≈ 4 characters for English text
            estimated_tokens = len(transcript_text) // 4
            
            if estimated_tokens < 32768:
                print(f"Warning: Content too small for caching (estimated {estimated_tokens} tokens, minimum 32,768 required)")
                print("Will use standard API calls without caching")
                return None
            
            # Create a temporary file with the transcript
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(transcript_text)
                temp_file_path = temp_file.name
            
            # Upload the file
            document = self.client.files.upload(file=temp_file_path)
            
            # Create cache with more specific system instruction
            cache = self.client.caches.create(
                model=self.model,
                config={
                    'contents': [document],
                    'system_instruction': 'You are an expert at analyzing video transcripts. Answer questions based on the content of the transcript. If information is not found in the transcript, clearly indicate this. ALWAYS include timestamps in square brackets [HH:MM:SS] when referencing information from the transcript.',
                },
            )
            
            # Store the cache ID
            self.google_cache_id = cache.name
            
            # Clean up
            os.unlink(temp_file_path)
            
            print(f"Created Google API cache with ID: {self.google_cache_id}")
            return self.google_cache_id
            
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Error creating Google API cache: {e}\n{traceback_str}")
            return None
    
    def _create_prompt(self, question: str, include_history: bool = True) -> str:
        """Create prompt to send to the model"""
        # Get relevant QA history
        history_context = ""
        if include_history:
            related_qa = self.cache.get_related_qa(question)
            if related_qa:
                history_context = "Here are previous questions and answers related to the video:\n\n"
                for qa in related_qa:
                    history_context += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
        
        # Get transcript context - this was missing and is critical for answering questions
        transcript_context = self.cache.get_transcript_context()
        
        # Build complete prompt with explicit instruction for not found information
        prompt = f"""Please answer the following question based on the video transcript. If the information is not found in the transcript, please indicate this clearly.

IMPORTANT: When referencing information from the transcript, ALWAYS include the timestamp in square brackets like this: [HH:MM:SS]. For example: "The speaker mentions at [00:01:30] that..."

Video Transcript:
{transcript_context}

{history_context}
Question: {question}
"""
        return prompt
    
    async def process_questions_async(self, questions: List[str]) -> List[Dict[str, Any]]:
        """Process questions asynchronously and display results"""
        print("Processing questions in batch...")
        results = await self.process_batch_async(questions)
        
        # Save results
        output_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results.json')
        self.save_results(results, output_file)
        
        print("Processing complete!")
        
        # Return results without displaying them (main.py will handle display)
        return results
    
    async def _process_single_question_async(self, question: str) -> Dict[str, Any]:
        """Process a single question asynchronously"""
        try:
            # Use rate limiter
            async with self.rate_limiter:
                # Create prompt
                prompt = self._create_prompt(question)
                
                # Call API
                from google.genai import types
                
                # Configure API call
                config = types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1024
                )
                
                # Add cached content if available
                if self.google_cache_id:
                    config.cached_content = self.google_cache_id
                    # When using cached content, we don't need to include the transcript in the prompt
                    # as it's already in the cache, so we'll modify the prompt to be more concise
                    # Get relevant QA history
                    history_context = ""
                    related_qa = self.cache.get_related_qa(question)
                    if related_qa:
                        history_context = "Here are previous questions and answers related to the video:\n\n"
                        for qa in related_qa:
                            history_context += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
                    
                    prompt = f"""Please answer the following question based on the video transcript. If the information is not found in the transcript, please indicate this clearly.

IMPORTANT: When referencing information from the transcript, ALWAYS include the timestamp in square brackets like this: [HH:MM:SS]. For example: "The speaker mentions at [00:01:30] that..."

{history_context}
Question: {question}
"""
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
            
            if hasattr(response, 'text'):
                answer = response.text
            else:
                answer = str(response.parts[0].text if hasattr(response, 'parts') else response)
            
            # Ensure answer is a string type
            if not isinstance(answer, str):
                answer = str(answer)
            
            # Check if answer is empty or None
            if not answer or answer.lower() == 'none':
                answer = "I apologize, but I couldn't generate a meaningful answer for this question. This might be due to limitations in the API response or the content of the video transcript. Please try rephrasing your question or asking about a different aspect of the video."
            
            # Process timestamp references - improved regex pattern
            import re
            # Match timestamps in format [HH:MM:SS] or [HH:MM:SS - HH:MM:SS]
            timestamps = re.findall(r'\[(\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:\s*-\s*\d{2}:\d{2}:\d{2}(?:\.\d{3})?)?)\]', answer)
            
            # Convert timestamps to clickable YouTube links if video_id is available
            if hasattr(self, 'video_id') and self.video_id:
                # Function to convert timestamp to seconds
                def timestamp_to_seconds(timestamp):
                    parts = timestamp.split(':')
                    if len(parts) == 3:
                        hours, minutes, seconds = parts
                        return int(hours) * 3600 + int(minutes) * 60 + int(float(seconds))
                    elif len(parts) == 2:
                        minutes, seconds = parts
                        return int(minutes) * 60 + int(float(seconds))
                    return 0
                
                # Replace timestamps with clickable links
                for timestamp in timestamps:
                    if '-' in timestamp:
                        # Handle timestamp ranges
                        start_time, end_time = timestamp.split('-')
                        start_time = start_time.strip()
                        end_time = end_time.strip()
                        start_seconds = timestamp_to_seconds(start_time)
                        end_seconds = timestamp_to_seconds(end_time)
                        
                        # Create clickable link for the start time
                        link = f"https://youtu.be/{self.video_id}?t={start_seconds}"
                        answer = answer.replace(f"[{timestamp}]", f"[{timestamp}]({link})")
                    else:
                        # Handle single timestamp
                        seconds = timestamp_to_seconds(timestamp)
                        link = f"https://youtu.be/{self.video_id}?t={seconds}"
                        answer = answer.replace(f"[{timestamp}]", f"[{timestamp}]({link})")
            
            # Check if the answer indicates no information was found
            no_info_phrases = [
                "does not mention", 
                "doesn't mention", 
                "not mentioned", 
                "no information", 
                "not found in the transcript",
                "not discussed in the transcript",
                "not covered in the transcript",
                "not provided in the transcript",
                "not stated in the transcript",
                "not indicated in the transcript",
                "not referenced in the transcript",
                "not included in the transcript",
                "not present in the transcript",
                "not available in the transcript",
                "not given in the transcript",
                "not shown in the transcript",
                "not described in the transcript",
                "not explained in the transcript",
                "not detailed in the transcript",
                "not specified in the transcript",
                "not outlined in the transcript",
                "not listed in the transcript",
                "not recorded in the transcript",
                "not documented in the transcript",
                "not noted in the transcript",
                "not reported in the transcript",
                "not revealed in the transcript",
                "not disclosed in the transcript",
                "not communicated in the transcript",
                "not conveyed in the transcript",
                "not expressed in the transcript",
                "not articulated in the transcript",
                "cannot find",
                "could not find",
                "unable to find",
                "no mention of",
                "no reference to",
                "no indication of",
                "no evidence of",
                "no data on",
                "no details about",
                "no information about",
                "no discussion of",
                "no coverage of",
                "no explanation of",
                "no description of",
                "no specification of",
                "no outline of",
                "no list of",
                "no record of",
                "no documentation of",
                "no note of",
                "no report of",
                "no revelation of",
                "no disclosure of",
                "no communication of",
                "no conveyance of",
                "no expression of",
                "no articulation of"
            ]
            
            # Check if the answer indicates no information was found
            no_info_found = False
            for phrase in no_info_phrases:
                if phrase.lower() in answer.lower():
                    no_info_found = True
                    break
            
            # If the answer indicates no information was found, clear timestamps
            if no_info_found:
                timestamps = []
                # Also modify the answer to make it clear that no information was found
                if not any(phrase.lower() in answer.lower() for phrase in ["no information", "not found", "cannot find"]):
                    answer = f"No information found in the transcript for this question. {answer}"
            
            # If no timestamps found and answer doesn't indicate no information, try to extract them from the transcript context
            if not timestamps and not no_info_found:
                # Get all timestamps from the transcript cache
                all_timestamps = []
                for chunk in self.cache.transcript_cache.values():
                    all_timestamps.append(chunk['start_time'])
                    all_timestamps.append(chunk['end_time'])
                
                # Look for timestamp mentions in the answer
                for timestamp in all_timestamps:
                    if timestamp in answer:
                        timestamps.append(timestamp)
            
            # Validate timestamps to ensure they are in the correct format
            valid_timestamps = []
            for timestamp in timestamps:
                # Check if timestamp is in the correct format (HH:MM:SS)
                if re.match(r'^\d{2}:\d{2}:\d{2}(?:\.\d{3})?$', timestamp):
                    valid_timestamps.append(timestamp)
                # If it's a range, extract the start time
                elif '-' in timestamp:
                    start_time = timestamp.split('-')[0].strip()
                    if re.match(r'^\d{2}:\d{2}:\d{2}(?:\.\d{3})?$', start_time):
                        valid_timestamps.append(start_time)
            
            # Use only valid timestamps
            timestamps = valid_timestamps
            
            # Add to QA cache
            self.cache.add_qa_pair(question, answer, timestamps)
            
            return {
                "question": question,
                "answer": answer,
                "timestamps": timestamps,
                "success": True
            }
            
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            return {
                "question": question,
                "error": f"{str(e)}\n{traceback_str}",
                "success": False
            }
    
    async def process_batch_async(self, questions: List[str]) -> List[Dict[str, Any]]:
        """Process a batch of questions asynchronously"""
        tasks = []
        results = []
        
        # Split questions into smaller batches
        for i in range(0, len(questions), self.max_batch_size):
            batch = questions[i:i + self.max_batch_size]
            
            print(f"Processing batch {i//self.max_batch_size + 1}/{(len(questions)-1)//self.max_batch_size + 1}, "
                  f"containing {len(batch)} questions")
            
            # Create async task for each question
            batch_tasks = []
            for question in batch:
                task = asyncio.create_task(self._process_single_question_async(question))
                batch_tasks.append(task)
                
            # Wait for all tasks in the current batch to complete
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
        
        return results
    
    # Keep synchronous methods as wrappers for async methods
    def process_batch(self, questions: List[str]) -> List[Dict[str, Any]]:
        """Process a batch of questions synchronously (wraps async method)"""
        return asyncio.run(self.process_batch_async(questions))
    
    # Other methods remain unchanged
    def _process_single_question(self, question: str) -> Dict[str, Any]:
        """Process a single question synchronously (wraps async method)"""
        return asyncio.run(self._process_single_question_async(question))
        
    async def process_interconnected_questions_async(self, questions: List[str]) -> List[Dict[str, Any]]:
        """
        Process interconnected questions asynchronously, where each question can build upon previous answers.
        
        This method processes questions sequentially, but each question can reference
        and build upon the answers to previous questions in the batch.
        
        Args:
            questions: List of questions to process
            
        Returns:
            List of results for each question
        """
        results = []
        all_answers = []  # Store all answers to be referenced by subsequent questions
        
        for i, question in enumerate(questions):
            print(f"Processing interconnected question {i+1}/{len(questions)}: {question[:50]}...")
            
            # Create a prompt that includes previous answers for context
            prompt = self._create_interconnected_prompt(question, all_answers)
            
            # Process the question with the enhanced prompt
            result = await self._process_single_question_with_prompt_async(question, prompt)
            results.append(result)
            
            # If successful, add the answer to the context for subsequent questions
            if result['success']:
                all_answers.append({
                    'question': question,
                    'answer': result['answer'],
                    'timestamps': result.get('timestamps', [])
                })
        
        return results
    
    def _create_interconnected_prompt(self, question: str, previous_answers: List[Dict[str, Any]]) -> str:
        """
        Create a prompt for interconnected questions that includes previous answers as context.
        
        Args:
            question: The current question
            previous_answers: List of previous question-answer pairs
            
        Returns:
            Enhanced prompt that includes previous answers as context
        """
        # Get relevant QA history from cache
        history_context = ""
        related_qa = self.cache.get_related_qa(question)
        if related_qa:
            history_context = "Here are previous questions and answers related to the video:\n\n"
            for qa in related_qa:
                history_context += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
        
        # Add previous answers from the current batch
        if previous_answers:
            history_context += "Here are the answers to previous questions in this batch:\n\n"
            for qa in previous_answers:
                history_context += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
        
        # Get transcript context
        transcript_context = self.cache.get_transcript_context()
        
        # Build complete prompt
        prompt = f"""Please answer the following question based on the video transcript and previous answers.
If the information is not found in the transcript, please indicate this clearly.

IMPORTANT: When referencing information from the transcript, ALWAYS include the timestamp in square brackets like this: [HH:MM:SS]. For example: "The speaker mentions at [00:01:30] that..."

Video Transcript:
{transcript_context}

{history_context}
Question: {question}
"""
        return prompt
    
    async def _process_single_question_with_prompt_async(self, question: str, prompt: str) -> Dict[str, Any]:
        """
        Process a single question with a custom prompt asynchronously.
        
        Args:
            question: The question to process
            prompt: Custom prompt to use
            
        Returns:
            Result dictionary
        """
        try:
            # Use rate limiter
            async with self.rate_limiter:
                # Call API
                from google.genai import types
                
                # Configure API call
                config = types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1024
                )
                
                # Add cached content if available
                if self.google_cache_id:
                    config.cached_content = self.google_cache_id
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                
                if hasattr(response, 'text'):
                    answer = response.text
                else:
                    answer = str(response.parts[0].text if hasattr(response, 'parts') else response)
                
                # Ensure answer is a string type
                if not isinstance(answer, str):
                    answer = str(answer)
                
                # Check if answer is empty or None
                if not answer or answer.lower() == 'none':
                    answer = "I apologize, but I couldn't generate a meaningful answer for this question. This might be due to limitations in the API response or the content of the video transcript. Please try rephrasing your question or asking about a different aspect of the video."
                
                # Process timestamp references - improved regex pattern
                import re
                # Match timestamps in format [HH:MM:SS] or [HH:MM:SS - HH:MM:SS]
                timestamps = re.findall(r'\[(\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:\s*-\s*\d{2}:\d{2}:\d{2}(?:\.\d{3})?)?)\]', answer)
                
                # Convert timestamps to clickable YouTube links if video_id is available
                if hasattr(self, 'video_id') and self.video_id:
                    # Function to convert timestamp to seconds
                    def timestamp_to_seconds(timestamp):
                        parts = timestamp.split(':')
                        if len(parts) == 3:
                            hours, minutes, seconds = parts
                            return int(hours) * 3600 + int(minutes) * 60 + int(float(seconds))
                        elif len(parts) == 2:
                            minutes, seconds = parts
                            return int(minutes) * 60 + int(float(seconds))
                        return 0
                    
                    # Replace timestamps with clickable links
                    for timestamp in timestamps:
                        if '-' in timestamp:
                            # Handle timestamp ranges
                            start_time, end_time = timestamp.split('-')
                            start_time = start_time.strip()
                            end_time = end_time.strip()
                            start_seconds = timestamp_to_seconds(start_time)
                            end_seconds = timestamp_to_seconds(end_time)
                            
                            # Create clickable link for the start time
                            link = f"https://youtu.be/{self.video_id}?t={start_seconds}"
                            answer = answer.replace(f"[{timestamp}]", f"[{timestamp}]({link})")
                        else:
                            # Handle single timestamp
                            seconds = timestamp_to_seconds(timestamp)
                            link = f"https://youtu.be/{self.video_id}?t={seconds}"
                            answer = answer.replace(f"[{timestamp}]", f"[{timestamp}]({link})")
                
                # Check if the answer indicates no information was found
                no_info_phrases = [
                    "does not mention", 
                    "doesn't mention", 
                    "not mentioned", 
                    "no information", 
                    "not found in the transcript",
                    "not discussed in the transcript",
                    "not covered in the transcript",
                    "not provided in the transcript",
                    "not stated in the transcript",
                    "not indicated in the transcript",
                    "not referenced in the transcript",
                    "not included in the transcript",
                    "not present in the transcript",
                    "not available in the transcript",
                    "not given in the transcript",
                    "not shown in the transcript",
                    "not described in the transcript",
                    "not explained in the transcript",
                    "not detailed in the transcript",
                    "not specified in the transcript",
                    "not outlined in the transcript",
                    "not listed in the transcript",
                    "not recorded in the transcript",
                    "not documented in the transcript",
                    "not noted in the transcript",
                    "not reported in the transcript",
                    "not revealed in the transcript",
                    "not disclosed in the transcript",
                    "not communicated in the transcript",
                    "not conveyed in the transcript",
                    "not expressed in the transcript",
                    "not articulated in the transcript",
                    "cannot find",
                    "could not find",
                    "unable to find",
                    "no mention of",
                    "no reference to",
                    "no indication of",
                    "no evidence of",
                    "no data on",
                    "no details about",
                    "no information about",
                    "no discussion of",
                    "no coverage of",
                    "no explanation of",
                    "no description of",
                    "no specification of",
                    "no outline of",
                    "no list of",
                    "no record of",
                    "no documentation of",
                    "no note of",
                    "no report of",
                    "no revelation of",
                    "no disclosure of",
                    "no communication of",
                    "no conveyance of",
                    "no expression of",
                    "no articulation of"
                ]
                
                # Check if the answer indicates no information was found
                no_info_found = False
                for phrase in no_info_phrases:
                    if phrase.lower() in answer.lower():
                        no_info_found = True
                        break
                
                # If the answer indicates no information was found, clear timestamps
                if no_info_found:
                    timestamps = []
                    # Also modify the answer to make it clear that no information was found
                    if not any(phrase.lower() in answer.lower() for phrase in ["no information", "not found", "cannot find"]):
                        answer = f"No information found in the transcript for this question. {answer}"
                
                # If no timestamps found and answer doesn't indicate no information, try to extract them from the transcript context
                if not timestamps and not no_info_found:
                    # Get all timestamps from the transcript cache
                    all_timestamps = []
                    for chunk in self.cache.transcript_cache.values():
                        all_timestamps.append(chunk['start_time'])
                        all_timestamps.append(chunk['end_time'])
                    
                    # Look for timestamp mentions in the answer
                    for timestamp in all_timestamps:
                        if timestamp in answer:
                            timestamps.append(timestamp)
                
                # Validate timestamps to ensure they are in the correct format
                valid_timestamps = []
                for timestamp in timestamps:
                    # Check if timestamp is in the correct format (HH:MM:SS)
                    if re.match(r'^\d{2}:\d{2}:\d{2}(?:\.\d{3})?$', timestamp):
                        valid_timestamps.append(timestamp)
                    # If it's a range, extract the start time
                    elif '-' in timestamp:
                        start_time = timestamp.split('-')[0].strip()
                        if re.match(r'^\d{2}:\d{2}:\d{2}(?:\.\d{3})?$', start_time):
                            valid_timestamps.append(start_time)
                
                # Use only valid timestamps
                timestamps = valid_timestamps
                
                # Add to QA cache
                self.cache.add_qa_pair(question, answer, timestamps)
                
                return {
                    "question": question,
                    "answer": answer,
                    "timestamps": timestamps,
                    "success": True
                }
                
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            return {
                "question": question,
                "error": f"{str(e)}\n{traceback_str}",
                "success": False
            }
    
    # Keep the synchronous version as a wrapper for the async method
    def process_interconnected_questions(self, questions: List[str]) -> List[Dict[str, Any]]:
        """Process interconnected questions synchronously (wraps async method)"""
        return asyncio.run(self.process_interconnected_questions_async(questions))
    
    def save_results(self, results: List[Dict[str, Any]], output_file: str = None):
        """Save processing results to a file"""
        if output_file is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_file = os.path.join(project_root, 'results.json')
        
        # Save results
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"Results saved to: {output_file}")