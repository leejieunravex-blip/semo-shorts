#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
세모 플레이리스트 쇼츠 자동 제작 스크립트
- URL + 시작초 + 길이만 설정하면 가사 없이 완전 자동
- YouTube ko/en-US 자막 자동 다운로드 → 싱크 매핑 → 인코딩
"""
import io, sys, json, re, os, shutil, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ══════════════════════════════════════════════════════
#  ★ 여기만 수정하세요 ★
# ══════════════════════════════════════════════════════
URL        = "https://www.youtube.com/watch?v=99arhk9wdNE"
START_SEC  = 0       # 소스 시작 위치 (초)
DURATION   = 60      # 클립 길이 (초)
FADE_AUDIO = 0.3     # 오디오 페이드인/아웃 (초)
# ══════════════════════════════════════════════════════

# ─── 경로 ─────────────────────────────────────────────
PYTHON   = sys.executable
_BIN     = r"C:\Users\PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
FFMPEG   = shutil.which("ffmpeg") or os.path.join(_BIN, "ffmpeg.exe")
FFPROBE  = shutil.which("ffprobe") or os.path.join(_BIN, "ffprobe.exe")

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
RAW_VIDEO = os.path.join(OUT_DIR, "_raw_video.mp4")
RAW_VONLY = os.path.join(OUT_DIR, "_raw_video.f401.mp4")
RAW_AONLY = os.path.join(OUT_DIR, "_raw_video.f140.m4a")
KO_SUB    = os.path.join(OUT_DIR, "_subs.ko.json3")
EN_SUB    = os.path.join(OUT_DIR, "_subs.en-US.json3")   # en-US 없으면 en으로 폴백
EN_SUB_FB = os.path.join(OUT_DIR, "_subs.en.json3")
ASS_FILE  = os.path.join(OUT_DIR, "_subtitles.ass")
OUTPUT    = os.path.join(OUT_DIR, "output_shorts.mp4")

# ─── 자막 스타일 ──────────────────────────────────────
WIDTH, HEIGHT = 1080, 1920
FONT_NAME      = "AppleSDGothicNeoEB00"
FONT_SIZE_KOR  = 74   # 한글
FONT_SIZE_ENG  = 74   # 영어
OUTLINE   = 1
ENG_COLOR = "&H00FFB1F5"   # #F5B1FF 연보라 (위 / 영어)
KOR_COLOR = "&H00FFFFFF"   # #FFFFFF 흰색   (아래 / 한글)
BLACK     = "&H00000000"
ENG_Y     = 900            # 영어 줄 Y (화면 중앙 기준 위)
KOR_Y     = 990            # 한글 줄 Y (화면 중앙 기준 아래)

# ─── 추임새 패턴 ──────────────────────────────────────
_CHUIMSAE_RE = re.compile(
    r"^[\s(La|la|LA|~|♪|♬|na|NA|oh|Oh|ah|Ah|uh|Uh|mm|Mm)]+$"
)

def is_chuimsae(text: str) -> bool:
    """La La / Na Na 등 추임새 여부"""
    stripped = re.sub(r"[Ll][aA]|[Nn][aA]|[Oo][hH]|[Aa][hH]|[Mm]+|\s", "", text)
    return len(stripped) == 0 and len(text.strip()) > 0

def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))

def has_english_word(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text))

# ─── YouTube JSON3 파싱 ───────────────────────────────
_MEMBER_RE = re.compile(r"\[.*?\]\s*")

def clean_yt(raw: str) -> str:
    text = _MEMBER_RE.sub("", raw)
    text = text.replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)

def parse_json3(path: str) -> list:
    """[(tStartMs, tEndMs, text), ...]"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", [])
    result = []
    for i, ev in enumerate(events):
        ts = ev.get("tStartMs", 0)
        td = ev.get("dDurationMs", 0)
        te = ts + td
        # 다음 이벤트 시작으로 끝 보정 (겹침 방지)
        if i + 1 < len(events):
            te = min(te, events[i + 1].get("tStartMs", te))
        text = clean_yt("".join(s.get("utf8", "") for s in ev.get("segs", [])))
        if text:
            result.append((ts, te, text))
    return result

# ─── 타임스탬프 기준 ko/en 매핑 ──────────────────────
def match_subtitles(ko_blocks, en_blocks, start_ms, end_ms):
    """
    ko 블록 기준으로 en 블록을 타임스탬프 겹침으로 매핑.
    반환: [(out_start_s, out_end_s, top_text, bot_text), ...]
      top = 영어 줄, bot = 한글 줄
    """
    clip_dur = (end_ms - start_ms) / 1000.0
    result = []

    # en 블록을 빠르게 찾기 위한 인덱스
    en_idx = 0

    for (ko_s, ko_e, ko_text) in ko_blocks:
        # 클립 범위 밖 제외
        if ko_e <= start_ms or ko_s >= end_ms:
            continue

        # 출력 기준 시간
        out_s = max(0.0, (ko_s - start_ms) / 1000.0)
        out_e = min(clip_dur, (ko_e - start_ms) / 1000.0)
        if out_e <= out_s:
            continue

        # 이 ko 블록과 가장 많이 겹치는 en 블록 찾기
        best_en = ko_text   # 기본값: ko 텍스트 그대로
        best_overlap = 0
        for (en_s, en_e, en_text) in en_blocks:
            overlap = min(ko_e, en_e) - max(ko_s, en_s)
            if overlap > best_overlap:
                best_overlap = overlap
                best_en = en_text

        # ── 라인 타입 분류 ──────────────────────────────
        if is_chuimsae(ko_text):
            # 추임새: 위아래 동일, 한글 번역 없음
            top = ko_text
            bot = ko_text

        elif has_korean(ko_text):
            # 한글 원문 → top=영어번역(en자막), bot=한글
            top = best_en
            bot = ko_text

        else:
            # 영어 원문 (We Run And Fly 등)
            # top=영어 원문, bot=한글 번역 필요
            top = ko_text
            # en자막도 영어일 가능성 높음 → 한글 번역 시도
            if has_korean(best_en):
                bot = best_en          # 운 좋게 en자막이 한글이면 그대로
            else:
                bot = translate_en_to_ko(ko_text)

        result.append((round(out_s, 3), round(out_e, 3), top, bot))

    # ── 가사 간격 0: 각 줄의 끝을 다음 줄 시작으로 연장 ──
    for i in range(len(result) - 1):
        s, e, top, bot = result[i]
        next_s = result[i + 1][0]
        result[i] = (s, next_s, top, bot)

    return result

# ─── 영어 → 한국어 번역 ───────────────────────────────
_translate_cache = {}

def translate_en_to_ko(text: str) -> str:
    """영어 텍스트를 한국어로 번역 (deep-translator 사용)"""
    if text in _translate_cache:
        return _translate_cache[text]
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source="en", target="ko").translate(text)
        _translate_cache[text] = result
        print(f"  번역: {text!r} → {result!r}")
        return result
    except Exception as ex:
        print(f"  번역 실패 ({ex}): {text!r} 원문 사용")
        return text

# ─── ASS 자막 생성 ────────────────────────────────────
def to_ass_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"

def build_ass(lines):
    fmt = ("Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
           "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")
    def sty(name, color, fsize):
        return (f"{name},{FONT_NAME},{fsize},{color},{BLACK},{BLACK},{BLACK},"
                f"-1,0,0,0,100,100,0,0,1,{OUTLINE},0,5,10,10,10,1")

    header = (
        f"[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {WIDTH}\nPlayResY: {HEIGHT}\n"
        f"ScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\nFormat: {fmt}\n"
        f"Style: {sty('ENG', ENG_COLOR, FONT_SIZE_ENG)}\n"
        f"Style: {sty('KOR', KOR_COLOR, FONT_SIZE_KOR)}\n\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    cx = WIDTH // 2
    rows = []
    for (s, e, top, bot) in lines:
        ts, te = to_ass_time(s), to_ass_time(e)
        rows.append(f"Dialogue: 0,{ts},{te},ENG,,0,0,0,,{{\\pos({cx},{ENG_Y})}}{top}")
        rows.append(f"Dialogue: 0,{ts},{te},KOR,,0,0,0,,{{\\pos({cx},{KOR_Y})}}{bot}")
    return header + "\n".join(rows) + "\n"

# ─── 얼굴 감지 스마트 크롭 ────────────────────────────
def analyze_face_crop(video_path, start_sec, duration, orig_w, orig_h, crop_w, crop_h,
                      sample_interval=2.0, smooth_window=9):
    """
    클립 구간에서 1초마다 얼굴 감지 → 스무딩된 crop_x 타임라인 생성.
    반환: ffmpeg crop x 표현식 문자열 (얼굴 없으면 센터 크롭 값)
    """
    default_x = (orig_w - crop_w) // 2
    default_y = (orig_h - crop_h) // 2

    try:
        import cv2
    except ImportError:
        print("  [얼굴감지] opencv-python 없음 → 센터 크롭 사용")
        return str(default_x), str(default_y)

    # alt2.xml: 더 정확한 정면 얼굴 감지 (thumbnail 스크립트와 동일)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return str(default_x), str(default_y)

    timeline = []   # [(clip_t, crop_x)]
    scale = 0.3     # 감지 정확도 위해 0.25→0.3으로 상향

    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, (start_sec + t) * 1000)
        ret, frame = cap.read()
        if not ret:
            break

        small = cv2.resize(frame, (int(orig_w * scale), int(orig_h * scale)))
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # scaleFactor/minNeighbors 낮춰 감지율 향상
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(15, 15)
        )

        if len(faces) > 0:
            # 가장 큰 얼굴 기준으로 중앙에 배치 (여러 얼굴이면 큰 얼굴 우선)
            largest = max(faces, key=lambda f: f[2] * f[3])
            fx, fy, fw, fh = largest
            face_cx_orig = (fx + fw / 2) / scale   # 원본 좌표계로 변환
            crop_x = int(face_cx_orig - crop_w / 2) # 얼굴 중앙을 크롭 중앙으로
            crop_x = max(0, min(orig_w - crop_w, crop_x))
        else:
            crop_x = default_x

        timeline.append((t, crop_x))
        t += sample_interval

    cap.release()

    if not timeline:
        return str(default_x), str(default_y)

    # 이동 평균 스무딩
    half_w = smooth_window // 2
    smoothed = []
    for i, (t, x) in enumerate(timeline):
        lo = max(0, i - half_w)
        hi = min(len(timeline), i + half_w + 1)
        avg_x = int(sum(timeline[j][1] for j in range(lo, hi)) / (hi - lo))
        smoothed.append((t, avg_x))

    # 얼굴 감지 로그
    detected = sum(1 for (t, x) in smoothed if x != default_x)
    print(f"  [얼굴감지] {len(smoothed)}프레임 분석 / {detected}프레임 얼굴 감지")
    for (t, x) in smoothed:
        marker = "★" if x != default_x else "·"
        print(f"    {marker} t={t:5.1f}s  crop_x={x}")

    # ffmpeg 표현식 생성 (선형 보간 → 크롭이 부드럽게 이동)
    if len(smoothed) == 1:
        return str(smoothed[0][1]), str(default_y)

    # 각 구간: t0~t1 사이에서 x0→x1 선형 보간
    # crop=...'x0+(x1-x0)*(t-t0)/(t1-t0)'...
    expr = str(smoothed[-1][1])   # 마지막 구간 이후는 고정값
    for i in range(len(smoothed) - 2, -1, -1):
        t0, x0 = smoothed[i]
        t1, x1 = smoothed[i + 1]
        seg = f"({x0}+({x1}-{x0})*(t-{t0:.1f})/({t1:.1f}-{t0:.1f}))"
        expr = f"if(lt(t,{t1:.1f}),{seg},{expr})"

    # 유효 범위 클램프
    expr = f"clip({expr},0,{orig_w - crop_w})"

    return expr, str(default_y)


# ─── 유틸 ─────────────────────────────────────────────
def run(cmd, **kw):
    print("  ▶", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)

# ─── 메인 ─────────────────────────────────────────────
def main():
    start_ms = int(START_SEC * 1000)
    end_ms   = int((START_SEC + DURATION) * 1000)

    # ① 자막 다운로드
    # ko
    if not os.path.exists(KO_SUB):
        print("\n[1] ko 자막 다운로드...")
        run([PYTHON, "-m", "yt_dlp",
             "--write-sub", "--sub-lang", "ko", "--sub-format", "json3",
             "--skip-download", "-o", os.path.join(OUT_DIR, "_subs"), URL])
    else:
        print(f"[1] ko 자막 재사용: {os.path.basename(KO_SUB)}")

    # en-US → 없으면 en 폴백
    en_sub_path = None
    for lang, path in [("en-US", EN_SUB), ("en", EN_SUB_FB)]:
        if os.path.exists(path):
            en_sub_path = path
            print(f"[1] {lang} 자막 재사용: {os.path.basename(path)}")
            break
    if en_sub_path is None:
        for lang, path in [("en-US", EN_SUB), ("en", EN_SUB_FB)]:
            print(f"\n[1] {lang} 자막 다운로드 시도...")
            try:
                run([PYTHON, "-m", "yt_dlp",
                     "--write-sub", "--sub-lang", lang, "--sub-format", "json3",
                     "--skip-download", "-o", os.path.join(OUT_DIR, "_subs"), URL])
                if os.path.exists(path):
                    en_sub_path = path
                    break
            except Exception:
                pass
    if en_sub_path is None:
        print("[1] 영어 자막 없음 → ko 자막 전체를 Google 번역으로 대체")

    # ② 자막 파싱
    print("\n[2] 자막 파싱 및 타임스탬프 매핑...")
    ko_blocks = parse_json3(KO_SUB)
    en_blocks = parse_json3(en_sub_path) if en_sub_path else []

    lines = match_subtitles(ko_blocks, en_blocks, start_ms, end_ms)

    print(f"\n  총 {len(lines)}줄 매핑 결과:")
    print(f"  {'시간':>12}  {'영어(위)':30}  {'한글(아래)'}")
    print(f"  {'-'*80}")
    for (s, e, top, bot) in lines:
        print(f"  [{s:5.2f}~{e:5.2f}s]  {top[:28]:30}  {bot}")

    # ③ ASS 파일 작성
    print(f"\n[3] ASS 자막 파일 생성...")
    with open(ASS_FILE, "w", encoding="utf-8-sig") as f:
        f.write(build_ass(lines))
    print(f"  → {ASS_FILE}")

    # ④ 영상 준비
    print(f"\n[4] 영상 준비...")
    if not os.path.exists(RAW_VIDEO):
        if os.path.exists(RAW_VONLY) and os.path.exists(RAW_AONLY):
            print("  스트림 병합...")
            run([FFMPEG, "-y", "-i", RAW_VONLY, "-i", RAW_AONLY,
                 "-c", "copy", RAW_VIDEO])
        else:
            print("  영상 다운로드...")
            run([PYTHON, "-m", "yt_dlp",
                 "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                 "--ffmpeg-location", os.path.dirname(FFMPEG),
                 "--merge-output-format", "mp4",
                 "-o", RAW_VIDEO, URL])
            if not os.path.exists(RAW_VIDEO) and os.path.exists(RAW_VONLY):
                run([FFMPEG, "-y", "-i", RAW_VONLY, "-i", RAW_AONLY,
                     "-c", "copy", RAW_VIDEO])
    else:
        print(f"  재사용: {os.path.basename(RAW_VIDEO)}")

    # ⑤ 해상도 확인 → 크롭 계산
    probe = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", RAW_VIDEO],
        capture_output=True, text=True, check=True)
    ow, oh = map(int, probe.stdout.strip().split(","))
    if ow / oh > 9 / 16:
        cw, ch = int(oh * 9 / 16), oh
    else:
        cw, ch = ow, int(ow * 16 / 9)
    print(f"\n[5] 크롭: {ow}x{oh} → {cw}x{ch} → {WIDTH}x{HEIGHT}")
    print(f"  얼굴 감지 스마트 크롭 분석 중...")
    crop_x_expr, crop_y_expr = analyze_face_crop(
        RAW_VIDEO, START_SEC, DURATION, ow, oh, cw, ch
    )

    # ⑥ 인코딩
    print(f"\n[6] 인코딩 (소스 {START_SEC}s ~ {START_SEC+DURATION}s)...")
    ass_esc = ASS_FILE.replace("\\", "/").replace(":", "\\:")
    vf = (f"crop={cw}:{ch}:'{crop_x_expr}':{crop_y_expr},"
          f"scale={WIDTH}:{HEIGHT},"
          f"ass='{ass_esc}'")
    af = (f"afade=t=in:st=0:d={FADE_AUDIO},"
          f"afade=t=out:st={DURATION - FADE_AUDIO}:d={FADE_AUDIO}")

    run([FFMPEG, "-y",
         "-ss", str(START_SEC), "-i", RAW_VIDEO, "-t", str(DURATION),
         "-vf", vf, "-af", af,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         OUTPUT])

    print(f"\n✅ 완성! → {OUTPUT}")

if __name__ == "__main__":
    main()
