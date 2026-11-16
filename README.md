# PepperResearch Telegram Deal Hunter

Hệ thống tự động quét 7 nguồn kèo/bounty mỗi giờ, lọc qua **Cổng Sạch**, báo cáo kèo **mới** lên Telegram và điều phối vòng lặp tự phân loại kèo (không tự ý bid/nộp bài/comment/PR).

## Quy tắc Payout & Cổng Sạch
- **Ví nhận thưởng chính:** MetaMask Base `0xd170ad7a09EC585Fcb37DC7a9C37d65b63783B61`
- **Ví phụ (chỉ dùng khi nền tảng chỉ hỗ trợ Solana):** Solana `EMCzkUmfVLcbey2eugzppupQkz4Z8FiosLpMP9opUDv1`
- Chỉ nhận kèo trả tiền (`> $0`), Global hoặc mở cho Việt Nam, không yêu cầu login/đặt cọc, không shill/gambling.

## Vòng lặp tự xử kèo (Auto-Handle Loop)
1. **Nghe xác nhận `"xong"` / `"done"` / `"đã thực hiện xong"`:** Đầu mỗi chu kỳ, script đọc `getUpdates` (theo `state/telegram_offset.json`). Nếu Luân xác nhận đã xong bước đăng nhập, các kèo `needs_user_login` được chuyển sang `user_done` để Muse tiếp tục xử lý — và tin nhắn đăng nhập của kèo đó được **gỡ pin**.
2. **Gửi kèo mới & chờ 2 phút (120 giây):** Sau khi báo kèo mới lên nhóm Telegram, script chờ 120s. Nếu Luân trả lời bất kỳ nội dung gì -> dừng lại (`user replied, waiting`), kèo vẫn được phân loại để theo dõi pin nhưng không gửi tin đăng nhập vội. Nếu im lặng -> tự phân loại.
3. **Tự phân loại trạng thái (`state/pending_deals.json`):** Nếu sau 120s không có phản hồi, script tự ghi `mode: "auto_handle"` kèm trạng thái hành động:
   - `synmerco_watch_cron_handles`: Nhường cho watch cron 15 phút xử lý theo bid gate (không bid trùng).
   - `needs_muse_execution`: Kèo `make.fun` / `GitHub Bounties` / `Topcoder` để Muse + Gemini làm bài và nộp qua CLI/PR.
   - `needs_user_login`: Kèo `Superteam Earn` hoặc cần tài khoản đăng nhập -> gửi link trực tiếp đầy đủ + lời nhắc cho Luân (tối đa 1 lần/trạng thái) và **pin tin nhắn đó**.
   - `needs_user_decision`: Kèo chưa có quy trình chuẩn -> chờ Luân quyết định.
4. **Pin / gỡ pin (luật pin 16/11):** Tin nhắn thông báo kèo mới và tin nhắn yêu cầu đăng nhập được **pin** lên đầu nhóm để Luân không miss; khi kèo xong (user_done hoặc không còn kèo nào trong tin cần Luân) thì **gỡ pin**; tin mới tới thì pin mới. Trạng thái pin lưu ở `state/pinned_messages.json`. Yêu cầu: bot phải là admin nhóm + có quyền Pin Messages — nếu chưa có quyền, tin nhắn vẫn gửi bình thường, chỉ pin thất bại (ghi log warning).
5. **Cảnh báo phát sinh lạ & chống spam:** Nếu gặp lỗi format API hoặc dấu hiệu lừa đảo, hệ thống báo cảnh báo 1 lần duy nhất (lưu vết qua `seen_deals.json`, `pending_deals.json`, `sent_alerts.json`).

## Endpoint đã kiểm chứng (16/11/2026, đối chiếu connector đang chạy)
- Synmerco: `https://synmerco-escrow.onrender.com/v1/intents?status=open` (Bearer) — lưu ý API trả `budgetCents` dạng string, code đã chia 100 ra USD.
- MoltJobs: `https://api.moltjobs.io/v1/jobs?status=OPEN` (Bearer).
- HYRVE: `https://api.hyrveai.com/v1/jobs` (X-API-Key). Lưu ý: host này đôi lúc lỗi qua proxy, code tự bỏ qua khi lỗi.
- Superteam: `https://superteam.fun/api/listings?status=open&take=50` (public, không key) — ưu tiên `usdValue` trước `rewardAmount` (tránh số token thô).
- make.fun: `https://make.fun/api/competitions` (x-api-key, không bắt buộc).
- GitHub: `https://api.github.com/search/issues` (public, label bounty).
- Topcoder: `https://api.topcoder.com/v6/challenges?status=Active` (public, không auth).

## Nguồn đã đánh giá và SKIP (16/11/2026)
- **GOAT Market (goatmarket.com):** cert TLS hỏng (NET::ERR_CERT_DATE_INVALID) + server chặn IP máy này; dữ liệu offers.json cũ (kiểm tra lần cuối 17–24/10/2026, không làm mới mỗi ngày); 4,035/4,806 kèo là Freelancer (cần tài khoản mới bid). Chỉ dùng tay.
- **Opire (opire.dev):** API public `https://api.opire.dev/rewards` gọi được, nhưng chỉ còn 3 bounty live (tổng $162), không có escrow (tiền do funder trả trực tiếp), 2 kèo 2+ năm tuổi, 1 kèo bẻ captcha. GitHub bounties đã phủ cùng mặt bằng.

## Xác thực (credentials)
- Trên máy Muse: key lấy qua cơ chế surrogate của Secure Vault (`credentials.py`,
  không bao giờ in/ghi key ra file). Telegram gửi/đọc/pin qua curl + surrogate RAW
  (urllib/requests trực tiếp tới api.telegram.org bị lớp egress cắt) — xem `telegram.py`.
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
```
