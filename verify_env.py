import sys
import torch
from loguru import logger

logger.remove()
logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")


def verify_runtime_environment() -> bool:
    logger.info("Initializing SignalForge environment validation protocol...")
    logger.info(f"Python Version: {sys.version}")
    logger.info(f"PyTorch Version: {torch.__version__}")

    cuda_available = torch.cuda.is_available()
    logger.info(f"CUDA Driver Link Established: {cuda_available}")

    if not cuda_available:
        logger.error("CRITICAL: CUDA is unavailable. Hardware invariants compromised.")
        return False

    device_id = torch.cuda.current_device()
    gpu_name = torch.cuda.get_device_name(device_id)
    vram_total = torch.cuda.get_device_properties(device_id).total_memory / (1024 ** 3)

    logger.info(f"Target Compute Device Recognized: [{device_id}] {gpu_name}")
    logger.info(f"Available Dedicated Hardware VRAM: {vram_total:.2f} GB")

    if "3050" not in gpu_name:
        logger.warning(f"Device name mismatch. Expected RTX 3050 variant, detected: {gpu_name}")

    logger.info("Task 01 Verification: SUCCESS. Compute hardware alignment validated.")
    return True


if __name__ == "__main__":
    success = verify_runtime_environment()
    sys.exit(0 if success else 1)