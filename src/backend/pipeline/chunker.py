"""
Sentence Boundary Chunker for Streaming Voice Assistant Pipeline.
Splits incoming LLM token stream into natural sentence units suitable for
real-time TTS speech synthesis.
"""
import re
import logging
from typing import List, Optional, AsyncGenerator

logger = logging.getLogger(__name__)

# Common abbreviations to avoid splitting on
COMMON_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "e.g.", "i.e.", "vs.", "etc.", "approx.", "dept.", "est."
}

class SentenceBoundaryChunker:
    """
    Buffers incremental token deltas from an LLM and emits complete sentences
    as soon as a sentence boundary is identified.

    Rules:
    - Splits on '.', '!', '?', '\n', and Hindi purna viram '।' (danda).
    - Avoids splitting on decimal numbers (e.g., '1.7B', '3.14') or common abbreviations ('e.g.', 'Dr.').
    - Fallback: Emits chunk if buffer exceeds max_words or max_chars even without terminal punctuation.
    """
    def __init__(self, max_words: int = 25, max_chars: int = 150, min_chars: int = 6):
        self.max_words = max_words
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.buffer = ""

    def add_token(self, token: str) -> List[str]:
        """
        Appends a token delta to the internal buffer and returns any completed sentences.
        """
        self.buffer += token
        sentences = []

        while True:
            split_idx = self._find_sentence_split(self.buffer)
            if split_idx is None:
                # Check max word / char fallback
                words = self.buffer.split()
                if len(words) >= self.max_words or len(self.buffer) >= self.max_chars:
                    # Find a safe break point (last space or comma)
                    fallback_idx = self._find_fallback_split(self.buffer)
                    if fallback_idx is not None and fallback_idx >= self.min_chars:
                        sentence = self.buffer[:fallback_idx].strip()
                        self.buffer = self.buffer[fallback_idx:].lstrip()
                        if sentence:
                            sentences.append(sentence)
                        continue
                break

            sentence = self.buffer[:split_idx].strip()
            self.buffer = self.buffer[split_idx:].lstrip()
            if sentence:
                sentences.append(sentence)

        return sentences

    def _find_sentence_split(self, text: str) -> Optional[int]:
        """
        Finds the end index of the first complete sentence in `text`.
        Returns index immediately after the terminal punctuation, or None.
        """
        # Match terminal punctuation: ., !, ?, \n, or Devanagari danda । followed by space or end-of-string
        pattern = re.compile(r'([.!?\n।])(\s+|$)', re.UNICODE)
        for match in pattern.finditer(text):
            punct = match.group(1)
            punct_end = match.end(1)
            candidate = text[:punct_end].strip()

            # Rule 1: Minimum character threshold
            if len(candidate) < self.min_chars:
                continue

            # Rule 2: If newline or exclamation or question or Hindi danda, always valid split
            if punct in ('\n', '!', '?', '।'):
                return punct_end

            # Rule 3: For period ('.'), check decimal number or abbreviation
            if punct == '.':
                # Check decimal number e.g. 1.7
                preceding = text[:match.start(1)]
                succeeding = text[match.end(1):]
                if preceding and preceding[-1].isdigit() and succeeding and succeeding[0].isdigit():
                    continue

                # Check abbreviation
                last_word = preceding.split()[-1].lower() + "." if preceding.split() else ""
                if last_word in COMMON_ABBREVIATIONS:
                    continue

                return punct_end

        return None

    def _find_fallback_split(self, text: str) -> Optional[int]:
        """
        Finds a safe word/clause break index when buffer exceeds maximum length.
        Prefers comma, semicolon, colon, or last space.
        """
        for delim in (', ', '; ', ': ', ' '):
            idx = text.rfind(delim)
            if idx > self.min_chars:
                return idx + len(delim)
        return len(text)

    def flush(self) -> Optional[str]:
        """
        Flushes and returns whatever remains in the buffer.
        """
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining if remaining else None


async def chunk_token_stream(
    token_generator: AsyncGenerator[str, None],
    chunker: Optional[SentenceBoundaryChunker] = None
) -> AsyncGenerator[str, None]:
    """
    Wraps an async token generator and yields complete sentences as they are identified.
    """
    if chunker is None:
        chunker = SentenceBoundaryChunker()

    async for token in token_generator:
        sentences = chunker.add_token(token)
        for s in sentences:
            if s:
                yield s

    remaining = chunker.flush()
    if remaining:
        yield remaining
