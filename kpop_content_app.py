#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K-pop 아티스트 브랜딩 콘텐츠 자동 생성기
@마군입니다 스타일 YouTube 콘텐츠 제작 자동화
"""
import io, sys, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, render_template_string, request, jsonify, send_file
import anthropic

app = Flask(__name__)

# .env 파일에서 API 키 로드
def load_api_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """당신은 @마군입니다 유튜브 채널 스타일의 K-pop 아티스트 브랜딩 콘텐츠 전문가입니다.

## @마군입니다 채널 스타일 특징:
- **제목 패턴**: 아티스트명을 앞에 배치 + 강렬한 후킹 키워드 (예: "aespa가 SM에서 살아남는 법", "뉴진스 브랜드 해체 분석")
- **콘텐츠 톤**: 날카로운 분석 + 팬심이 느껴지는 온기 공존, 마케팅/브랜딩 관점에서 아티스트를 해석
- **구성 방식**: 훅(충격적 사실/질문) → 배경 → 핵심 분석 → 사례 → 결론/전망
- **언어 스타일**: 전문 용어와 친근한 구어체 혼합, 짧고 임팩트 있는 문장, "~입니다" 체
- **썸네일 개념**: 아티스트 강렬한 표정 or 무대 컷 + 핵심 키워드 텍스트 (2-3단어, 큰 폰트)
- **댓글 유도**: 논쟁을 유발하는 마지막 질문, 시청자 의견을 구하는 열린 결말

## 콘텐츠 유형별 특징:
1. **브랜딩 분석**: "왜 이 아티스트가 성공했는가" - 전략적 시각
2. **이미지 전략**: 컨셉, 비주얼 아이덴티티, 세계관 분석
3. **위기/논란 분석**: 브랜드 위기를 어떻게 극복했는가
4. **vs 비교**: 두 아티스트의 전략 비교
5. **미래 전망**: 다음 컨셉 예측, 성장 가능성

출력은 반드시 JSON 형식으로 제공하세요."""

CONTENT_PROMPT = """다음 소재로 @마군입니다 스타일의 YouTube 콘텐츠를 생성해주세요.

**아티스트/주제**: {topic}
**콘텐츠 유형**: {content_type}
**추가 맥락**: {context}

다음 JSON 형식으로 정확히 출력하세요:
{{
  "titles": [
    "제목 옵션 1 (아티스트명 앞배치, 강한 훅)",
    "제목 옵션 2 (질문형)",
    "제목 옵션 3 (숫자/리스트형)"
  ],
  "thumbnail": {{
    "main_image_concept": "썸네일 이미지 설명",
    "text_overlay": "썸네일 텍스트 (2-4단어)",
    "color_mood": "색감/분위기 설명",
    "layout": "레이아웃 설명"
  }},
  "hook": "영상 첫 15초 후킹 멘트",
  "script_outline": [
    {{"section": "인트로 (0~30초)", "content": "내용"}},
    {{"section": "배경/문제 제기 (30초~2분)", "content": "내용"}},
    {{"section": "핵심 분석 1 (2~5분)", "content": "내용"}},
    {{"section": "핵심 분석 2 (5~8분)", "content": "내용"}},
    {{"section": "사례/증거 (8~11분)", "content": "내용"}},
    {{"section": "결론/전망 (11~13분)", "content": "내용"}},
    {{"section": "아웃트로 (13~14분)", "content": "댓글 유도 질문 포함"}}
  ],
  "full_script_intro": "실제 스크립트 인트로 ~ 배경 부분 전문 (약 300-400자)",
  "description": "YouTube 설명란 텍스트 (SEO 최적화, 500자 이내)",
  "tags": ["태그1","태그2","태그3","태그4","태그5","태그6","태그7","태그8","태그9","태그10"],
  "engagement_question": "영상 마지막 댓글 유도 질문",
  "posting_tips": ["업로드 팁1", "업로드 팁2", "업로드 팁3"]
}}"""


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>K-pop 브랜딩 스튜디오</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0f;--surface:#13131a;--surface2:#1a1a24;--border:#2a2a3a;
  --accent:#b388ff;--accent2:#ea80fc;--text:#e8e8f0;--muted:#7a7a9a;
  --success:#69f0ae;--shadow:0 4px 24px rgba(0,0,0,.4)
}
body{background:var(--bg);color:var(--text);font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;min-height:100vh}
header{background:linear-gradient(135deg,#1a0a2e,#0d1117);border-bottom:1px solid var(--border);padding:18px 28px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:22px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{color:var(--muted);font-size:12px;margin-top:3px}
.key-status{font-size:12px;padding:4px 12px;border-radius:12px;font-weight:600}
.key-ok{background:rgba(105,240,174,.15);color:var(--success)}
.key-none{background:rgba(255,82,82,.15);color:#ff5252}

.wrap{max-width:1100px;margin:0 auto;padding:28px}

.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:28px;margin-bottom:24px;box-shadow:var(--shadow)}
.card h2{font-size:16px;font-weight:700;margin-bottom:20px;display:flex;align-items:center;gap:8px}
.card h2::before{content:'✦';color:var(--accent)}

.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.full{grid-column:1/-1}
.fg{display:flex;flex-direction:column;gap:7px}
label{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
input,textarea,select{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:11px 14px;color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:border-color .2s,box-shadow .2s;width:100%}
input:focus,textarea:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(179,136,255,.12)}
textarea{resize:vertical;min-height:75px}
select option{background:var(--surface2)}

.btn{width:100%;margin-top:20px;padding:15px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:11px;color:#000;font-size:15px;font-weight:800;cursor:pointer;transition:opacity .2s,transform .1s}
.btn:hover{opacity:.9;transform:translateY(-1px)}
.btn:disabled{opacity:.45;cursor:not-allowed;transform:none}

.loading{display:none;text-align:center;padding:36px;color:var(--muted)}
.loading.on{display:block}
.spin{width:38px;height:38px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:sp .8s linear infinite;margin:0 auto 14px}
@keyframes sp{to{transform:rotate(360deg)}}

.result{display:none}
.result.on{display:block}
.rg{display:grid;grid-template-columns:1fr 1fr;gap:18px}

.rc{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:22px;box-shadow:var(--shadow)}
.rc.full{grid-column:1/-1}
.rc h3{font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}

.title-opt{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:13px 15px;margin-bottom:9px;cursor:pointer;display:flex;align-items:flex-start;gap:11px;transition:border-color .2s,background .2s}
.title-opt:hover{border-color:var(--accent);background:rgba(179,136,255,.05)}
.title-opt:last-child{margin-bottom:0}
.tnum{color:var(--accent);font-weight:800;font-size:11px;min-width:18px;margin-top:3px}
.ttxt{font-size:14px;font-weight:600;line-height:1.5}

.copy{background:transparent;border:1px solid var(--border);border-radius:7px;color:var(--muted);font-size:11px;padding:3px 9px;cursor:pointer;transition:all .2s}
.copy:hover{border-color:var(--accent);color:var(--accent)}

.tbox{background:var(--surface2);border-radius:10px;padding:17px;border:1px solid var(--border)}
.tlabel{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}
.tval{font-size:13px;line-height:1.6;margin-bottom:12px}
.tval:last-child{margin-bottom:0}
.toverlay{font-size:20px;font-weight:900;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}

.hook{background:linear-gradient(135deg,rgba(179,136,255,.1),rgba(234,128,252,.05));border:1px solid rgba(179,136,255,.3);border-radius:10px;padding:18px;font-size:15px;font-weight:600;line-height:1.7;font-style:italic}

.oi{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--border)}
.oi:last-child{border-bottom:none}
.otime{min-width:120px;font-size:10px;color:var(--accent);font-weight:700;text-transform:uppercase;padding-top:2px}
.ocont{font-size:13px;line-height:1.6}

.prebox{background:var(--surface2);border-radius:10px;padding:18px;font-size:13px;line-height:1.9;border:1px solid var(--border);white-space:pre-wrap;word-break:keep-all}

.tags{display:flex;flex-wrap:wrap;gap:7px}
.tag{background:rgba(179,136,255,.12);border:1px solid rgba(179,136,255,.25);color:var(--accent);padding:5px 13px;border-radius:20px;font-size:12px;font-weight:600}

.tiplist{list-style:none}
.tiplist li{padding:9px 0;border-bottom:1px solid var(--border);font-size:13px;line-height:1.6;display:flex;gap:9px}
.tiplist li::before{content:'→';color:var(--accent2);font-weight:700}
.tiplist li:last-child{border-bottom:none}

.engage{background:linear-gradient(135deg,rgba(234,128,252,.1),rgba(179,136,255,.05));border:1px solid rgba(234,128,252,.3);border-radius:10px;padding:18px;font-size:15px;font-weight:600;line-height:1.7;text-align:center}

.err{background:rgba(255,82,82,.1);border:1px solid rgba(255,82,82,.3);border-radius:10px;padding:16px;color:#ff5252;font-size:13px;margin-bottom:20px;display:none}
.err.on{display:block}

.dl-bar{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}
.dlbtn{padding:10px 20px;border-radius:9px;font-size:13px;font-weight:700;cursor:pointer;border:none;transition:opacity .2s}
.dlbtn:hover{opacity:.85}
.dl-txt{background:var(--surface2);border:1px solid var(--border);color:var(--text)}
.dl-md{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#000}

.notice{background:rgba(179,136,255,.08);border:1px solid rgba(179,136,255,.2);border-radius:10px;padding:14px 18px;font-size:13px;color:var(--muted);margin-bottom:20px;display:none}
.notice.on{display:block}
.notice a{color:var(--accent);text-decoration:none}
.notice a:hover{text-decoration:underline}

@media(max-width:700px){.grid2,.rg{grid-template-columns:1fr}.rc.full,.full{grid-column:1}}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">✦ K-pop 브랜딩 스튜디오</div>
    <div class="sub">@마군입니다 스타일 유튜브 콘텐츠 자동 생성기</div>
  </div>
  <div id="keyStatus"></div>
</header>

<div class="wrap">
  <div class="notice" id="keyNotice">
    ⚠️ API 키가 설정되지 않았습니다. <code>C:\Users\PC\클로드\.env</code> 파일에
    <code>ANTHROPIC_API_KEY=sk-ant-...</code>를 입력하거나,
    <a href="https://console.anthropic.com" target="_blank">console.anthropic.com</a>에서 키를 발급받으세요.
    또는 아래 입력란에 직접 입력하세요.
  </div>

  <div class="card">
    <h2>콘텐츠 생성</h2>
    <div class="grid2">
      <div class="fg full" id="keyRow" style="display:none">
        <label>🔑 API Key (일회용 입력)</label>
        <input type="password" id="apiKeyInput" placeholder="sk-ant-...">
      </div>
      <div class="fg">
        <label>🎤 아티스트 / 주제</label>
        <input id="topic" placeholder="예: aespa, 뉴진스, BTS 진, ILLIT" value="aespa">
      </div>
      <div class="fg">
        <label>📋 콘텐츠 유형</label>
        <select id="ctype">
          <option value="브랜딩 분석">브랜딩 분석 — 성공 전략 해부</option>
          <option value="이미지/컨셉 전략">이미지/컨셉 전략 — 비주얼 아이덴티티</option>
          <option value="위기 극복 분석">위기/논란 극복 분석</option>
          <option value="vs 비교 분석">vs 비교 — 두 아티스트 전략 대결</option>
          <option value="미래 전망">미래 전망 — 다음 컨셉 예측</option>
          <option value="팬덤 마케팅">팬덤 마케팅 전략 분석</option>
          <option value="글로벌 진출">글로벌 진출 전략 분석</option>
        </select>
      </div>
      <div class="fg full">
        <label>📝 추가 소재 (선택)</label>
        <textarea id="ctx" placeholder="최근 발매 앨범, 논란, 특이한 마케팅 포인트, 분석하고 싶은 각도 등"></textarea>
      </div>
    </div>
    <button class="btn" id="genBtn" onclick="generate()">✦ 콘텐츠 자동 생성</button>
  </div>

  <div class="err" id="errBox"></div>

  <div class="loading" id="loading">
    <div class="spin"></div>
    <div>AI가 콘텐츠를 분석하고 생성 중입니다...</div>
    <div style="font-size:12px;color:var(--muted);margin-top:7px">보통 10~20초 소요됩니다</div>
  </div>

  <div class="result" id="result">
    <div class="dl-bar">
      <button class="dlbtn dl-txt" onclick="download('txt')">⬇ TXT 다운로드</button>
      <button class="dlbtn dl-md" onclick="download('md')">⬇ Markdown 다운로드</button>
    </div>
    <br>
    <div class="rg">

      <div class="rc full">
        <h3>📌 제목 옵션 <span style="font-size:10px;color:var(--muted);text-transform:none">(클릭하여 복사)</span></h3>
        <div id="titlesOut"></div>
      </div>

      <div class="rc">
        <h3>🖼️ 썸네일 콘셉트</h3>
        <div class="tbox" id="thumbOut"></div>
      </div>

      <div class="rc">
        <h3>⚡ 인트로 훅 멘트 <button class="copy" onclick="cp('hookOut')">복사</button></h3>
        <div class="hook" id="hookOut"></div>
      </div>

      <div class="rc full">
        <h3>📐 영상 구성 아웃라인</h3>
        <div id="outlineOut"></div>
      </div>

      <div class="rc full">
        <h3>🎬 실제 스크립트 (인트로~배경) <button class="copy" onclick="cp('scriptOut')">복사</button></h3>
        <div class="prebox" id="scriptOut"></div>
      </div>

      <div class="rc">
        <h3>📄 YouTube 설명란 <button class="copy" onclick="cp('descOut')">복사</button></h3>
        <div class="prebox" id="descOut"></div>
      </div>

      <div class="rc">
        <h3>🏷️ 태그</h3>
        <div class="tags" id="tagsOut"></div>
      </div>

      <div class="rc full">
        <h3>💬 댓글 참여 유도 질문</h3>
        <div class="engage" id="engageOut"></div>
      </div>

      <div class="rc full">
        <h3>📈 업로드 전략 팁</h3>
        <ul class="tiplist" id="tipsOut"></ul>
      </div>
    </div>
  </div>
</div>

<script>
let lastData = null;

// API 키 상태 확인
fetch('/api/key-status').then(r=>r.json()).then(d=>{
  const el = document.getElementById('keyStatus');
  const notice = document.getElementById('keyNotice');
  const keyRow = document.getElementById('keyRow');
  if(d.ok){
    el.innerHTML = '<span class="key-status key-ok">✓ API 키 연결됨</span>';
  } else {
    el.innerHTML = '<span class="key-status key-none">✗ API 키 없음</span>';
    notice.classList.add('on');
    keyRow.style.display = '';
  }
});

async function generate(){
  const topic = document.getElementById('topic').value.trim();
  if(!topic){ showErr('아티스트/주제를 입력해주세요.'); return; }

  const body = {
    topic,
    content_type: document.getElementById('ctype').value,
    context: document.getElementById('ctx').value.trim() || '없음',
    api_key: document.getElementById('apiKeyInput').value.trim()
  };

  setLoad(true); hideErr();
  document.getElementById('result').classList.remove('on');

  try {
    const res = await fetch('/api/generate', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const d = await res.json();
    if(d.error){ showErr(d.error); return; }
    lastData = d;
    render(d);
  } catch(e){ showErr('서버 오류: '+e.message); }
  finally { setLoad(false); }
}

function render(d){
  // 제목
  document.getElementById('titlesOut').innerHTML = d.titles.map((t,i)=>
    `<div class="title-opt" onclick="navigator.clipboard.writeText(this.querySelector('.ttxt').textContent)">
      <span class="tnum">${i+1}</span><span class="ttxt">${esc(t)}</span>
    </div>`).join('');
  // 썸네일
  const th = d.thumbnail;
  document.getElementById('thumbOut').innerHTML = `
    <div class="tlabel">이미지 컨셉</div><div class="tval">${esc(th.main_image_concept)}</div>
    <div class="tlabel">텍스트 오버레이</div><div class="tval toverlay">${esc(th.text_overlay)}</div>
    <div class="tlabel">색감/분위기</div><div class="tval">${esc(th.color_mood)}</div>
    <div class="tlabel">레이아웃</div><div class="tval">${esc(th.layout)}</div>`;
  document.getElementById('hookOut').textContent = d.hook;
  document.getElementById('outlineOut').innerHTML = d.script_outline.map(s=>
    `<div class="oi"><span class="otime">${esc(s.section)}</span><span class="ocont">${esc(s.content)}</span></div>`).join('');
  document.getElementById('scriptOut').textContent = d.full_script_intro;
  document.getElementById('descOut').textContent = d.description;
  document.getElementById('tagsOut').innerHTML = d.tags.map(t=>`<span class="tag">#${esc(t)}</span>`).join('');
  document.getElementById('engageOut').textContent = d.engagement_question;
  document.getElementById('tipsOut').innerHTML = d.posting_tips.map(t=>`<li>${esc(t)}</li>`).join('');
  document.getElementById('result').classList.add('on');
  document.getElementById('result').scrollIntoView({behavior:'smooth',block:'start'});
}

function download(fmt){
  if(!lastData){ alert('먼저 콘텐츠를 생성해주세요.'); return; }
  const topic = document.getElementById('topic').value.trim();
  fetch('/api/download', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({data: lastData, topic, fmt})
  }).then(r=>r.blob()).then(blob=>{
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `kpop_content_${topic}_${new Date().toISOString().slice(0,10)}.${fmt}`;
    a.click();
  });
}

function cp(id){
  const el = document.getElementById(id);
  navigator.clipboard.writeText(el.textContent).then(()=>{
    const h = el.previousElementSibling;
    if(h){ const b=h.querySelector('.copy'); if(b){const o=b.textContent;b.textContent='✓ 복사됨';setTimeout(()=>b.textContent=o,1500);} }
  });
}
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function setLoad(v){ document.getElementById('loading').classList.toggle('on',v); document.getElementById('genBtn').disabled=v; }
function showErr(m){ const e=document.getElementById('errBox'); e.textContent='❌ '+m; e.classList.add('on'); }
function hideErr(){ document.getElementById('errBox').classList.remove('on'); }
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/key-status")
def key_status():
    key = load_api_key()
    return jsonify({"ok": bool(key and key.startswith("sk-"))})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    api_key = data.get("api_key", "").strip() or load_api_key()
    topic = data.get("topic", "").strip()
    content_type = data.get("content_type", "브랜딩 분석")
    context = data.get("context", "없음").strip() or "없음"

    if not api_key:
        return jsonify({"error": "API 키가 없습니다. .env 파일에 ANTHROPIC_API_KEY를 설정하거나 입력란에 직접 입력해주세요."}), 400
    if not topic:
        return jsonify({"error": "주제를 입력해주세요."}), 400

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = CONTENT_PROMPT.format(topic=topic, content_type=content_type, context=context)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = json.loads(raw)
        return jsonify(result)
    except anthropic.AuthenticationError:
        return jsonify({"error": "API 키가 올바르지 않습니다. console.anthropic.com에서 확인해주세요."}), 401
    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI 응답 파싱 오류. 다시 시도해주세요. ({e})"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json()
    d = body.get("data", {})
    topic = body.get("topic", "kpop")
    fmt = body.get("fmt", "txt")

    lines = []
    if fmt == "md":
        lines.append(f"# {topic} — K-pop 브랜딩 콘텐츠\n")
        lines.append("## 📌 제목 옵션\n")
        for i, t in enumerate(d.get("titles", []), 1):
            lines.append(f"{i}. {t}")
        lines.append("\n## 🖼️ 썸네일 콘셉트\n")
        th = d.get("thumbnail", {})
        lines.append(f"- **이미지**: {th.get('main_image_concept','')}")
        lines.append(f"- **텍스트**: {th.get('text_overlay','')}")
        lines.append(f"- **색감**: {th.get('color_mood','')}")
        lines.append(f"- **레이아웃**: {th.get('layout','')}")
        lines.append("\n## ⚡ 인트로 훅 멘트\n")
        lines.append(f"> {d.get('hook','')}")
        lines.append("\n## 📐 영상 구성 아웃라인\n")
        for s in d.get("script_outline", []):
            lines.append(f"### {s.get('section','')}")
            lines.append(s.get("content", "") + "\n")
        lines.append("## 🎬 실제 스크립트 (인트로~배경)\n")
        lines.append(d.get("full_script_intro", "") + "\n")
        lines.append("## 📄 YouTube 설명란\n")
        lines.append(d.get("description", "") + "\n")
        lines.append("## 🏷️ 태그\n")
        lines.append(" ".join(f"#{t}" for t in d.get("tags", [])) + "\n")
        lines.append("## 💬 댓글 유도 질문\n")
        lines.append(d.get("engagement_question", "") + "\n")
        lines.append("## 📈 업로드 팁\n")
        for tip in d.get("posting_tips", []):
            lines.append(f"- {tip}")
    else:
        lines.append(f"[{topic}] K-pop 브랜딩 콘텐츠\n{'='*50}\n")
        lines.append("[ 제목 옵션 ]")
        for i, t in enumerate(d.get("titles", []), 1):
            lines.append(f"  {i}. {t}")
        th = d.get("thumbnail", {})
        lines.append("\n[ 썸네일 콘셉트 ]")
        lines.append(f"  이미지: {th.get('main_image_concept','')}")
        lines.append(f"  텍스트: {th.get('text_overlay','')}")
        lines.append(f"  색감: {th.get('color_mood','')}")
        lines.append(f"  레이아웃: {th.get('layout','')}")
        lines.append("\n[ 인트로 훅 멘트 ]")
        lines.append(f"  {d.get('hook','')}")
        lines.append("\n[ 영상 구성 아웃라인 ]")
        for s in d.get("script_outline", []):
            lines.append(f"  ▸ {s.get('section','')}: {s.get('content','')}")
        lines.append("\n[ 실제 스크립트 ]")
        lines.append(d.get("full_script_intro", ""))
        lines.append("\n[ YouTube 설명란 ]")
        lines.append(d.get("description", ""))
        lines.append("\n[ 태그 ]")
        lines.append("  " + " ".join(f"#{t}" for t in d.get("tags", [])))
        lines.append("\n[ 댓글 유도 질문 ]")
        lines.append(f"  {d.get('engagement_question','')}")
        lines.append("\n[ 업로드 팁 ]")
        for tip in d.get("posting_tips", []):
            lines.append(f"  → {tip}")

    content = "\n".join(lines)
    import io as _io
    buf = _io.BytesIO(content.encode("utf-8-sig"))
    buf.seek(0)
    mime = "text/markdown" if fmt == "md" else "text/plain"
    return send_file(buf, mimetype=mime, as_attachment=True,
                     download_name=f"kpop_{re.sub(r'[^a-zA-Z0-9가-힣]','_',topic)}.{fmt}")


if __name__ == "__main__":
    key = load_api_key()
    print("=" * 55)
    print("  K-pop 브랜딩 콘텐츠 생성기 — http://localhost:5002")
    print(f"  API 키: {'✓ 로드됨' if key else '✗ 없음 (.env 파일 필요)'}")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
