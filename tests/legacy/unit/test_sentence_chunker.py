import pytest
from src.backend.pipeline.chunker import SentenceBoundaryChunker, chunk_token_stream

def test_basic_sentence_splitting():
    chunker = SentenceBoundaryChunker()
    tokens = ["Hello ", "world! ", "How ", "are ", "you ", "today? ", "I ", "am ", "fine."]
    results = []
    for token in tokens:
        sentences = chunker.add_token(token)
        results.extend(sentences)
    remaining = chunker.flush()
    if remaining:
        results.append(remaining)

    assert len(results) == 3
    assert results[0] == "Hello world!"
    assert results[1] == "How are you today?"
    assert results[2] == "I am fine."

def test_abbreviation_and_decimal_protection():
    chunker = SentenceBoundaryChunker()
    tokens = ["The ", "Qwen ", "1.7B ", "model ", "was ", "created ", "by ", "Dr. ", "Smith. ", "It ", "works."]
    results = []
    for token in tokens:
        results.extend(chunker.add_token(token))
    remaining = chunker.flush()
    if remaining:
        results.append(remaining)

    assert len(results) == 2
    assert results[0] == "The Qwen 1.7B model was created by Dr. Smith."
    assert results[1] == "It works."

def test_indic_purna_viram_danda():
    chunker = SentenceBoundaryChunker()
    tokens = ["नमस्ते ", "दोस्तों। ", "यह ", "एक ", "परीक्षण ", "है।"]
    results = []
    for token in tokens:
        results.extend(chunker.add_token(token))
    remaining = chunker.flush()
    if remaining:
        results.append(remaining)

    assert len(results) == 2
    assert results[0] == "नमस्ते दोस्तों।"
    assert results[1] == "यह एक परीक्षण है।"

def test_max_words_fallback_split():
    # Long run-on text with no punctuation
    chunker = SentenceBoundaryChunker(max_words=6, max_chars=50, min_chars=5)
    tokens = ["word1 ", "word2 ", "word3 ", "word4 ", "word5 ", "word6 ", "word7 ", "word8"]
    results = []
    for token in tokens:
        results.extend(chunker.add_token(token))
    remaining = chunker.flush()
    if remaining:
        results.append(remaining)

    # Should have split into at least 2 parts despite no terminal punctuation
    assert len(results) >= 2
    assert "word1" in results[0]

def test_flush_unpunctuated_tail():
    chunker = SentenceBoundaryChunker()
    chunker.add_token("First sentence. ")
    chunker.add_token("Trailing without punctuation")
    
    first_split = chunker.flush()
    assert first_split == "Trailing without punctuation"

@pytest.mark.asyncio
async def test_chunk_token_stream_async():
    async def sample_token_gen():
        for t in ["SenseAI ", "streams ", "audio. ", "Latency ", "is ", "low!"]:
            yield t

    sentences = []
    async for s in chunk_token_stream(sample_token_gen()):
        sentences.append(s)

    assert len(sentences) == 2
    assert sentences[0] == "SenseAI streams audio."
    assert sentences[1] == "Latency is low!"
