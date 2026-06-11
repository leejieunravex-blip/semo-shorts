#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세모 쇼츠 자동 제작 웹서비스 v2
- 영어/한국어 자막 스타일 완전 개별 설정
- 첫 자막 0.3s 페이드인 / 마지막 자막 0.3s 페이드아웃
"""
import io, sys, os, json, re, shutil, subprocess, uuid, threading, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# ─── 환경 설정 ──────────────────────────────────────────
PYTHON   = sys.executable
_BIN     = r"C:\Users\PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
FFMPEG   = shutil.which("ffmpeg") or os.path.join(_BIN, "ffmpeg.exe")
FFPROBE  = shutil.which("ffprobe") or os.path.join(_BIN, "ffprobe.exe")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.environ.get("JOBS_DIR", os.path.join(BASE_DIR, "web_jobs"))
os.makedirs(JOBS_DIR, exist_ok=True)

# 클라우드 환경에서는 Noto Sans CJK KR 폰트 사용
_IS_CLOUD = not os.path.exists(_BIN)
_DEFAULT_FONT = "Noto Sans CJK KR" if _IS_CLOUD else "AppleSDGothicNeoEB00"

WIDTH, HEIGHT = 1080, 1920
FADE_AUDIO    = 0.3

# ─── 잡 관리 ────────────────────────────────────────────
JOBS  = {}
_lock = threading.Lock()

def _log(jid, msg):
    with _lock:
        JOBS[jid]['log'].append(msg)

def _step(jid, n, msg):
    with _lock:
        JOBS[jid]['step']     = n
        JOBS[jid]['step_msg'] = msg
    _log(jid, f"[{n}/6] {msg}")


# ═══════════════════════════════════════════════════════
#  색상 변환
# ═══════════════════════════════════════════════════════
def rgb_to_ass(hex_color: str, opacity_pct: float = 100) -> str:
    """#RRGGBB → &HAABBGGRR  (opacity 100=불투명, 0=투명)"""
    c = hex_color.lstrip('#')
    if len(c) == 3:
        c = c[0]*2 + c[1]*2 + c[2]*2
    r, g, b = c[0:2], c[2:4], c[4:6]
    alpha = format(round((1 - opacity_pct / 100) * 255), '02X')
    return f"&H{alpha}{b}{g}{r}".upper()


# ═══════════════════════════════════════════════════════
#  ASS 자막 생성
# ═══════════════════════════════════════════════════════
def to_ass_time(sec: float) -> str:
    h  = int(sec // 3600)
    m  = int((sec % 3600) // 60)
    s  = sec % 60
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


DEFAULT_STYLE = {
    "font":           _DEFAULT_FONT,
    "size":           74,
    "pos_x":          540,
    "pos_y":          900,
    "alignment":      5,
    "bold":           True,
    "italic":         False,
    "underline":      False,
    "strikeout":      False,
    "color":          "#F5B1FF",
    "color_opacity":  100,
    "outline_color":  "#000000",
    "outline_opacity":100,
    "outline_width":  1,
    "shadow_color":   "#000000",
    "shadow_opacity": 100,
    "shadow_depth":   0,
    "blur":           0,
    "scale_x":        100,
    "scale_y":        100,
    "spacing":        0,
    "angle":          0,
}
DEFAULT_KOR = {**DEFAULT_STYLE,
    "color":   "#FFFFFF",
    "pos_y":   990,
}


def build_ass(lines, eng_sty: dict, kor_sty: dict) -> str:
    """
    lines: [(start_s, end_s, eng_text, kor_text), ...]
    첫 번째 줄: \fad(300,0)  마지막 줄: \fad(0,300)
    """
    def s2a(st):
        """style dict → ASS Style line 값"""
        pc = rgb_to_ass(st['color'],          st.get('color_opacity',  100))
        oc = rgb_to_ass(st['outline_color'],   st.get('outline_opacity',100))
        bc = rgb_to_ass(st['shadow_color'],    st.get('shadow_opacity', 100))
        sc = pc   # SecondaryColour = Primary
        bold      = -1 if st.get('bold')      else 0
        italic    = -1 if st.get('italic')    else 0
        underline = -1 if st.get('underline') else 0
        strikeout = -1 if st.get('strikeout') else 0
        return (f"{st['font']},{st['size']},"
                f"{pc},{sc},{oc},{bc},"
                f"{bold},{italic},{underline},{strikeout},"
                f"{st.get('scale_x',100)},{st.get('scale_y',100)},"
                f"{st.get('spacing',0)},{st.get('angle',0)},"
                f"1,{st.get('outline_width',1)},{st.get('shadow_depth',0)},"
                f"{st.get('alignment',5)},10,10,10,1")

    fmt = ("Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
           "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")

    header = (f"[Script Info]\nScriptType: v4.00+\n"
              f"PlayResX: {WIDTH}\nPlayResY: {HEIGHT}\n"
              f"ScaledBorderAndShadow: yes\n\n"
              f"[V4+ Styles]\nFormat: {fmt}\n"
              f"Style: ENG,{s2a(eng_sty)}\n"
              f"Style: KOR,{s2a(kor_sty)}\n\n"
              f"[Events]\n"
              f"Format: Layer, Start, End, Style, Name, "
              f"MarginL, MarginR, MarginV, Effect, Text\n")

    rows = []
    last = len(lines) - 1
    for idx, (s, e, top, bot) in enumerate(lines):
        ts, te = to_ass_time(s), to_ass_time(e)

        # 페이드 태그
        if idx == 0 and idx == last:
            fade = r"{\fad(300,300)}"
        elif idx == 0:
            fade = r"{\fad(300,0)}"
        elif idx == last:
            fade = r"{\fad(0,300)}"
        else:
            fade = ""

        # 블러 태그
        e_blur = rf"{{\blur{eng_sty.get('blur',0)}}}" if eng_sty.get('blur',0) else ""
        k_blur = rf"{{\blur{kor_sty.get('blur',0)}}}" if kor_sty.get('blur',0) else ""

        ex = eng_sty.get('pos_x', 540)
        ey = eng_sty.get('pos_y', 900)
        kx = kor_sty.get('pos_x', 540)
        ky = kor_sty.get('pos_y', 990)

        rows.append(
            f"Dialogue: 0,{ts},{te},ENG,,0,0,0,,"
            f"{{\\pos({ex},{ey})}}{fade}{e_blur}{top}"
        )
        rows.append(
            f"Dialogue: 0,{ts},{te},KOR,,0,0,0,,"
            f"{{\\pos({kx},{ky})}}{fade}{k_blur}{bot}"
        )

    return header + "\n".join(rows) + "\n"


# ═══════════════════════════════════════════════════════
#  자막 파싱 & 매핑 (make_shorts.py 동일)
# ═══════════════════════════════════════════════════════
_MEMBER_RE = re.compile(r"\[.*?\]\s*")

def clean_yt(raw):
    t = _MEMBER_RE.sub("", raw)
    return re.sub(r"\s+", " ", t.replace("\n", " ").strip())

def parse_json3(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", [])
    result = []
    for i, ev in enumerate(events):
        ts = ev.get("tStartMs", 0)
        td = ev.get("dDurationMs", 0)
        te = ts + td
        if i + 1 < len(events):
            te = min(te, events[i+1].get("tStartMs", te))
        text = clean_yt("".join(s.get("utf8","") for s in ev.get("segs",[])))
        if text:
            result.append((ts, te, text))
    return result

def is_chuimsae(text):
    s = re.sub(r"[Ll][aA]|[Nn][aA]|[Oo][hH]|[Aa][hH]|[Mm]+|\s", "", text)
    return len(s) == 0 and len(text.strip()) > 0

def has_korean(text):
    return bool(re.search(r"[가-힣]", text))

_trans_cache = {}
def translate_en_to_ko(text):
    if text in _trans_cache:
        return _trans_cache[text]
    try:
        from deep_translator import GoogleTranslator
        r = GoogleTranslator(source="en", target="ko").translate(text)
        _trans_cache[text] = r
        return r
    except Exception:
        return text

def match_subtitles(ko_blocks, en_blocks, start_ms, end_ms):
    clip_dur = (end_ms - start_ms) / 1000.0
    result = []
    for (ko_s, ko_e, ko_text) in ko_blocks:
        if ko_e <= start_ms or ko_s >= end_ms:
            continue
        out_s = max(0.0, (ko_s - start_ms) / 1000.0)
        out_e = min(clip_dur, (ko_e - start_ms) / 1000.0)
        if out_e <= out_s:
            continue
        best_en, best_ov = ko_text, 0
        for (en_s, en_e, en_text) in en_blocks:
            ov = min(ko_e, en_e) - max(ko_s, en_s)
            if ov > best_ov:
                best_ov, best_en = ov, en_text
        if is_chuimsae(ko_text):
            top = bot = ko_text
        elif has_korean(ko_text):
            top, bot = best_en, ko_text
        else:
            top = ko_text
            bot = best_en if has_korean(best_en) else translate_en_to_ko(ko_text)
        result.append((round(out_s,3), round(out_e,3), top, bot))
    for i in range(len(result)-1):
        s, _, top, bot = result[i]
        result[i] = (s, result[i+1][0], top, bot)
    return result


# ═══════════════════════════════════════════════════════
#  얼굴 감지 크롭
# ═══════════════════════════════════════════════════════
def analyze_face_crop(video_path, start_sec, duration, ow, oh, cw, ch, jid=None):
    default_x = (ow - cw) // 2
    default_y = (oh - ch) // 2
    try:
        import cv2
    except ImportError:
        return str(default_x), str(default_y)

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return str(default_x), str(default_y)

    timeline, scale, t = [], 0.3, 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, (start_sec + t) * 1000)
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (int(ow*scale), int(oh*scale)))
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.05, 3, minSize=(15,15))
        if len(faces) > 0:
            fx, fy, fw, fh = max(faces, key=lambda f: f[2]*f[3])
            cx = int((fx + fw/2) / scale - cw/2)
            timeline.append((t, max(0, min(ow-cw, cx))))
        else:
            timeline.append((t, default_x))
        t += 2.0
    cap.release()

    if not timeline:
        return str(default_x), str(default_y)

    hw = 4
    smoothed = []
    for i, (tt, x) in enumerate(timeline):
        lo, hi = max(0,i-hw), min(len(timeline),i+hw+1)
        smoothed.append((tt, int(sum(timeline[j][1] for j in range(lo,hi))/(hi-lo))))

    det = sum(1 for _,x in smoothed if x != default_x)
    if jid:
        _log(jid, f"  얼굴 감지: {len(smoothed)}구간 / {det}구간 감지")

    if len(smoothed) == 1:
        return str(smoothed[0][1]), str(default_y)

    expr = str(smoothed[-1][1])
    for i in range(len(smoothed)-2, -1, -1):
        t0, x0 = smoothed[i]
        t1, x1 = smoothed[i+1]
        seg = f"({x0}+({x1}-{x0})*(t-{t0:.1f})/({t1:.1f}-{t0:.1f}))"
        expr = f"if(lt(t,{t1:.1f}),{seg},{expr})"
    return f"clip({expr},0,{ow-cw})", str(default_y)


# ═══════════════════════════════════════════════════════
#  잡 실행 (백그라운드 스레드)
# ═══════════════════════════════════════════════════════
def run_job(jid, url, start_sec, duration, eng_sty, kor_sty):
    jdir      = os.path.join(JOBS_DIR, jid)
    os.makedirs(jdir, exist_ok=True)
    raw_video = os.path.join(jdir, "_raw_video.mp4")
    ko_sub    = os.path.join(jdir, "_subs.ko.json3")
    en_sub    = os.path.join(jdir, "_subs.en-US.json3")
    en_sub_fb = os.path.join(jdir, "_subs.en.json3")
    ass_file  = os.path.join(jdir, "_subtitles.ass")
    output    = os.path.join(jdir, "output_shorts.mp4")
    start_ms  = int(start_sec * 1000)
    end_ms    = int((start_sec + duration) * 1000)

    def sp(cmd):
        return subprocess.run(cmd, check=True, capture_output=True,
                              text=True, encoding='utf-8', errors='replace')

    try:
        JOBS[jid]['status'] = 'running'

        # ① 자막 다운로드
        _step(jid, 1, "자막 다운로드 중...")
        sp([PYTHON, "-m", "yt_dlp",
            "--write-sub", "--sub-lang", "ko", "--sub-format", "json3",
            "--skip-download", "--no-playlist",
            "-o", os.path.join(jdir, "_subs"), url])
        if not os.path.exists(ko_sub):
            raise FileNotFoundError("한국어 자막 없음 (자막이 없는 영상이거나 URL 오류)")

        en_sub_path = None
        for lang, path in [("en-US", en_sub), ("en", en_sub_fb)]:
            try:
                sp([PYTHON, "-m", "yt_dlp",
                    "--write-sub", "--sub-lang", lang, "--sub-format", "json3",
                    "--skip-download", "--no-playlist",
                    "-o", os.path.join(jdir, "_subs"), url])
                if os.path.exists(path):
                    en_sub_path = path
                    _log(jid, f"  영어 자막({lang}) 완료")
                    break
            except Exception:
                pass
        if not en_sub_path:
            _log(jid, "  영어 자막 없음 → Google 번역 사용")

        # ② 파싱
        _step(jid, 2, "자막 싱크 매핑 중...")
        ko_blocks = parse_json3(ko_sub)
        en_blocks = parse_json3(en_sub_path) if en_sub_path else []
        lines = match_subtitles(ko_blocks, en_blocks, start_ms, end_ms)
        _log(jid, f"  총 {len(lines)}줄 매핑 완료")

        # ③ ASS
        _step(jid, 3, "자막 파일 생성 중...")
        with open(ass_file, "w", encoding="utf-8-sig") as f:
            f.write(build_ass(lines, eng_sty, kor_sty))
        _log(jid, "  ASS 자막 생성 완료 (첫줄 페이드인 / 마지막줄 페이드아웃 적용)")

        # ④ 영상 다운로드
        _step(jid, 4, "영상 다운로드 중...")
        sp([PYTHON, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
            "--ffmpeg-location", os.path.dirname(FFMPEG),
            "--merge-output-format", "mp4",
            "--no-playlist", "-o", raw_video, url])
        rvonly = os.path.join(jdir, "_raw_video.f401.mp4")
        raonly = os.path.join(jdir, "_raw_video.f140.m4a")
        if not os.path.exists(raw_video) and os.path.exists(rvonly):
            subprocess.run([FFMPEG, "-y", "-i", rvonly, "-i", raonly,
                            "-c", "copy", raw_video], check=True, capture_output=True)
        if not os.path.exists(raw_video):
            raise FileNotFoundError("영상 다운로드 실패")
        _log(jid, "  영상 다운로드 완료")

        # ⑤ 해상도 + 얼굴 감지
        _step(jid, 5, "얼굴 감지 & 크롭 분석 중...")
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", raw_video],
            capture_output=True, text=True, check=True)
        ow, oh = map(int, probe.stdout.strip().split(","))
        cw = int(oh * 9/16) if ow/oh > 9/16 else ow
        ch = oh             if ow/oh > 9/16 else int(ow * 16/9)
        _log(jid, f"  원본 {ow}x{oh} → 크롭 {cw}x{ch} → {WIDTH}x{HEIGHT}")
        cx_expr, cy_expr = analyze_face_crop(raw_video, start_sec, duration,
                                              ow, oh, cw, ch, jid)

        # ⑥ 인코딩
        _step(jid, 6, "최종 인코딩 중... (약 1~2분)")
        ass_esc = ass_file.replace("\\", "/").replace(":", "\\:")
        vf = (f"crop={cw}:{ch}:'{cx_expr}':{cy_expr},"
              f"scale={WIDTH}:{HEIGHT},"
              f"ass='{ass_esc}'")
        af = (f"afade=t=in:st=0:d={FADE_AUDIO},"
              f"afade=t=out:st={duration-FADE_AUDIO}:d={FADE_AUDIO}")
        proc = subprocess.run(
            [FFMPEG, "-y",
             "-ss", str(start_sec), "-i", raw_video, "-t", str(duration),
             "-vf", vf, "-af", af,
             "-c:v", "libx264", "-preset", "slow", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             output],
            capture_output=True, text=True, encoding='utf-8', errors='replace')
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 오류:\n{proc.stderr[-600:]}")

        _log(jid, "  인코딩 완료! ✅")
        with _lock:
            JOBS[jid].update({'status':'done','step':6,'output':output,'progress':100})

    except Exception as ex:
        _log(jid, f"\n❌ 오류: {ex}")
        with _lock:
            JOBS[jid].update({'status':'error','error':str(ex)})


# ═══════════════════════════════════════════════════════
#  Flask 라우트
# ═══════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    data      = request.get_json()
    url       = re.sub(r"&list=[^&]+|&start_radio=[^&]+|&index=[^&]+",
                       "", (data.get("url") or "").strip())
    start_sec = int(data.get("start_sec", 0))
    duration  = int(data.get("duration",  60))

    def parse_sty(d, default):
        if not d:
            return dict(default)
        out = dict(default)
        for k, v in d.items():
            if k in out:
                out[k] = type(out[k])(v) if not isinstance(out[k], bool) else bool(v)
            else:
                out[k] = v
        return out

    eng_sty = parse_sty(data.get("eng_style"), DEFAULT_STYLE)
    kor_sty = parse_sty(data.get("kor_style"), DEFAULT_KOR)

    if not url:
        return jsonify({"error": "URL을 입력해주세요"}), 400

    jid = str(uuid.uuid4())[:8]
    with _lock:
        JOBS[jid] = {
            'status':'pending','step':0,'step_msg':'대기 중',
            'progress':0,'log':[],'output':None,'error':None,
            'created':time.time()
        }
    threading.Thread(target=run_job,
                     args=(jid, url, start_sec, duration, eng_sty, kor_sty),
                     daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/api/status/<jid>")
def api_status(jid):
    if jid not in JOBS:
        return jsonify({"error":"없는 작업"}), 404
    j = JOBS[jid]
    prog = {0:0,1:10,2:25,3:35,4:60,5:75,6:90}.get(j['step'],0)
    if j['status'] == 'done':
        prog = 100
    return jsonify({
        "status":   j['status'],
        "step":     j['step'],
        "step_msg": j.get('step_msg',''),
        "progress": prog,
        "log":      j['log'][-40:],
        "error":    j.get('error'),
    })


@app.route("/api/download/<jid>")
def api_download(jid):
    if jid not in JOBS:
        return jsonify({"error":"없음"}), 404
    out = JOBS[jid].get('output')
    if not out or not os.path.exists(out):
        return jsonify({"error":"파일 없음"}), 404
    return send_file(out, as_attachment=True,
                     download_name=f"shorts_{jid}.mp4",
                     mimetype="video/mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("="*50)
    print(f"  세모 쇼츠 메이커 v2 — http://localhost:{port}")
    print("="*50)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
