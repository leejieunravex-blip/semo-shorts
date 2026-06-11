#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys, os, shutil, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ══════════════════════════════════════════════════════
#  ★ 여기만 수정하세요 ★
# ══════════════════════════════════════════════════════
URL    = "https://youtu.be/99arhk9wdNE"
SECOND = 26        # 썸네일 뽑을 초 (이 초 안에서 최적 프레임 자동 선택)
# ══════════════════════════════════════════════════════

PYTHON  = sys.executable
_BIN    = r"C:\Users\PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
FFMPEG  = shutil.which("ffmpeg") or os.path.join(_BIN, "ffmpeg.exe")
FFPROBE = shutil.which("ffprobe") or os.path.join(_BIN, "ffprobe.exe")

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
RAW_VIDEO = os.path.join(OUT_DIR, "_raw_video.mp4")
RAW_VONLY = os.path.join(OUT_DIR, "_raw_video.f401.mp4")
RAW_AONLY = os.path.join(OUT_DIR, "_raw_video.f140.m4a")
OUTPUT    = os.path.join(OUT_DIR, "thumbnail_shorts.png")

WIDTH, HEIGHT = 1080, 1920


def run(cmd, **kw):
    print("  ▶", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def pick_best_frame(video_path, second, orig_w, orig_h):
    """
    SECOND 초 내 전체 프레임 분석.

    점수 = 얼굴_면적 × 눈_영역_Laplacian분산
      - 얼굴 면적: 클수록 인물이 잘 잡힘
      - Laplacian 분산: 눈 주변 엣지량 → 눈이 열릴수록 수치 높아짐
        (눈 감으면 매끄러워서 Laplacian↓, 뜨면 속눈썹·홍채 엣지로 Laplacian↑)
    """
    import cv2

    face_cas = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"  # alt2 = 더 정확
    )

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 24.0

    start_f = int(second * fps)
    end_f   = int((second + 1) * fps)
    total   = end_f - start_f

    print(f"  FPS: {fps:.1f} | 분석 프레임: {total}장 ({second}s ~ {second+1}s)")

    best_frame = None
    best_score = -1
    best_ts    = float(second)
    results_log = []
    scale = 0.3

    for fi in range(start_f, end_f):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            break

        small = cv2.resize(frame, (int(orig_w * scale), int(orig_h * scale)))
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        faces = face_cas.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(15, 15)
        )

        score = 0.0
        for (fx, fy, fw, fh) in faces:
            face_area = fw * fh

            # 눈 영역 = 얼굴 상단 45% (이마 제외 위해 10%~55%)
            ey0 = int(fh * 0.10); ey1 = int(fh * 0.55)
            eye_roi = gray[fy+ey0 : fy+ey1, fx : fx+fw]
            if eye_roi.size == 0:
                continue

            # Laplacian 분산: 높을수록 눈이 선명하게 열려 있음
            lap_var = cv2.Laplacian(eye_roi, cv2.CV_64F).var()

            score += face_area * lap_var

        results_log.append((fi, score))
        if score > best_score:
            best_score = score
            best_frame = frame.copy()
            best_ts    = fi / fps

        pct = (fi - start_f + 1) / total * 100
        print(f"    [{pct:5.1f}%] frame {fi}  score={score:,.0f}", end="\r")

    cap.release()
    print()

    top3 = sorted(results_log, key=lambda x: x[1], reverse=True)[:3]
    print("  상위 3프레임: " + " | ".join(
        f"frame {f} @ {f/fps:.2f}s (score={s:,.0f})" for f, s in top3
    ))

    if best_frame is None:
        print("  얼굴 감지 실패 → 첫 프레임 사용")
        cap2 = cv2.VideoCapture(video_path)
        cap2.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        _, best_frame = cap2.read()
        cap2.release()
        best_ts = float(second)

    return best_frame, best_ts, best_score


def crop_to_vertical(frame_bgr, orig_w, orig_h):
    """BGR 프레임을 1080×1920 센터 크롭"""
    from PIL import Image
    import numpy as np

    img = Image.fromarray(frame_bgr[:, :, ::-1])   # BGR → RGB

    # 세로 꽉 채우기 스케일
    scale = max(WIDTH / orig_w, HEIGHT / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img   = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - WIDTH)  // 2
    top  = (new_h - HEIGHT) // 2
    img  = img.crop((left, top, left + WIDTH, top + HEIGHT))
    return img


def main():
    # ① 영상 준비
    print("\n[1] 영상 준비...")
    if not os.path.exists(RAW_VIDEO):
        if os.path.exists(RAW_VONLY) and os.path.exists(RAW_AONLY):
            print("  스트림 병합...")
            run([FFMPEG, "-y", "-i", RAW_VONLY, "-i", RAW_AONLY, "-c", "copy", RAW_VIDEO])
        else:
            print("  최고화질 영상 다운로드...")
            run([PYTHON, "-m", "yt_dlp",
                 "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                 "--ffmpeg-location", os.path.dirname(FFMPEG),
                 "--merge-output-format", "mp4",
                 "-o", RAW_VIDEO, URL])
            if not os.path.exists(RAW_VIDEO) and os.path.exists(RAW_VONLY):
                run([FFMPEG, "-y", "-i", RAW_VONLY, "-i", RAW_AONLY, "-c", "copy", RAW_VIDEO])
    else:
        print(f"  재사용: {os.path.basename(RAW_VIDEO)}")

    # ② 원본 해상도 확인
    probe = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", RAW_VIDEO],
        capture_output=True, text=True, check=True)
    orig_w, orig_h = map(int, probe.stdout.strip().split(","))
    print(f"  원본 해상도: {orig_w}x{orig_h}")

    # ③ 최적 프레임 선택
    print(f"\n[2] {SECOND}초 내 최적 프레임 선택 중 (눈 감김 분석)...")
    import cv2
    best_frame, best_ts, best_score = pick_best_frame(RAW_VIDEO, SECOND, orig_w, orig_h)
    print(f"  ✓ 선택된 프레임: {best_ts:.3f}s  (score={best_score})")

    # ④ 세로 크롭 + PNG 저장
    print(f"\n[3] 1080×1920 세로 크롭 후 PNG 저장...")
    img = crop_to_vertical(best_frame, orig_w, orig_h)
    img.save(OUTPUT, "PNG")
    print(f"  ✓ 저장 완료: {OUTPUT}")

    # ⑤ 폴더 열기
    subprocess.Popen(["explorer", OUT_DIR])
    print(f"\n✅ 완성! → {OUTPUT}")


if __name__ == "__main__":
    main()
