import os
import json
import logging
from dotenv import load_dotenv

load_dotenv(override=True)

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from ragas.run_config import RunConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ragas-eval")

DATASET_PATH = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "ragas_results.json")


def load_eval_dataset(path):
    """
    NOTE: the 'answer' field here is the audit result rewritten as plain prose, not the raw JSON the live pipeline returns. 
    RAGAS's faithfulness metric extracts individual factual statements from 'answer' to check against retrieved context; 
    it cannot parse structured JSON and silently returns NaN if given raw JSON. 
    The prose rewrite preserves the exact same findings, just in sentence form, so faithfulness can score it.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return Dataset.from_dict({
        "question": [row["question"] for row in raw],
        "contexts": [row["contexts"] for row in raw],
        "answer": [row["answer"] for row in raw],
        "ground_truth": [row["ground_truth"] for row in raw],
    })


def run_evaluation():
    logger.info(f"Loading eval dataset from: {DATASET_PATH}")
    dataset = load_eval_dataset(DATASET_PATH)
    logger.info(f"Loaded {len(dataset)} eval rows.")

    # RAGAS needs a judge LLM to score faithfulness/relevancy/precision:
    judge_llm = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.0,
    )
    ragas_llm = LangchainLLMWrapper(judge_llm)

    # RAGAS also needs embeddings for some metrics (context_precision).
    # Reuses the same local embedding model as the main retriever, so no extra API cost or dependency.
    judge_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    ragas_embeddings = LangchainEmbeddingsWrapper(judge_embeddings)

    logger.info("Running RAGAS evaluation (faithfulness, answer_relevancy, context_precision)...")
    # RunConfig: slows down and lengthens timeouts 
    # so Groq's free-tier rate limit (429s) doesn't cause jobs to time out before they succeed on retry. 
    # max_workers=1 forces sequential calls instead of parallel, which is slower overall but avoids bursts that trigger 429s.
    run_config = RunConfig(timeout=180, max_retries=10, max_wait=60, max_workers=1)

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
        run_config=run_config,
    )

    result_df = result.to_pandas()
    result_dict = result_df.to_dict(orient="records")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        # Converts np.nan / float('nan') into valid JSON null
        clean_dict = json.loads(result_df.to_json(orient="records"))
        json.dump(clean_dict, f, indent=2)

    logger.info("=" * 60)
    logger.info("RAGAS Evaluation Complete")
    logger.info(f"Results saved to: {RESULTS_PATH}")
    logger.info("=" * 60)
    print(result_df)

    return result_dict


if __name__ == "__main__":
    run_evaluation()