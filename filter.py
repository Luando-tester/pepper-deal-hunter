from config import EVM_BASE_WALLET, SOLANA_WALLET

# Từ khóa cấm tuyệt đối (shill, fake, cờ bạc, phí kích hoạt, ngoài scope)
BANNED_KEYWORDS = [
    "shill",
    "raid",
    "retweet",
    "follow & like",
    "fake review",
    "gambling",
    "casino",
    "betting",
    "sportsbook",
    "slot machine",
    "poker",
    "lottery",
    "ponzi",
    "mlm",
    "activation fee",
    "security deposit",
    "pay to apply",
    "send crypto first",
    "kyc fee",
    "sports betting",
    "prediction market",
    "predictions",
]

# Các vùng địa lý bị loại (chỉ giữ Global hoặc Vietnam)
BLOCKED_REGION_KEYWORDS = [
    "us only",
    "usa only",
    "united states only",
    "eu only",
    "europe only",
    "uk only",
    "india only",
    "americas only",
    "north america only",
    "exclude vietnam",
]


def resolve_payout_wallet(deal: dict) -> tuple[str, str]:
    """
    Trả về (network_label, wallet_address) theo đúng quy tắc:
    - Mặc định mọi payout về MetaMask Base: 0xd170ad7a09EC585Fcb37DC7a9C37d65b63783B61
    - Chỉ dùng Solana EMCzkUmfVLcbey2eugzppupQkz4Z8FiosLpMP9opUDv1 khi nền tảng chỉ hỗ trợ Solana.
    """
    network = str(deal.get("network") or "base").lower()
    if network in ("solana_only", "solana"):
        return ("Solana", SOLANA_WALLET)
    return ("Base (EVM)", EVM_BASE_WALLET)


def is_clean_deal(deal: dict) -> tuple[bool, str]:
    """
    Cổng sạch bắt buộc:
    1. Trả tiền thật (budget > $0)
    2. Không shill, fake, gambling, deposit/activation fee
    3. Công khai, không cần login để làm việc
    4. Mở Global hoặc Vietnam
    5. URL hợp lệ
    """
    budget = float(deal.get("budget") or 0)
    if budget <= 0:
        return False, "Budget <= $0"

    # Chặn dữ liệu lỗi: kèo nhỏ không thể có budget > $100k (vd sponsor nhập nhầm
    # số lượng token thô vào trường rewardAmount). Hackathon lớn xử lý riêng, không qua hunter này.
    if budget > 100000:
        return False, f"Budget bất thường ${budget:g} (nghi dữ liệu lỗi)"

    if not deal.get("url"):
        return False, "Thiếu link kèo"

    if deal.get("requires_login") is True:
        return False, "Yêu cầu login mới làm được"

    if deal.get("deposit_required") is True:
        return False, "Yêu cầu đặt cọc / phí kích hoạt"

    combined_text = f"{deal.get('title', '')} {deal.get('description', '')}".lower()
    for bad in BANNED_KEYWORDS:
        if bad in combined_text:
            return False, f"Chứa từ khóa cấm: {bad}"

    region_text = f"{deal.get('region', '')} {combined_text}".lower()
    for blocked in BLOCKED_REGION_KEYWORDS:
        if blocked in region_text:
            return False, f"Giới hạn khu vực không hỗ trợ VN: {blocked}"

    # Gắn thông tin ví chuẩn vào deal đã pass
    net_label, wallet = resolve_payout_wallet(deal)
    deal["payout_network"] = net_label
    deal["payout_wallet"] = wallet
    return True, "PASS"