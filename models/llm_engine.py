# models/llm_engine.py
import sys
import requests
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class LlamaEngine:
    """Connects to local Llama 3.2 via Ollama API to generate AI reasoning."""

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
        self.api_url = f"{self.host}/api/chat"
        # Ensure this matches the exact model name you pulled in Ollama
        self.model_name = "llama3.2"

    def generate_reasoning(self, ticker: str, metrics: Dict[str, Any], context_chunks: List[str]) -> str:
        """
        Sends the data to the Llama 3.2 model and returns the exact reasoning paragraph.
        """
        formatted_context = "\n\n".join([f"- {chunk.strip()}" for chunk in
                                         context_chunks]) if context_chunks else "No historical news context found."

        # We define clean roles. The inference server (Ollama) will automatically
        # translate this into the correct Meta tokens under the hood.
        system_content = (
            "You are the core quantitative analysis engine for SignalForge Pro. "
            "Synthesize market data and news context into a razor-sharp, actionable professional trade insight.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Base your reasoning STRICTLY on the provided Technical State and Historical News Context.\n"
            "2. Do NOT extrapolate or invent facts.\n"
            "3. Maintain a dense, institutional financial tone.\n"
            "4. NEVER use introductory filler phrases such as 'Based on...', 'According to...', 'The provided data shows...', or 'In conclusion...'.\n"
            "5. Start your response immediately with the direct asset analysis (e.g., 'NVDA's price action at $1,051.52 demonstrates...').\n"
            "6. Output your analysis in a single, polished paragraph (maximum 3 sentences)."
        )

        user_content = f"""Analyze the following asset context matrix for execution:

### ASSET TICKER: {ticker}

### REAL-TIME TECHNICAL STATE:
- Last Traded Price: ${metrics.get('last_price', 'N/A')}
- Rolling VWAP: ${metrics.get('vwap', 'N/A')}
- Intraday Volatility: {metrics.get('volatility', 'N/A')}
- Window Ticks: {metrics.get('tick_count', 'N/A')}

### HISTORICAL NEWS CONTEXT:
{formatted_context}

Generate only the 'AI Reasoning' value."""

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "temperature": 0.1  # Low temperature for strict, analytical output
        }

        try:
            logger.info(f"Sending prompt to Llama 3.2 for {ticker} analysis...")
            response = requests.post(self.api_url, json=payload, timeout=45)
            response.raise_for_status()

            result = response.json()
            return result.get("message", {}).get("content", "").strip()

        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to Llama 3.2 at {self.host}. Is Ollama running?")
            return "AI Analysis unavailable due to connection failure."
        except Exception as e:
            logger.error(f"Llama 3.2 inference failed: {e}")
            return "AI Analysis failed to compute."


if __name__ == "__main__":
    logger.info("Testing Llama 3.2 Inference Engine...")

    sample_metrics = {"last_price": 1051.52, "vwap": 1051.04, "volatility": 1.036, "tick_count": 10}
    sample_news = [
        "NVIDIA Corporation announces massive enterprise chip allocations following Q1 performance beats.",
        "Data center infrastructure demand scales up heavily across top cloud providers."
    ]

    engine = LlamaEngine()
    result = engine.generate_reasoning("NVDA", sample_metrics, sample_news)

    print("\n--- LLAMA 3.2 LIVE RESPONSE START ---")
    print(result)
    print("--- LLAMA 3.2 LIVE RESPONSE END ---\n")