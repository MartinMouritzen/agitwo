#!/usr/bin/env python3
"""Voice Lab server — static app + ElevenLabs proxy + take/state management.

Zero dependencies (stdlib only). Run: python3 server.py [port]  (default 3717)

Endpoints:
  GET  /api/state              -> characters (all lines), takes, picks
  GET  /api/voices             -> cached ElevenLabs voice catalog (user + curated)
  GET  /api/voices/refresh     -> re-fetch catalog from ElevenLabs
  GET  /api/quota              -> ElevenLabs subscription usage
  POST /api/generate           -> {charId, lineKey, text, voiceId, stability?, seed?}
                                  generates a take via ElevenLabs, saves mp3, returns take info
  POST /api/pick               -> {charId, voiceId, voiceName} set character's chosen voice
  POST /api/take/select        -> {charId, lineKey, file} mark a take as the keeper
  POST /api/take/delete        -> {charId, lineKey, file} delete a bad take
Static: everything else served from this directory.
"""
import base64, hashlib, json, os, secrets, sys, time, threading, urllib.request, urllib.error, urllib.parse
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
AUDIO = os.path.join(ROOT, "audio")
KEYFILE = os.path.join(ROOT, "..", ".elevenlabs.key")
STATE_LOCK = threading.Lock()

# Three isolated voice packs share this lab. Per-game content + casting state lives under
# data/<game>/ and audio/<game>/; the ElevenLabs/Magnific voice catalog + account slot state are
# shared across all games and stay at the data/ root.
GAMES = {"qfg1"}
SHARED_FILES = {"el_voices.json", "protected_voices.json", "voice_slots.json", "magnific_voices.json"}

def game_of(val):
    g = (val or "qfg1").strip().lower()
    return g if g in GAMES else "qfg1"

def gpath(game, filename):
    """Resolve a data file: shared catalog files at data/, everything else at data/<game>/."""
    if filename in SHARED_FILES:
        return os.path.join(DATA, filename)
    return os.path.join(DATA, game, filename)

def gaudio(game):
    return os.path.join(AUDIO, game)

def safe_id(s):
    """A charId/lineKey used to build a file path — must not escape the game's audio dir."""
    return isinstance(s, str) and bool(s) and "/" not in s and "\\" not in s and ".." not in s

def api_key():
    return open(KEYFILE).read().strip()

def jload(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default

def jsave(p, obj):
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def el_request(path, method="GET", body=None, raw=False, timeout=120):
    req = urllib.request.Request(
        "https://api.elevenlabs.io" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"xi-api-key": api_key(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else json.loads(data)

def fetch_catalog():
    """User's voices + a broad slice of the shared library, cached to data/el_voices.json."""
    voices = []
    seen = set()
    def add(v, source):
        vid = v.get("voice_id")
        if not vid or vid in seen: return
        seen.add(vid)
        labels = v.get("labels") or {}
        # user voices carry metadata in `labels`; shared-library voices carry it top-level
        voices.append({
            "voice_id": vid,
            "public_owner_id": v.get("public_owner_id"),  # needed to (re-)add library voices to a slot
            "name": v.get("name"),
            "category": v.get("category") or source,
            "gender": v.get("gender") or labels.get("gender"),
            "age": v.get("age") or labels.get("age"),
            "accent": v.get("accent") or labels.get("accent"),
            "use": v.get("use_case") or labels.get("use_case") or labels.get("use case"),
            "desc": labels.get("description") or v.get("descriptive") or v.get("description") or "",
            "preview": v.get("preview_url"),
            "source": source,
        })
    mine = el_request("/v1/voices")
    for v in mine.get("voices", []):
        add(v, "mine")
    # shared library: several themed searches to get a useful casting pool
    for term in ["deep", "gravelly", "narrator", "villain", "raspy", "smoky", "sultry",
                 "old", "young", "tough", "warm", "creepy", "robot", "british", "character"]:
        try:
            page = el_request(f"/v1/shared-voices?page_size=30&language=en&search={term}")
            for v in page.get("voices", []):
                add(v, "library")
        except Exception:
            pass
    jsave(os.path.join(DATA, "el_voices.json"), {"fetched": int(time.time()), "voices": voices})
    return voices

# ---------- Magnific MCP direct client (our own OAuth client, no AI in the loop) ----------
MCP_URL = "https://mcp.magnific.com"
AUTH_BASE = "https://auth.magnific.com/realms/mcp/protocol/openid-connect"
CLIENT_FILE = os.path.join(ROOT, "..", ".mcp_client.json")
TOKEN_FILE = os.path.join(ROOT, "..", ".mcp_tokens.json")
MCP_LOCK = threading.Lock()
_pkce = {}          # state -> verifier
_mcp_session = {"id": None}

def client_id():
    return json.load(open(CLIENT_FILE))["client_id"]

def tokens():
    try: return json.load(open(TOKEN_FILE))
    except Exception: return None

def save_tokens(t):
    t["obtained_at"] = int(time.time())
    json.dump(t, open(TOKEN_FILE, "w"))
    os.chmod(TOKEN_FILE, 0o600)

def token_post(data):
    req = urllib.request.Request(AUTH_BASE + "/token",
        data=urllib.parse.urlencode(data).encode(), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def access_token():
    """Valid access token, refreshing when close to expiry. None if never authorized."""
    with MCP_LOCK:
        t = tokens()
        if not t: return None
        if time.time() < t.get("obtained_at", 0) + t.get("expires_in", 300) - 60:
            return t["access_token"]
        try:
            nt = token_post({"grant_type": "refresh_token", "client_id": client_id(),
                             "refresh_token": t["refresh_token"]})
            if "refresh_token" not in nt: nt["refresh_token"] = t["refresh_token"]
            save_tokens(nt)
            _mcp_session["id"] = None  # new token -> fresh MCP session
            return nt["access_token"]
        except Exception as e:
            sys.stderr.write(f"mcp token refresh failed: {e}\n")
            return None

def _mcp_post(body, tok, session=None):
    h = {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream",
         "Authorization": f"Bearer {tok}",
         "MCP-Protocol-Version": "2025-03-26"}
    if session: h["Mcp-Session-Id"] = session
    req = urllib.request.Request(MCP_URL, data=json.dumps(body).encode(), method="POST", headers=h)
    resp = urllib.request.urlopen(req, timeout=120)
    sid = resp.headers.get("Mcp-Session-Id")
    ctype = resp.headers.get("Content-Type", "")
    raw = resp.read().decode("utf-8", "replace")
    if "text/event-stream" in ctype:
        # last data: payload wins (progress events may precede the result)
        payload = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                try: payload = json.loads(line[5:].strip())
                except Exception: pass
        return payload, sid
    return (json.loads(raw) if raw.strip() else None), sid

def mcp_call(tool, arguments):
    """tools/call against Magnific's MCP; returns the parsed inner JSON of the text content."""
    tok = access_token()
    if not tok: raise RuntimeError("Magnific MCP not connected (visit /oauth/login)")
    with MCP_LOCK:
        session = _mcp_session["id"]
    if not session:
        init, sid = _mcp_post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                          "clientInfo": {"name": "srr-voice-lab", "version": "1.0"}}}, tok)
        if init is None or "error" in (init or {}):
            raise RuntimeError(f"MCP initialize failed: {init}")
        session = sid
        with MCP_LOCK:
            _mcp_session["id"] = sid
        try:
            _mcp_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, tok, session)
        except urllib.error.HTTPError:
            pass  # some servers 202/400 on notifications; harmless
    resp, _ = _mcp_post({"jsonrpc": "2.0", "id": int(time.time() * 1000) % 10**9,
                         "method": "tools/call",
                         "params": {"name": tool, "arguments": arguments}}, tok, session)
    if resp is None: raise RuntimeError("empty MCP response")
    if "error" in resp: raise RuntimeError(f"MCP error: {resp['error']}")
    result = resp.get("result", {})
    if result.get("isError"):
        raise RuntimeError(f"tool error: {json.dumps(result)[:400]}")
    # Magnific returns the real payload in structuredContent; content[] carries an
    # instruction reminder AND a JSON block, so never just trust content[0].
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    best = None
    for c in result.get("content", []):
        if c.get("type") == "text":
            try:
                obj = json.loads(c["text"])
                if isinstance(obj, dict) and ("creation" in obj or "results" in obj):
                    return obj
                best = best or obj
            except Exception:
                best = best or {"text": c["text"]}
    return best if best is not None else result

def magnific_generate(text, mag_voice_id, stability):
    """Full TTS round trip through our own MCP session; returns raw mp3 bytes."""
    created = mcp_call("audio_tts", {"text": text, "voiceId": mag_voice_id,
                                     "model": "eleven_v3", "stability": stability, "visible": False})
    ident = (created.get("creation") or {}).get("identifier")
    if not ident: raise RuntimeError(f"no creation id: {json.dumps(created)[:300]}")
    url = None
    for _ in range(20):
        w = mcp_call("creations_wait", {"identifiers": [ident]})
        results = w.get("results") or []
        if results and results[0].get("status") == "completed":
            url = results[0]["results"]["url"]; break
        if results and results[0].get("status") == "failed":
            raise RuntimeError("generation failed on Magnific side")
    if not url: raise RuntimeError("generation timed out")
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()

def touch_slot(vid):
    p = os.path.join(DATA, "voice_slots.json")
    with STATE_LOCK:
        s = jload(p, {})
        s[vid] = int(time.time())
        jsave(p, s)

def ensure_voice(vid):
    """Make sure voice vid is usable for TTS. Auto-add library voices; LRU-evict on slot limit.
    Voices are deterministic and re-addable, so eviction loses nothing (persona lives in our data)."""
    mine = el_request("/v1/voices")
    by_id = {v["voice_id"]: v for v in mine.get("voices", [])}
    # one-time snapshot: voices that were in the account before the lab ever touched it
    # (e.g. the Gateborn cast) are permanently protected from eviction
    pp = os.path.join(DATA, "protected_voices.json")
    protected = jload(pp, None)
    if protected is None:
        protected = [v["voice_id"] for v in mine.get("voices", []) if v.get("category") != "premade"]
        jsave(pp, protected)
    if vid in by_id:
        touch_slot(vid)
        return
    cat = jload(os.path.join(DATA, "el_voices.json"), {"voices": []})
    entry = next((v for v in cat["voices"] if v["voice_id"] == vid), None)
    if not entry or not entry.get("public_owner_id"):
        raise RuntimeError(f"voice {vid} not in account and no library owner known; refresh catalog")
    add_path = f"/v1/voices/add/{entry['public_owner_id']}/{vid}"
    try:
        el_request(add_path, method="POST", body={"new_name": entry.get("name") or vid})
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        if e.code == 400 and ("voice_limit" in detail or "maximum" in detail.lower() or "limit" in detail.lower()):
            # evict least-recently-used non-premade voice, then retry once
            slots = jload(os.path.join(DATA, "voice_slots.json"), {})
            evictable = [v for v in mine.get("voices", [])
                         if v.get("category") != "premade" and v["voice_id"] not in protected]
            if not evictable:
                raise RuntimeError("slot limit reached and nothing evictable")
            evictable.sort(key=lambda v: slots.get(v["voice_id"], 0))
            victim = evictable[0]
            el_request(f"/v1/voices/{victim['voice_id']}", method="DELETE")
            sys.stderr.write(f"slot-manager: evicted '{victim.get('name')}' to make room\n")
            el_request(add_path, method="POST", body={"new_name": entry.get("name") or vid})
        else:
            raise RuntimeError(f"add voice failed ({e.code}): {detail}")
    touch_slot(vid)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        # Data files (line_segments.json, takes, etc.) change under the running lab; never let the
        # browser serve a stale cached copy — otherwise a hard reload still shows old segmentation.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def ingest_mcp_results(self, game):
        """Consume result files written by the Claude MCP worker into takes.json.
        Caller must hold STATE_LOCK. The server is the only writer of takes.json."""
        indir = os.path.join(DATA, game, "mcp_results")
        if not os.path.isdir(indir): return
        files = sorted(os.listdir(indir))
        if not files: return
        takes = jload(gpath(game, "takes.json"), {})
        queue = jload(gpath(game, "mcp_queue.json"), {})
        changed = False
        for fn in files:
            p = os.path.join(indir, fn)
            try:
                r = json.load(open(p))
            except Exception:
                continue
            job = queue.pop(r.get("qid", ""), None)
            if r.get("status") == "ok" and job:
                arr = takes.setdefault(job["charId"], {}).setdefault(job["lineKey"],
                                                                     {"selected": None, "takes": []})
                arr["takes"].append({"file": r["file"], "voiceId": f'mag_{job["magId"]}',
                                     "voiceName": job.get("voiceName") or f'Magnific {job["magId"]}',
                                     "stability": job.get("stability", 0),
                                     "chars": len(job.get("text", "")), "ts": r.get("ts") or int(time.time())})
                if arr["selected"] is None:
                    arr["selected"] = r["file"]
            os.remove(p)
            changed = True
        if changed:
            jsave(gpath(game, "takes.json"), takes)
            jsave(gpath(game, "mcp_queue.json"), queue)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def run_sync(self, game="dms"):
        # Export current takes -> voicepack and install into the game (game restart still needed).
        # Reachable via GET and POST so a cached lab can't hit a method mismatch.
        import subprocess
        script = os.path.join(ROOT, "..", "tools", "sync_to_game.sh")
        try:
            r = subprocess.run(["bash", script, game], capture_output=True, text=True, timeout=600)
            out = (r.stdout + "\n" + r.stderr).strip()
            status = ""
            for line in out.splitlines():
                if "SYNCED" in line or "NOT FOUND" in line:
                    status = line.strip()
            ok = r.returncode == 0 and "SYNCED" in out
            return self.send_json({"ok": ok, "message": status or (out.splitlines()[-1] if out else ""),
                                   "log": out[-2000:]})
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()  # end_headers() adds Cache-Control: no-store for every response
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        game = game_of((qs.get("game") or ["qfg1"])[0])
        if path == "/api/sync":
            return self.run_sync(game)
        if path == "/api/state":
            with STATE_LOCK:
                self.ingest_mcp_results(game)
                chars = jload(gpath(game, "characters.json"), {})
                takes = jload(gpath(game, "takes.json"), {})
                picks = jload(gpath(game, "picks.json"), {})
                edits = jload(gpath(game, "text_edits.json"), {})
                queue = jload(gpath(game, "mcp_queue.json"), {})
            return self.send_json({"game": game, "characters": chars, "takes": takes, "picks": picks,
                                   "edits": edits, "queue": queue,
                                   "mcpConnected": bool(tokens())})
        if path == "/api/voices":
            c = jload(os.path.join(DATA, "el_voices.json"), None)
            if not c:
                try:
                    c = {"fetched": int(time.time()), "voices": fetch_catalog()}
                except Exception as e:
                    return self.send_json({"error": str(e)}, 502)
            return self.send_json(c)
        if path == "/api/voices/refresh":
            try:
                return self.send_json({"voices": fetch_catalog()})
            except Exception as e:
                return self.send_json({"error": str(e)}, 502)
        if path == "/oauth/login":
            verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            state = secrets.token_urlsafe(16)
            _pkce[state] = verifier
            port = self.server.server_address[1]
            q = urllib.parse.urlencode({
                "client_id": client_id(), "response_type": "code",
                "redirect_uri": f"http://localhost:{port}/oauth/callback",
                "scope": "openid profile email mcp:custom-audience offline_access",
                "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
            self.send_response(302)
            self.send_header("Location", AUTH_BASE + "/auth?" + q)
            self.end_headers()
            return
        if self.path.startswith("/oauth/callback"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            state = (qs.get("state") or [""])[0]
            code = (qs.get("code") or [""])[0]
            verifier = _pkce.pop(state, None)
            if not (code and verifier):
                return self.send_json({"error": "bad oauth callback"}, 400)
            port = self.server.server_address[1]
            try:
                t = token_post({"grant_type": "authorization_code", "client_id": client_id(),
                                "code": code, "code_verifier": verifier,
                                "redirect_uri": f"http://localhost:{port}/oauth/callback"})
                save_tokens(t)
            except urllib.error.HTTPError as e:
                return self.send_json({"error": f"token exchange failed: {e.read().decode()[:300]}"}, 502)
            self.send_response(302)
            self.send_header("Location", "/lab.html")
            self.end_headers()
            return
        if path == "/api/quota":
            try:
                u = el_request("/v1/user")
                s = u.get("subscription", {})
                return self.send_json({"tier": s.get("tier"),
                                       "used": s.get("character_count"),
                                       "limit": s.get("character_limit"),
                                       "reset_unix": s.get("next_character_count_reset_unix")})
            except Exception as e:
                return self.send_json({"error": str(e)}, 502)
        return super().do_GET()

    def do_POST(self):
        try:
            body = self.read_body()
        except Exception:
            return self.send_json({"error": "bad json"}, 400)
        game = game_of(body.get("game"))

        if self.path == "/api/generate":
            cid = body.get("charId"); key = body.get("lineKey")
            text = (body.get("text") or "").strip()
            vid = body.get("voiceId")
            stability = body.get("stability", 0.0)
            if not (cid and key and text and vid):
                return self.send_json({"error": "charId, lineKey, text, voiceId required"}, 400)
            if not (safe_id(cid) and safe_id(key)):
                return self.send_json({"error": "invalid charId/lineKey"}, 400)
            if str(vid).startswith("mag_"):
                mag_id = int(str(vid)[4:])
                # direct path ONLY — our own MCP client. No queue, no AI in the loop.
                # If it fails, it fails loudly so we fix the real problem.
                if not tokens():
                    return self.send_json({"error": "Magnific not connected — click 'Connect Magnific' first"}, 401)
                try:
                    audio = magnific_generate(text, mag_id, stability)
                except Exception as e:
                    return self.send_json({"error": f"Magnific generation failed: {e}"}, 502)
                ts = int(time.time())
                d = os.path.join(gaudio(game), cid, "takes")
                os.makedirs(d, exist_ok=True)
                fname = f"{key}__mag{mag_id}__{ts}.mp3"
                with open(os.path.join(d, fname), "wb") as f:
                    f.write(audio)
                rel = f"{cid}/takes/{fname}"
                with STATE_LOCK:
                    takes = jload(gpath(game, "takes.json"), {})
                    arr = takes.setdefault(cid, {}).setdefault(key, {"selected": None, "takes": []})
                    arr["takes"].append({"file": rel, "voiceId": f"mag_{mag_id}",
                                         "voiceName": body.get("voiceName") or f"Magnific {mag_id}",
                                         "stability": stability, "chars": len(text), "ts": ts})
                    if arr["selected"] is None: arr["selected"] = rel
                    jsave(gpath(game, "takes.json"), takes)
                return self.send_json({"ok": True, "file": rel})
            payload = {
                "text": text,
                "model_id": "eleven_v3",
                "voice_settings": {"stability": stability, "use_speaker_boost": True},
            }
            try:
                ensure_voice(vid)
            except Exception as e:
                return self.send_json({"error": f"slot manager: {e}"}, 502)
            try:
                audio = el_request(f"/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                                   method="POST", body=payload, raw=True)
            except urllib.error.HTTPError as e:
                return self.send_json({"error": f"ElevenLabs {e.code}: {e.read().decode()[:400]}"}, 502)
            except Exception as e:
                return self.send_json({"error": str(e)}, 502)
            ts = int(time.time())
            d = os.path.join(gaudio(game), cid, "takes")
            os.makedirs(d, exist_ok=True)
            fname = f"{key}__{vid[:12]}__{ts}.mp3"
            with open(os.path.join(d, fname), "wb") as f:
                f.write(audio)
            rel = f"{cid}/takes/{fname}"
            with STATE_LOCK:
                takes = jload(gpath(game, "takes.json"), {})
                arr = takes.setdefault(cid, {}).setdefault(key, {"selected": None, "takes": []})
                arr["takes"].append({"file": rel, "voiceId": vid,
                                     "voiceName": body.get("voiceName") or vid[:8],
                                     "stability": stability, "chars": len(text), "ts": ts})
                if arr["selected"] is None:
                    arr["selected"] = rel
                jsave(gpath(game, "takes.json"), takes)
            return self.send_json({"ok": True, "file": rel})

        if self.path == "/api/text/set":
            key = body.get("key"); text = (body.get("text") or "").strip()
            if not key:
                return self.send_json({"error": "key required"}, 400)
            with STATE_LOCK:
                p = gpath(game, "text_edits.json")
                edits = jload(p, {})
                if text:
                    edits[key] = text
                else:
                    edits.pop(key, None)   # empty = reset to default
                jsave(p, edits)
            return self.send_json({"ok": True})

        if self.path == "/api/sync":
            return self.run_sync(game)

        if self.path == "/api/pick":
            with STATE_LOCK:
                picks = jload(gpath(game, "picks.json"), {})
                picks[body["charId"]] = {"voiceId": body.get("voiceId"),
                                         "voiceName": body.get("voiceName")}
                jsave(gpath(game, "picks.json"), picks)
            return self.send_json({"ok": True})

        if self.path == "/api/bark/pick":
            # Assign a voice to a combat-bark SPEAKER (applies to all that speaker's barks).
            with STATE_LOCK:
                bp = jload(gpath(game, "bark_picks.json"), {})
                bp[body["speaker"]] = {"voiceId": body.get("voiceId"),
                                       "voiceName": body.get("voiceName")}
                jsave(gpath(game, "bark_picks.json"), bp)
            return self.send_json({"ok": True})

        if self.path == "/api/seg/setvoice":
            # Per-LINE voice override for a character segment (wins over the character's pick).
            # Lets a mis-bucketed bucket (e.g. "Player Character 1") voice different lines differently.
            with STATE_LOCK:
                ov = jload(gpath(game, "seg_overrides.json"), {})
                if body.get("voiceId"):
                    ov[body["segKey"]] = {"voiceId": body["voiceId"], "voiceName": body.get("voiceName")}
                else:
                    ov.pop(body["segKey"], None)
                jsave(gpath(game, "seg_overrides.json"), ov)
            return self.send_json({"ok": True})

        if self.path == "/api/bark/setvoice":
            # Per-bark voice override (wins over the speaker voice). Pass voiceId=null to clear.
            with STATE_LOCK:
                ov = jload(gpath(game, "bark_overrides.json"), {})
                if body.get("voiceId"):
                    ov[body["barkKey"]] = {"voiceId": body["voiceId"], "voiceName": body.get("voiceName")}
                else:
                    ov.pop(body["barkKey"], None)
                jsave(gpath(game, "bark_overrides.json"), ov)
            return self.send_json({"ok": True})

        if self.path == "/api/take/select":
            with STATE_LOCK:
                takes = jload(gpath(game, "takes.json"), {})
                e = takes.get(body["charId"], {}).get(body["lineKey"])
                if e: e["selected"] = body["file"]
                jsave(gpath(game, "takes.json"), takes)
            return self.send_json({"ok": True})

        if self.path == "/api/take/delete":
            with STATE_LOCK:
                takes = jload(gpath(game, "takes.json"), {})
                e = takes.get(body["charId"], {}).get(body["lineKey"])
                if e:
                    e["takes"] = [t for t in e["takes"] if t["file"] != body["file"]]
                    if e["selected"] == body["file"]:
                        e["selected"] = e["takes"][-1]["file"] if e["takes"] else None
                    jsave(gpath(game, "takes.json"), takes)
                gadir = gaudio(game)
                p = os.path.join(gadir, *body["file"].split("/"))
                if os.path.abspath(p).startswith(os.path.abspath(gadir)) and os.path.exists(p):
                    os.remove(p)
            return self.send_json({"ok": True})

        return self.send_json({"error": "unknown endpoint"}, 404)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3717
    print(f"Voice Lab: http://localhost:{port}/lab.html")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
