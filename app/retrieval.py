import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def chunk_text(text, max_chars=700):
    parts = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(current) + len(part) + 2 <= max_chars:
            current = f"{current}\n\n{part}".strip()
        else:
            if current:
                chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks

def search_text(query, text, top_k=3):
    chunks = chunk_text(text)
    if not chunks:
        return []
    corpus = [query] + chunks
    matrix = TfidfVectorizer(stop_words="english").fit_transform(corpus)
    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    ranked = scores.argsort()[::-1][:top_k]
    return [{"text": chunks[i], "score": float(scores[i])} for i in ranked if scores[i] > 0]

def search_work_orders(query, work_orders, top_k=3):
    if work_orders.empty:
        return []
    docs = (
        work_orders["problem"].fillna("")
        + " "
        + work_orders["cause"].fillna("")
        + " "
        + work_orders["corrective_action"].fillna("")
    ).tolist()
    corpus = [query] + docs
    matrix = TfidfVectorizer(stop_words="english").fit_transform(corpus)
    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    ranked = scores.argsort()[::-1][:top_k]
    results = []
    for i in ranked:
        if scores[i] <= 0:
            continue
        row = work_orders.iloc[i].to_dict()
        row["score"] = float(scores[i])
        results.append(row)
    return results
