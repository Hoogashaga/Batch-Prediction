import os
import json

def parse_vtt(vtt_file_path):
    print(f"Parsing VTT file: {vtt_file_path}")
    
    if not os.path.exists(vtt_file_path):
        print(f"Error: VTT file does not exist: {vtt_file_path}")
        return []
    
    try:
        with open(vtt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            print("Warning: VTT file is empty")
            return []
        
        # skip useless char
        lines = content.strip().split('\n')
        start_index = 0
        
        # Look for subtitle starting position
        for i, line in enumerate(lines):
            if line.strip() == '' and i > 0:
                start_index = i + 1
                break
        
        content = '\n'.join(lines[start_index:])
        
        segments = []
        blocks = content.strip().split('\n\n')
        print(f"Found {len(blocks)} blocks in VTT file")
        
        for i, block in enumerate(blocks):
            lines = block.strip().split('\n')
            
            if len(lines) < 2:
                print(f"Warning: Block {i} has less than 2 lines, skipping")
                continue
                
            timestamp_line = None
            for line in lines:
                if ' --> ' in line:
                    timestamp_line = line
                    break
            
            if not timestamp_line:
                print(f"Warning: Block {i} has no timestamp line, skipping")
                continue
                
            try:
                time_parts = timestamp_line.split(' --> ')
                start_time = time_parts[0].strip()
                end_time = time_parts[1].strip().split(' ')[0]
                
                text_start_index = lines.index(timestamp_line) + 1
                text = ' '.join(lines[text_start_index:])
                
                if text:
                    segments.append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'text': text
                    })
                else:
                    print(f"Warning: Block {i} has empty text, skipping")
            except Exception as e:
                print(f"Error parsing block {i}: {e}")
        
        print(f"Successfully parsed {len(segments)} segments from VTT file")
        return segments
    except Exception as e:
        print(f"Error parsing VTT file: {e}")
        return []

def chunk_transcript(segments, max_chunk_size=8000):
    """
    Split transcript into chunks suitable for API processing
    
    Args:
        segments: List of subtitle segments containing timestamps and text
        max_chunk_size: Maximum character count for each chunk
        
    Returns:
        List of chunked text
    """
    print(f"Starting to chunk transcript with {len(segments)} segments")
    
    if not segments:
        print("Warning: No segments provided to chunk_transcript function")
        return []
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for i, segment in enumerate(segments):
        # Ensure text is not None
        if 'text' not in segment or segment['text'] is None:
            print(f"Warning: Segment {i} has no text or text is None")
            segment['text'] = ""
            
        segment_size = len(segment['text'])
        
        if current_size + segment_size > max_chunk_size and current_chunk:
            # Save current chunk and start new chunk
            start_time = current_chunk[0]['start_time']
            end_time = current_chunk[-1]['end_time']
            text = ' '.join([seg['text'] for seg in current_chunk])
            
            # Only add chunk if it has content
            if text.strip():
                chunks.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'text': text
                })
                print(f"Created chunk {len(chunks)} with {len(current_chunk)} segments, size: {len(text)} chars")
            
            current_chunk = [segment]
            current_size = segment_size
        else:
            current_chunk.append(segment)
            current_size += segment_size
    
    # Add the last chunk
    if current_chunk:
        start_time = current_chunk[0]['start_time']
        end_time = current_chunk[-1]['end_time']
        text = ' '.join([seg['text'] for seg in current_chunk])
        
        # Only add chunk if it has content
        if text.strip():
            chunks.append({
                'start_time': start_time,
                'end_time': end_time,
                'text': text
            })
            print(f"Created final chunk {len(chunks)} with {len(current_chunk)} segments, size: {len(text)} chars")
    
    print(f"Finished chunking transcript into {len(chunks)} chunks")
    return chunks

if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    vtt_file_path = os.path.join(data_dir, 'transcript.en.vtt')
    
    segments = parse_vtt(vtt_file_path)
    
    
    print(f"{len(segments)} segments parsed")
    
    print("\nFirst 5 segments:")
    for i, segment in enumerate(segments[:5]):
        print(f"segment {i+1}:")
        print(f"  Start time: {segment['start_time']}")
        print(f"  End time: {segment['end_time']}")
        print(f"  content: {segment['text']}")
        print()
    
    
    output_json_path = os.path.join(data_dir, 'transcript_parsed.json')
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    
    print(f"Save to: {output_json_path}")