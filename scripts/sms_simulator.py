from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="短信服务模拟器")


class SMSRequest(BaseModel):
    phone: str
    message: str


@app.post("/sms")
async def send_sms(request: SMSRequest):
    logger.info("=" * 60)
    logger.info(f"[短信发送] 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"[短信发送] 收件人: {request.phone}")
    logger.info(f"[短信发送] 内容: {request.message}")
    logger.info("=" * 60)

    return {
        "status": "success",
        "message": "短信发送成功（模拟）",
        "data": {
            "phone": request.phone,
            "timestamp": datetime.now().isoformat()
        }
    }


@app.get("/")
async def root():
    return {
        "service": "短信服务模拟器",
        "status": "running",
        "endpoint": "/sms",
        "method": "POST"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sms_simulator:app", host="0.0.0.0", port=8001, reload=True)
