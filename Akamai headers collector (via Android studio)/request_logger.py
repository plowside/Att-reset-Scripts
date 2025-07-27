# request_logger.py
import json
import logging
from mitmproxy import http

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("mitmproxy_logs.log", encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

class RequestLogger:
    def request(self, flow: http.HTTPFlow) -> None:
        target_path = "/identity-api/password-management-services/v1/unauth/id-inquiry"

        if target_path in flow.request.url:
            logger.info(f"\n[+] Захвачен запрос:")
            logger.info(f"URL: {flow.request.url}")
            logger.info(f"Method: {flow.request.method}")
            logger.info(f"Headers: {dict(flow.request.headers)}")

            # Сохраняем curl-команду в файл
            with open('curls.txt', 'a', encoding='utf-8') as f:
                f.write(f"json{json.dumps(dict(flow.request.headers))}\n")

            try:
                body = flow.request.content.decode("utf-8", errors="replace")
                logger.info(f"Body: {body}")
            except Exception as e:
                logger.error(f"Ошибка декодирования тела запроса: {e}")

addons = [
    RequestLogger()
]