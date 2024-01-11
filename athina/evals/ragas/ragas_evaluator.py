
from typing import Optional
from athina.interfaces.athina import AthinaExperiment
from athina.interfaces.model import Model
import time
from typing import Optional
from athina.interfaces.result import EvalResult, EvalResultMetric
from athina.interfaces.model import Model
from athina.helpers.logger import logger

from ..base_evaluator import BaseEvaluator
from datasets import Dataset
from ragas.llms import LangchainLLM
from langchain.chat_models import ChatOpenAI
from ragas import evaluate
from athina.keys import OpenAiApiKey


class RagasEvaluator(BaseEvaluator):
    _model: str
    _openai_api_key: str
    _experiment: Optional[AthinaExperiment] = None

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if model is None:
            self._model = self.default_model
        elif not Model.is_supported(model):
            raise ValueError(f"Unsupported model: {model}")
        else:
            self._model = model
        
        if openai_api_key is None:
            self._openai_api_key = OpenAiApiKey.get_key()
        else:
            self._openai_api_key = openai_api_key

    def _validate_args(self, **kwargs) -> None:
        for arg in self.required_args:
            if arg not in kwargs:
                raise ValueError(f"Missing required argument: {arg}")
            
    def _get_model(self):
        return ChatOpenAI(model_name=self._model, api_key=self._openai_api_key)

    def _evaluate(self, **kwargs) -> EvalResult:
        """
        Run the Ragas evaluator.
        """
        start_time = time.time()
        self._validate_args(**kwargs)
        metrics = []
        try:
            self.ragas_metric.llm = LangchainLLM(llm=self._get_model())
            data = self.generate_data_to_evaluate(**kwargs)
            dataset = Dataset.from_dict(data)
            scores = evaluate(dataset, metrics=[self.ragas_metric])
            metrics.append(EvalResultMetric(id=self.metric_ids[0], value=scores[self.ragas_metric_name]))
        except Exception as e:
            logger.error(f"Error occurred during eval: {e}")
            raise e

        end_time = time.time()
        eval_runtime_ms = int((end_time - start_time) * 1000)
        llm_eval_result = EvalResult(
            name=self.name,
            display_name=self.display_name,
            data=kwargs,
            failure=False,
            reason='',
            runtime=eval_runtime_ms,
            model=self._model,
            metrics=metrics,
        )
        return {k: v for k, v in llm_eval_result.items() if v is not None}


