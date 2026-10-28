"""全局配置。所有敏感项从环境变量读取，不写入代码。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
ROOT_DIR = BASE_DIR.parent                                  # diligence-platform/
DATA_DIR = Path(os.getenv("DILIGENCE_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "app.db"

SECRET_KEY = os.getenv("DILIGENCE_SECRET", "dev-only-change-me")
COOKIE_NAME = "diligence_sid"
SESSION_MAX_AGE = 7 * 24 * 3600
# 公网发布必备：HTTPS 下必须让 cookie 只走加密通道
COOKIE_SECURE = os.getenv("DILIGENCE_COOKIE_SECURE", "0") == "1"
# 公开站点建议关闭自助注册，改为管理员建号（0 = 关闭）
ALLOW_REGISTER = os.getenv("DILIGENCE_ALLOW_REGISTER", "1") != "0"

# DeepSeek（OpenAI 兼容协议）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 业务参数
CREDITS_PER_RUN = int(os.getenv("DILIGENCE_CREDITS_PER_RUN", "10"))
REGISTER_BONUS = int(os.getenv("DILIGENCE_REGISTER_BONUS", "100"))
MAX_QC_ROUNDS = 2
# 单文件上限 / 单项目上限 / 单项目文件数上限
MAX_UPLOAD_MB = int(os.getenv("DILIGENCE_MAX_UPLOAD_MB", "20"))
MAX_PROJECT_MB = int(os.getenv("DILIGENCE_MAX_PROJECT_MB", "200"))
MAX_FILES_PER_PROJECT = int(os.getenv("DILIGENCE_MAX_FILES_PER_PROJECT", "60"))

MOCK_MODE = not bool(DEEPSEEK_API_KEY)
# 演示模式（无 Key）下每步之间的停顿，让前端进度条看得见；接真实模型时无需它
MOCK_STEP_DELAY = float(os.getenv("DILIGENCE_MOCK_STEP_DELAY", "0.25"))

# 扫描件 OCR（本地引擎 rapidocr-onnxruntime，不联网、不外发）
OCR_DPI = int(os.getenv("DILIGENCE_OCR_DPI", "200"))
OCR_MAX_PAGES = int(os.getenv("DILIGENCE_OCR_MAX_PAGES", "30"))
OCR_MIN_SCORE = float(os.getenv("DILIGENCE_OCR_MIN_SCORE", "0.5"))
OCR_ENABLED = os.getenv("DILIGENCE_OCR", "1") != "0"

BOARDS = {
    "asset": "资产权属与经营基础",
    "labor": "劳动用工合规",
    "equity": "投资退出与股权回购",
    "all": "三维度全面核查",
}

# 每次核查固定覆盖的三个维度（顺序即执行顺序）
BOARD_SEQUENCE = ["asset", "labor", "equity"]
