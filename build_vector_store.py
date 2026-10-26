import json
import os
import chromadb
from chromadb.utils import embedding_functions

# ---- Setup ----
# This uses the same folder that already exists, so your embeddings are saved permanently on disk.
client = chromadb.PersistentClient(path="chroma_db")

# This turns text into embeddings (lists of numbers representing meaning).
# It downloads a small model the first time you run this — that's normal, just wait for it.
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# Create (or reuse) one collection that holds everything, and tell each entry which category it belongs to.
collection = client.get_or_create_collection(
    name="interview_knowledge_base",
    embedding_function=embedding_fn
)

# ---- Load and embed each category file ----
category_files = ["technical.json", "hr.json", "general.json"]

for filename in category_files:
    filepath = os.path.join("knowledge_base", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        questions = json.load(f)

    ids = []
    documents = []
    metadatas = []

    for q in questions:
        ids.append(q["id"])
        # We embed the question + model answer together, so a search can match on either.
        documents.append(f"Question: {q['question']}\nModel Answer: {q['model_answer']}")
        metadatas.append({
            "category": q["category"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "model_answer": q["model_answer"],
            "key_points": ", ".join(q["key_points"])  # Chroma metadata can't store lists, so join as text
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Added {len(ids)} questions from {filename}")

print("\nDone! Total questions in the vector store:", collection.count())

# ---- Quick test: does retrieval actually work? ----
print("\n--- Test search ---")
results = collection.query(
    query_texts=["What is the difference between a process and a thread?"],
    n_results=2
)
for i, doc_id in enumerate(results["ids"][0]):
    print(f"{i+1}. {doc_id} — {results['metadatas'][0][i]['question']}")