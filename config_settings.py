import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Windows 控制台默认 GBK,模型返回的 emoji/中文会报 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Setttings:
    BASE_URL = os.getenv("BASE_URL")
    API_KEY = os.getenv("API_KEY")
    MODEL = os.getenv("MODEL")
    POSTGRES_URI = os.getenv("POSTGRES_URI")
    AGENTS_NAMESPACE=666
    LOCAL_SKILLS_DIR=os.getenv("LOCAL_SKILLS_DIR")



settings = Setttings()
