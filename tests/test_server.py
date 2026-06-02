"""
Tests for the ReaSig Daemon protocol and TCP server.
"""

import pytest
import asyncio
from daemon.protocol import Message, MessageType, status_request, analyze_track_request
from daemon.server import ReaSigServer
from daemon.config import Config

# --- Protocol Tests ---
def test_message_serialization():
    # Create a message
    msg = Message(type=MessageType.STATUS, payload={"foo": "bar"}, id="test-123")
    
    # Serialize to JSON lines
    json_str = msg.to_json()
    assert json_str.endswith("\n")
    
    # Parse back
    parsed = Message.from_json(json_str)
    assert parsed.type == MessageType.STATUS
    assert parsed.payload == {"foo": "bar"}
    assert parsed.id == "test-123"

def test_message_from_bytes():
    raw = b'{"type": "chat", "id": "msg1", "payload": {"user_message": "hello"}}\n'
    msg = Message.from_bytes(raw)
    assert msg.type == MessageType.CHAT
    assert msg.payload["user_message"] == "hello"
    assert msg.id == "msg1"


# --- Server Integration Tests ---
@pytest.fixture
def test_config(tmp_path):
    return Config(
        openrouter_api_key="test_key",
        model="test-model",
        host="127.0.0.1",
        port=0, # OS assigned ephemeral port
        temp_dir=tmp_path,
        project_root=tmp_path
    )

@pytest.mark.asyncio
async def test_server_status_ping(test_config):
    server = ReaSigServer(test_config)
    
    # Start the server as a background task
    server_task = asyncio.create_task(server.serve_forever())
    
    # Wait for the server to actually bind a port
    await asyncio.sleep(0.1)
    
    # Get the assigned port
    assert server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    
    # Connect client
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    
    try:
        # Send a status request
        req = status_request()
        writer.write(req.to_bytes())
        await writer.drain()
        
        # Read the response
        line = await reader.readline()
        resp = Message.from_bytes(line)
        
        assert resp.type == MessageType.STATUS_OK
        assert resp.id == req.id
        assert resp.payload["status"] == "ok"
    finally:
        writer.close()
        await writer.wait_closed()
        await server.shutdown()
        server_task.cancel()


@pytest.mark.asyncio
async def test_server_analyze_with_fake_handlers(test_config):
    server = ReaSigServer(test_config)
    
    # Inject fake DSP handler
    def fake_analyze(wav_path, user_question, stereo):
        return {"test_dsp_key": 42}
    server.analyze_handler = fake_analyze
    
    # Inject fake LLM handler
    async def fake_llm(request_id, analysis, track_metadata, user_question, conversation_history, send_fn, is_multi_track=False):
        # The llm handler is responsible for sending chunks and the done message
        from daemon.protocol import response_chunk, response_done
        await send_fn(response_chunk(request_id, "chunk 1 "))
        await send_fn(response_chunk(request_id, "chunk 2"))
        await send_fn(response_done(request_id, "chunk 1 chunk 2"))
        return "chunk 1 chunk 2"
    server.llm_handler = fake_llm
    
    server_task = asyncio.create_task(server.serve_forever())
    await asyncio.sleep(0.1)
    
    assert server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    
    try:
        # Send analyze request
        req = analyze_track_request("/fake/path.wav", {"name": "test"}, "what is this?")
        writer.write(req.to_bytes())
        await writer.drain()
        
        # Read chunk 1
        line1 = await reader.readline()
        resp1 = Message.from_bytes(line1)
        assert resp1.type == MessageType.RESPONSE_CHUNK
        assert resp1.payload["content"] == "chunk 1 "
        
        # Read chunk 2
        line2 = await reader.readline()
        resp2 = Message.from_bytes(line2)
        assert resp2.type == MessageType.RESPONSE_CHUNK
        assert resp2.payload["content"] == "chunk 2"
        
        # Read done
        line3 = await reader.readline()
        resp3 = Message.from_bytes(line3)
        assert resp3.type == MessageType.RESPONSE_DONE
        assert resp3.payload["full_response"] == "chunk 1 chunk 2"
        
    finally:
        writer.close()
        await writer.wait_closed()
        await server.shutdown()
        server_task.cancel()
