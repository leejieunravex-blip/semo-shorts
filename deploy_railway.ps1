# Railway 배포 스크립트
# 실행 방법: PowerShell에서 .\deploy_railway.ps1

Write-Host "=== 세모 쇼츠 Railway 배포 ===" -ForegroundColor Cyan

# 1. git 초기화
if (-not (Test-Path ".git")) {
    git init
    Write-Host "[1/4] Git 초기화 완료" -ForegroundColor Green
} else {
    Write-Host "[1/4] Git 이미 초기화됨" -ForegroundColor Yellow
}

# 2. Railway CLI 설치 확인
$railwayCmd = Get-Command railway -ErrorAction SilentlyContinue
if (-not $railwayCmd) {
    Write-Host "[2/4] Railway CLI 설치 중..." -ForegroundColor Yellow
    npm install -g @railway/cli
} else {
    Write-Host "[2/4] Railway CLI 이미 설치됨" -ForegroundColor Green
}

# 3. 파일 스테이징
git add .
git commit -m "deploy: 세모 쇼츠 메이커 v2" 2>$null
if ($?) {
    Write-Host "[3/4] Git 커밋 완료" -ForegroundColor Green
} else {
    Write-Host "[3/4] 변경사항 없음 (이미 최신)" -ForegroundColor Yellow
}

# 4. Railway 배포
Write-Host "[4/4] Railway에 배포 중..." -ForegroundColor Cyan
Write-Host ""
Write-Host "브라우저에서 Railway 로그인이 열립니다." -ForegroundColor Yellow
Write-Host "로그인 후 프로젝트 이름을 입력하세요 (예: semo-shorts)" -ForegroundColor Yellow
Write-Host ""

railway up

Write-Host ""
Write-Host "=== 배포 완료! ===" -ForegroundColor Green
Write-Host "Railway 대시보드에서 URL 확인: https://railway.app/dashboard" -ForegroundColor Cyan
