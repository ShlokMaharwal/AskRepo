import math
import threading

from app.config import Settings


class Reranker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.lock = threading.RLock()

    def score(self, question: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        with self.lock:
            if self.model is None:
                import torch
                from sentence_transformers import CrossEncoder

                torch.set_num_threads(self.settings.model_threads)
                self.model = CrossEncoder(
                    self.settings.reranker_model,
                    device="cpu",
                    max_length=self.settings.reranker_max_length,
                    trust_remote_code=False,
                    cache_dir=str(self.settings.model_cache),
                )
                if self.settings.quantize_models:
                    from app.index.quantize import quantize_cpu_model

                    self.model.model = quantize_cpu_model(
                        self.model.model, linears=self.settings.quantize_linears
                    )
            # Explicit identity activation avoids applying sigmoid twice when library defaults vary.
            import torch

            logits = self.model.predict(
                [(question, text) for text in documents],
                batch_size=self.settings.reranker_batch_size,
                activation_fct=torch.nn.Identity(),
                show_progress_bar=False,
            )
            return [1 / (1 + math.exp(-max(-60.0, min(60.0, float(logit))))) for logit in logits]
