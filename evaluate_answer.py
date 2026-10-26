import os
import json
import time
import chromadb
from chromadb.utils import embedding_functions
import google.generativeai as genai
from dotenv import load_dotenv

# ---- Setup ----
load_dotenv()  # reads GEMINI_API_KEY from your .env file
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-3.6-flash")

client = chromadb.PersistentClient(path="chroma_db")
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_collection(
    name="interview_knowledge_base",
    embedding_function=embedding_fn
)

with open(os.path.join("knowledge_base", "rubric.json"), "r", encoding="utf-8") as f:
    rubric = json.load(f)


def evaluate(candidate_answer, question_text=None):
    """
    Retrieves the best-matching question from the vector store (using either the
    typed question, or the candidate's answer if no question is given), then asks
    Gemini to score it using the rubric.
    """
    search_text = question_text if question_text else candidate_answer

    t0 = time.time()
    results = collection.query(query_texts=[search_text], n_results=1)
    print(f"[TIMING] ChromaDB retrieval took {time.time() - t0:.1f}s")

    matched_meta = results["metadatas"][0][0]
    matched_question = matched_meta["question"]
    model_answer = matched_meta["model_answer"]
    key_points = matched_meta["key_points"]
    category = matched_meta["category"]

    # Build the prompt: rubric + retrieved context + candidate's actual answer
    prompt = f"""You are an interview evaluator. Score the candidate's answer using the rubric below.
Respond ONLY with valid JSON, no other text, in this exact structure:
{{
  "scores": {{"relevance": 0-100, "content_quality": 0-100, "communication": 0-100, "confidence": 0-100, "technical_knowledge": 0-100}},
  "overall_score": 0-100,
  "strength": "one specific thing they did well",
  "improvement": "one specific thing to improve",
  "suggestion": "a concrete way to improve it"
}}

RUBRIC DIMENSIONS:
{json.dumps(rubric["dimensions"], indent=2)}

INTERVIEW CATEGORY: {category}

QUESTION: {matched_question}

MODEL ANSWER (for reference): {model_answer}

KEY POINTS EXPECTED: {key_points}

CANDIDATE'S ANSWER: {candidate_answer}

Note: for HR/General questions, set technical_knowledge to null since it doesn't apply.
"""

    t1 = time.time()
    response = model.generate_content(prompt, request_options={"timeout": 60})
    print(f"[TIMING] Gemini call took {time.time() - t1:.1f}s")
    raw_text = response.text.strip()

    # Gemini sometimes wraps JSON in ```json fences — strip them if present
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        print("Could not parse JSON. Raw response was:\n", raw_text)
        return None

    return {
        "matched_question": matched_question,
        "category": category,
        **result
    }


def evaluate_many(items):
    """
    items: a list of (question_text, candidate_answer) pairs.
    Grades ALL answers in ONE Gemini request, which avoids Google's
    requests-per-minute limit. Returns a list of results in the same order
    (None for any answer that could not be graded).
    """
    blocks = []
    categories = []
    for number, (question_text, candidate_answer) in enumerate(items, start=1):
        # RAG retrieval step: find the matching question + model answer in ChromaDB
        results = collection.query(query_texts=[question_text], n_results=1)
        meta = results["metadatas"][0][0]
        categories.append(meta["category"])
        blocks.append(
            f"--- ANSWER {number} ---\n"
            f"CATEGORY: {meta['category']}\n"
            f"QUESTION: {meta['question']}\n"
            f"MODEL ANSWER (for reference): {meta['model_answer']}\n"
            f"KEY POINTS EXPECTED: {meta['key_points']}\n"
            f"CANDIDATE'S ANSWER: {candidate_answer}\n"
        )
    print(f"[TIMING] Retrieved context for {len(items)} questions from ChromaDB")

    instructions = """You are an interview evaluator. Score EACH candidate answer below using the rubric.
Respond ONLY with valid JSON (no other text), in exactly this structure, with one entry per answer, in order:
{"results": [
  {"answer_number": 1,
   "scores": {"relevance": 0-100, "content_quality": 0-100, "communication": 0-100, "confidence": 0-100, "technical_knowledge": 0-100 or null},
   "strength": "one specific thing they did well",
   "improvement": "one specific thing to improve",
   "suggestion": "a concrete way to improve it"}
]}
For HR and General questions, set technical_knowledge to null.
Keep strength, improvement and suggestion to one sentence each.
"""
    prompt = (
        instructions
        + "\nRUBRIC DIMENSIONS:\n" + json.dumps(rubric["dimensions"], indent=2)
        + "\n\n" + "\n".join(blocks)
    )

    parsed = None
    for attempt in range(3):
        try:
            t1 = time.time()
            response = model.generate_content(prompt, request_options={"timeout": 120})
            print(f"[TIMING] Gemini batch call took {time.time() - t1:.1f}s")
            raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw_text)["results"]
            break
        except Exception as error:
            print(f"[ERROR] Batch evaluation attempt {attempt + 1} failed: {error}")
            time.sleep(10)  # wait before retrying so we don't hit the rate limit again

    by_number = {}
    for entry in parsed or []:
        by_number[entry.get("answer_number")] = entry

    output = []
    for number in range(1, len(items) + 1):
        entry = by_number.get(number)
        try:
            scores = entry["scores"]
            applicable = [v for v in scores.values() if isinstance(v, (int, float))]
            overall = round(sum(applicable) / len(applicable), 1) if applicable else 0
            output.append({
                "category": categories[number - 1],
                "scores": scores,
                "overall_score": overall,  # average of the scored dimensions, as the rubric defines
                "strength": entry["strength"],
                "improvement": entry["improvement"],
                "suggestion": entry["suggestion"],
            })
        except (TypeError, KeyError):
            output.append(None)
    return output

# ---- Test it with a sample candidate answer ----
if __name__ == "__main__":
    sample_answer = (
        "A process is like a running program with its own memory, and a thread "
        "is inside a process. Threads in the same process share memory so they "
        "can work together faster, but processes are separate from each other."
    )

    result = evaluate(sample_answer)

    if result:
        print("\n===== EVALUATION RESULT =====")
        print("Matched question:", result["matched_question"])
        print("Category:", result["category"])
        print("\nScores:", json.dumps(result["scores"], indent=2))
        print("\nOverall score:", result["overall_score"])
        print("\nStrength:", result["strength"])
        print("Improvement:", result["improvement"])
        print("Suggestion:", result["suggestion"])