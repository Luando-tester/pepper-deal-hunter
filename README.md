# PepperResearch Telegram Deal Hunter

Hệ thống tự động quét 7 nguồn kèo/bounty mỗi giờ, lọc qua **Cổng Sạch** và báo cáo các kèo **mới** lên nhóm Telegram (không spam khi không có kèo mới, không tự ý bid/nộp bài).

## Quy tắc Payout & Cổng Sạch
- **Ví nhận thưởng chính:** MetaMask Base `0xd170ad7a09EC585Fcb37DC7a9C37d65b63783B61`
- **Ví phụ (chỉ dùng cho Superteam Earn / make.fun):** Solana `EMCzkUmfVLcbey2eugzppupQkz4Z8FiosLpMP9opUDv1`
- Chỉ nhận kèo trả tiền (`> $0`), Global hoặc mở cho Việt Nam, không yêu cầu login/đặt cọc, không shill/gambling.

## Endpoint đã kiểm chứng (16/11/2026, đối chiếu connector đang chạy)
- Synmerco: `https://synmerco-escrow.onrender.com/v1/intents?status=open` (Bearer) — lưu ý API trả `budgetCents` dạng string, code đã chia 100 ra USD.
- MoltJobs: `https://api.moltjobs.io/v1/jobs?status=OPEN` (Bearer).
- HYRVE: `https://api.hyrveai.com/v1/jobs` (X-API-Key). Lưu ý: host này đôi lúc lỗi qua proxy, code tự bỏ qua khi lỗi.
- Superteam: `https://superteam.fun/api/listings?status=open&take=50` (public, không key) — ưu tiên `usdValue` trước `rewardAmount` (tránh số token thô).
- make.fun: `https://make.fun/api/competitions` (x-api-key, không bắt buộc).
- GitHub: `https://api.github.com/search/issues` (public, label bounty).
- Topcoder: `https://api.topcoder.com/v6/challenges?status=Active` (public, không auth).

## Xác thực (credentials)
- Trên máy Muse: key lấy qua cơ chế surrogate của Secure Vault (`credentials.py`,
  không bao giờ in/ghi key ra file). Telegram gửi qua helper curl đã kiểm chứng.
- Chạy standalone (bản GitHub): điền key vào `.env` theo `.env.example`, code tự
  fallback sang biến môi trường khi không có surrogate.

## Cổng sạch — các bộ lọc đã kiểm chứng
- Budget phải > $0 và ≤ $100.000 (chặn dữ liệu lỗi, vd sponsor nhập nhầm số token thô).
- Từ khóa cấm: shill, gambling/betting, sports betting, prediction market,
  predictions, activation fee, deposit, v.v. — xem `filter.py`.
- Chỉ Global hoặc mở cho Vietnam; không yêu cầu login/đặt cọc.

## Cài đặt & Chạy thử
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Điền TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID và các API key vào .env
set -a && source .env && set +a
python3 hunter.py