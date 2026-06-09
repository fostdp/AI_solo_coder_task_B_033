import multiprocessing
import time
import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from backend.config import settings

logger = logging.getLogger(__name__)

_inference_process: Optional[multiprocessing.Process] = None
_inference_start_time: Optional[float] = None
_requests_processed: int = 0
_total_response_time_ms: float = 0.0


class BayesianFireDetector:
    def __init__(self):
        self.prior_fire = 0.001
        self.prior_no_fire = 0.999

        self.p_temp_rate_high_given_fire = 0.85
        self.p_temp_rate_high_given_no_fire = 0.05

        self.p_smoke_high_given_fire = 0.90
        self.p_smoke_high_given_no_fire = 0.03

        self.p_temp_high_given_fire = 0.75
        self.p_temp_high_given_no_fire = 0.10

        self.p_correlation_high_given_fire = 0.95
        self.p_correlation_high_given_no_fire = 0.08

    def calculate_fire_probability(
        self,
        temperature: float,
        temp_rate: float,
        smoke_density: float,
        temp_smoke_correlation: float
    ) -> Dict[str, Any]:
        temp_high = temperature > 45.0
        temp_rate_high = temp_rate > settings.FIRE_TEMP_RATE_WARNING
        smoke_high = smoke_density > settings.FIRE_SMOKE_DENSITY_WARNING
        correlation_high = temp_smoke_correlation > 0.7

        likelihood_fire = 1.0
        likelihood_no_fire = 1.0

        if temp_rate_high:
            likelihood_fire *= self.p_temp_rate_high_given_fire
            likelihood_no_fire *= self.p_temp_rate_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_temp_rate_high_given_fire)
            likelihood_no_fire *= (1 - self.p_temp_rate_high_given_no_fire)

        if smoke_high:
            likelihood_fire *= self.p_smoke_high_given_fire
            likelihood_no_fire *= self.p_smoke_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_smoke_high_given_fire)
            likelihood_no_fire *= (1 - self.p_smoke_high_given_no_fire)

        if temp_high:
            likelihood_fire *= self.p_temp_high_given_fire
            likelihood_no_fire *= self.p_temp_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_temp_high_given_fire)
            likelihood_no_fire *= (1 - self.p_temp_high_given_no_fire)

        if correlation_high:
            likelihood_fire *= self.p_correlation_high_given_fire
            likelihood_no_fire *= self.p_correlation_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_correlation_high_given_fire)
            likelihood_no_fire *= (1 - self.p_correlation_high_given_no_fire)

        posterior_fire = self.prior_fire * likelihood_fire
        posterior_no_fire = self.prior_no_fire * likelihood_no_fire

        total = posterior_fire + posterior_no_fire
        if total == 0:
            probability = 0.0
        else:
            probability = posterior_fire / total

        risk_level = "normal"
        if probability >= 0.9:
            risk_level = "critical"
        elif probability >= settings.FIRE_PROBABILITY_THRESHOLD:
            risk_level = "warning"
        elif probability >= 0.5:
            risk_level = "attention"

        return {
            "fire_probability": probability,
            "risk_level": risk_level,
            "factors": {
                "temp_high": temp_high,
                "temp_rate_high": temp_rate_high,
                "smoke_high": smoke_high,
                "correlation_high": correlation_high
            }
        }


class FireProbabilityRequest(BaseModel):
    temperature: float
    temp_rate: float
    smoke_density: float
    temp_smoke_correlation: float = 0.0


def _create_inference_app() -> FastAPI:
    app = FastAPI(title="Fire Inference Service", version="1.0.0")

    detector = BayesianFireDetector()
    request_count = 0
    total_response_time = 0.0

    @app.post("/api/v1/inference/fire_probability")
    async def calculate_fire_probability(request: FireProbabilityRequest):
        nonlocal request_count, total_response_time
        start_time = time.time()

        try:
            result = detector.calculate_fire_probability(
                temperature=request.temperature,
                temp_rate=request.temp_rate,
                smoke_density=request.smoke_density,
                temp_smoke_correlation=request.temp_smoke_correlation
            )

            processing_time_ms = (time.time() - start_time) * 1000
            request_count += 1
            total_response_time += processing_time_ms

            return {
                "success": True,
                "fire_probability": result["fire_probability"],
                "risk_level": result["risk_level"],
                "factors": result["factors"],
                "processing_time_ms": processing_time_ms
            }
        except Exception as e:
            logger.error(f"Inference error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/inference/health")
    async def health_check():
        return {
            "status": "healthy",
            "requests_processed": request_count,
            "average_response_time_ms": total_response_time / max(request_count, 1)
        }

    return app


def _run_inference_server(port: int):
    app = _create_inference_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def start_inference_service(port: Optional[int] = None) -> bool:
    global _inference_process, _inference_start_time, _requests_processed, _total_response_time_ms

    if _inference_process and _inference_process.is_alive():
        logger.warning("Inference service is already running")
        return True

    try:
        service_port = port or settings.FIRE_INFERENCE_SERVICE_PORT

        _inference_process = multiprocessing.Process(
            target=_run_inference_server,
            args=(service_port,),
            daemon=True,
            name="fire-inference-service"
        )

        _inference_process.start()
        _inference_start_time = time.time()
        _requests_processed = 0
        _total_response_time_ms = 0.0

        time.sleep(1.0)

        if _inference_process.is_alive():
            logger.info(f"Fire inference service started with PID {_inference_process.pid} on port {service_port}")
            return True
        else:
            logger.error("Fire inference service failed to start")
            _inference_process = None
            return False

    except Exception as e:
        logger.error(f"Failed to start fire inference service: {e}")
        _inference_process = None
        return False


def stop_inference_service() -> bool:
    global _inference_process, _inference_start_time, _requests_processed, _total_response_time_ms

    success = True

    if _inference_process and _inference_process.is_alive():
        try:
            _inference_process.terminate()
            _inference_process.join(timeout=5)

            if _inference_process.is_alive():
                logger.warning("Inference service did not exit gracefully, killing")
                _inference_process.kill()
                _inference_process.join(timeout=2)

            logger.info("Fire inference service stopped")
        except Exception as e:
            logger.error(f"Error stopping inference service: {e}")
            success = False

    _inference_process = None
    _inference_start_time = None
    _requests_processed = 0
    _total_response_time_ms = 0.0

    return success


def is_service_running() -> bool:
    return _inference_process is not None and _inference_process.is_alive()


async def call_inference_service(
    temperature: float,
    temp_rate: float,
    smoke_density: float,
    temp_smoke_correlation: float = 0.0,
    timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    global _requests_processed, _total_response_time_ms

    if not is_service_running():
        return None

    port = settings.FIRE_INFERENCE_SERVICE_PORT
    url = f"http://localhost:{port}/api/v1/inference/fire_probability"

    try:
        start_time = time.time()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json={
                    "temperature": temperature,
                    "temp_rate": temp_rate,
                    "smoke_density": smoke_density,
                    "temp_smoke_correlation": temp_smoke_correlation
                }
            )

            if response.status_code == 200:
                result = response.json()

                _requests_processed += 1
                if "processing_time_ms" in result:
                    _total_response_time_ms += result["processing_time_ms"]

                return result

    except Exception as e:
        logger.warning(f"Failed to call inference service: {e}")

    return None


def get_service_status() -> Dict[str, Any]:
    status = {
        "status": "stopped",
        "port": None,
        "pid": None,
        "uptime_seconds": None,
        "requests_processed": None,
        "average_response_time_ms": None
    }

    if is_service_running() and _inference_process:
        status["status"] = "running"
        status["port"] = settings.FIRE_INFERENCE_SERVICE_PORT
        status["pid"] = _inference_process.pid

        if _inference_start_time:
            status["uptime_seconds"] = time.time() - _inference_start_time

        status["requests_processed"] = _requests_processed

        if _requests_processed > 0:
            status["average_response_time_ms"] = _total_response_time_ms / _requests_processed

    return status
