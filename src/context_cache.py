import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class ContextCache:
    
    def __init__(self, cache_dir: str = None):
        # Get path of project root and cache folder path
        if cache_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.cache_dir = os.path.join(project_root, 'cache')
        else:
            self.cache_dir = cache_dir
            
        # Check if cache folder is existed
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Data structure of vedio content and QA history 
        self.transcript_cache = {}  # Video content
        self.qa_cache = []  # QA history
        
        # Cache path
        self.transcript_cache_file = os.path.join(self.cache_dir, 'transcript_cache.json')
        self.qa_cache_file = os.path.join(self.cache_dir, 'qa_cache.json')
        
        # Cache Loader
        self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(self.transcript_cache_file):
            try:
                with open(self.transcript_cache_file, 'r', encoding='utf-8') as f:
                    self.transcript_cache = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Loading transcript_cache_file error: {e}")
        
        if os.path.exists(self.qa_cache_file):
            try:
                with open(self.qa_cache_file, 'r', encoding='utf-8') as f:
                    self.qa_cache = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Loading qa_cache_file error: {e}")
                # If there's an error loading the cache, reset it to avoid further issues
                self.qa_cache = []
    
    def _save_cache(self):
        # Create a deep copy of the cache to avoid modifying the original
        qa_cache_serializable = []
        
        for qa in self.qa_cache:
            # Create a new dictionary for each QA pair
            qa_copy = {}
            
            # Copy all fields except 'embedding'
            for key, value in qa.items():
                if key != 'embedding':
                    qa_copy[key] = value
            
            # Handle embedding separately - convert numpy array to list
            if 'embedding' in qa:
                if isinstance(qa['embedding'], np.ndarray):
                    qa_copy['embedding'] = qa['embedding'].tolist()
                elif isinstance(qa['embedding'], list):
                    qa_copy['embedding'] = qa['embedding']
                else:
                    # Skip embedding if it's not in a format we can serialize
                    print(f"Warning: Skipping embedding of type {type(qa['embedding'])}")
            
            qa_cache_serializable.append(qa_copy)
        
        # Save transcript to cache
        try:
            with open(self.transcript_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.transcript_cache, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error occurred while saving transcripts to cache: {e}")
        
        # Save QA to cache
        try:
            with open(self.qa_cache_file, 'w', encoding='utf-8') as f:
                json.dump(qa_cache_serializable, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error occurred while saving QA to cache: {e}")
    
    def add_transcript_chunks(self, chunks: List[Dict[str, Any]]):
        for i, chunk in enumerate(chunks):
            # Use timestamp as unique key 
            key = f"{chunk['start_time']}_{chunk['end_time']}"
            self.transcript_cache[key] = {
                'index': i,
                'start_time': chunk['start_time'],
                'end_time': chunk['end_time'],
                'text': chunk['text']
            }
        
        # Save updated content in cache
        self._save_cache()
    
    # Store QA information
    def add_qa_pair(self, question: str, answer: str, related_timestamps: List[str] = None):
        qa_pair = {
            'question': question,
            'answer': answer,
            'timestamps': related_timestamps if related_timestamps is not None else [],
            'time': datetime.now().isoformat()
        }
        
        self.qa_cache.append(qa_pair)
        
        # Save to cache
        self._save_cache()
    
    def get_transcript_context(self, timestamps: List[str] = None, max_chars: int = 8000) -> str:
        if not timestamps:
            sorted_chunks = sorted(
                self.transcript_cache.values(),
                key=lambda x: x['index']
            )
        else:
            filtered_chunks = []
            for timestamp in timestamps:
                for chunk in self.transcript_cache.values():
                    if chunk['start_time'] <= timestamp <= chunk['end_time']:
                        filtered_chunks.append(chunk)
            
            sorted_chunks = sorted(filtered_chunks, key=lambda x: x['index'])
        
        # Combine context
        context = ""
        for chunk in sorted_chunks:
            chunk_text = f"[{chunk['start_time']} - {chunk['end_time']}] {chunk['text']}\n\n"
            
            if len(context) + len(chunk_text) > max_chars:
                break
                
            context += chunk_text
            
        return context.strip()
    
    def get_related_qa(self, question: str, max_pairs: int = 3) -> List[Dict[str, Any]]:
        """
        Get related question-answer pairs based on semantic similarity using the all-MiniLM-L6-v2 model.
        
        Args:
            question: The current question to find related pairs for
            max_pairs: Maximum number of related pairs to return
            
        Returns:
            List of related question-answer pairs sorted by relevance
        """
        # If no QA history, return empty list
        if not self.qa_cache:
            return []
            
        # Lazy loading of the embedding model
        if not hasattr(self, '_model'):
            try:
                from sentence_transformers import SentenceTransformer
                print("Loading embedding model (this may take a few seconds)...")
                self._model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
                print("Model loaded successfully!")
            except ImportError:
                print("Warning: sentence-transformers not installed. Falling back to keyword matching.")
                return self._fallback_keyword_matching(question, max_pairs)
            except Exception as e:
                print(f"Error loading model: {e}")
                print("Falling back to keyword matching.")
                return self._fallback_keyword_matching(question, max_pairs)
        
        # Calculate embedding for the current question
        question_embedding = self._model.encode([question])[0]
        
        # Calculate similarity scores for each QA pair
        scored_qa = []
        for qa in self.qa_cache:
            # If embedding not calculated yet, calculate and cache it
            if 'embedding' not in qa:
                qa['embedding'] = self._model.encode([qa['question']])[0]
                # Save cache after adding embedding to make it persistent
                self._save_cache()
            
            # Convert embedding to numpy array if it's a list (loaded from cache)
            embedding = qa['embedding']
            if isinstance(embedding, list):
                embedding = np.array(embedding)
            
            # Calculate cosine similarity
            similarity = cosine_similarity([question_embedding], [embedding])[0][0]
            
            # Combine with time factor (recent QAs get higher weight)
            from datetime import datetime
            now = datetime.now()
            qa_time = datetime.fromisoformat(qa['time'])
            time_diff = (now - qa_time).total_seconds() / 3600  # hours
            time_factor = 1 / (1 + time_diff / 24)  # 24-hour decay
            final_score = similarity * 0.7 + time_factor * 0.3  # 70% similarity, 30% time factor
            
            scored_qa.append((final_score, qa))
        
        # Sort by score
        sorted_qa = sorted(scored_qa, key=lambda x: x[0], reverse=True)
        
        # Return the most relevant QA pairs
        return [qa for _, qa in sorted_qa[:max_pairs]]
    
    def _fallback_keyword_matching(self, question: str, max_pairs: int = 3) -> List[Dict[str, Any]]:
        """
        Fallback method using simple keyword matching when embedding model is not available.
        
        Args:
            question: The current question to find related pairs for
            max_pairs: Maximum number of related pairs to return
            
        Returns:
            List of related question-answer pairs sorted by relevance
        """
        # Simple keyword matching
        keywords = set(question.lower().split())
        
        # Calculate relevance score for each QA pair
        scored_qa = []
        for qa in self.qa_cache:
            qa_keywords = set(qa['question'].lower().split())
            # Calculate keyword overlap ratio
            overlap = len(keywords.intersection(qa_keywords)) / len(keywords) if keywords else 0
            scored_qa.append((overlap, qa))
        
        # Sort by score
        sorted_qa = sorted(scored_qa, key=lambda x: x[0], reverse=True)
        
        # Return the most relevant QA pairs
        return [qa for _, qa in sorted_qa[:max_pairs]]
    
    # Clean cache
    def clear_cache(self):
        self.transcript_cache = {}
        self.qa_cache = []
        self._save_cache()