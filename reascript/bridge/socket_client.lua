--[[
  ReaSig — bridge/socket_client.lua
  Non-blocking TCP client for communication with the ReaSig daemon.

  Design:
  - State machine: DISCONNECTED → CONNECTING → CONNECTED → DISCONNECTED
  - FIFO send queue: oldest message sent first, never blocks
  - Receive buffer: accumulates bytes across frames, dispatches complete JSON lines
  - All socket errors transition to DISCONNECTED; caller calls reconnect() to retry.

  Requires: Mavriq LuaSockets (installed via ReaPack)
            lib/dkjson  (bundled at reascript/lib/dkjson.lua)
--]]

local M          = {}

local socket     = require("socket")
local json       = require("lib/dkjson")

-- ── Configuration ──────────────────────────────────────────────────────────
local HOST       = "127.0.0.1"
local PORT       = 9876
local MAX_Q      = 64 -- max pending messages before oldest is dropped

-- ── Module state ──────────────────────────────────────────────────────────
local _sock      = nil
local _state     = "DISCONNECTED" -- "DISCONNECTED" | "CONNECTING" | "CONNECTED"
local _send_q    = {}             -- FIFO: [1] = oldest, [#] = newest
local _recv_buf  = ""
local _on_msg_cb = nil            -- function(msg_table) — set by caller
local _last_ping = 0              -- track last ping time

-- ── Internal helpers ───────────────────────────────────────────────────────

local function _close()
  if _sock then
    pcall(function() _sock:close() end)
    _sock = nil
  end
  _state = "DISCONNECTED"
end

local function _dispatch_buffer()
  -- Extract and dispatch every complete newline-terminated message
  while true do
    local nl = _recv_buf:find("\n", 1, true) -- plain search, not pattern
    if not nl then break end

    local line = _recv_buf:sub(1, nl - 1)
    _recv_buf  = _recv_buf:sub(nl + 1)

    line       = line:match("^%s*(.-)%s*$") -- trim whitespace
    if line ~= "" then
      local ok, msg = pcall(json.decode, line)
      if ok and msg then
        if _on_msg_cb then _on_msg_cb(msg) end
      else
        reaper.ShowConsoleMsg("[ReaSig] JSON parse error on line: " .. line:sub(1, 80) .. "\n")
      end
    end
  end
end

-- ── Public API ─────────────────────────────────────────────────────────────

---Attempt to connect to the daemon. Non-blocking — actual connection is confirmed
---on the first successful send/receive (state becomes "CONNECTED" then).
function M.connect()
  if _state ~= "DISCONNECTED" then return end
  _sock = socket.tcp()
  _sock:settimeout(0) -- non-blocking mode

  -- connect() on a non-blocking socket returns immediately.
  -- The error "timeout" here means "in progress" — that's fine.
  local ok, err = _sock:connect(HOST, PORT)
  if ok or err == "timeout" or err == "Operation already in progress" then
    _state = "CONNECTING"
  else
    -- Immediate failure (e.g. connection refused, daemon not running)
    _close()
  end
end

---Attempt to reconnect after a disconnect.
function M.reconnect()
  _close()
  _recv_buf = ""
  _send_q   = {}
  M.connect()
end

---Register callback for incoming daemon messages. Called with a decoded Lua table.
---@param cb function  function(msg_table)
function M.on_message(cb)
  _on_msg_cb = cb
end

---Send a keep-alive ping, bypassing the send queue.
function M.ping()
  if _state ~= "CONNECTED" then return end
  local line = json.encode({ type = "status", id = "ping" }) .. "\n"
  table.insert(_send_q, 1, line)
end

---Enqueue a message to be sent to the daemon. msg_table is a Lua table that
---will be JSON-encoded and sent as a newline-terminated line.
---@param msg_table table
function M.send(msg_table)
  local line = json.encode(msg_table) .. "\n"
  -- Enforce queue cap — drop oldest if full
  if #_send_q >= MAX_Q then
    table.remove(_send_q, 1)
    reaper.ShowConsoleMsg("[ReaSig] Send queue full — dropping oldest message\n")
  end
  table.insert(_send_q, line)
end

---Must be called every defer frame. Handles all I/O without blocking.
function M.tick()
  if _state == "DISCONNECTED" then return end

  -- ── Keep-alive ping (every 5 seconds) ──────────────────────────────────
  local now = reaper.time_precise()
  if now - _last_ping > 5.0 then
    M.ping()
    _last_ping = now
  end

  -- ── Flush send queue (FIFO: index 1 = oldest) ────────────────────────
  while #_send_q > 0 do
    local ok, err, _ = _sock:send(_send_q[1])
    if ok then
      table.remove(_send_q, 1) -- sent: remove and try next in same frame
      if _state == "CONNECTING" then
        _state = "CONNECTED"   -- confirmed live on first successful send
      end
    elseif err == "timeout" then
      break -- socket buffer full — retry next frame
    else
      -- Real error: connection dropped
      reaper.ShowConsoleMsg("[ReaSig] Send error: " .. tostring(err) .. "\n")
      _close()
      return
    end
  end

  -- ── Receive ───────────────────────────────────────────────────────────
  local data, err, partial = _sock:receive(65536)
  local chunk = data or partial
  if chunk and chunk ~= "" then
    _state    = "CONNECTED" -- confirmed live on first successful receive
    _recv_buf = _recv_buf .. chunk
    _dispatch_buffer()
  end

  if err == "closed" then
    reaper.ShowConsoleMsg("[ReaSig] Connection lost: " .. tostring(err) .. "\n")
    _close()
  elseif err ~= "timeout" and err ~= nil then
    reaper.ShowConsoleMsg("[ReaSig] Connection error: " .. tostring(err) .. "\n")
    _close()
  end
end

---@return boolean true if connection is confirmed established
function M.is_connected()
  return _state == "CONNECTED"
end

---@return string  "DISCONNECTED" | "CONNECTING" | "CONNECTED"
function M.state()
  return _state
end

return M
