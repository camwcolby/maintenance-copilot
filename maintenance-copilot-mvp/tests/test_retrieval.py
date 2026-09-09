from app.retrieval import search_text

def test_manual_search_finds_bearing():
    text = "Bearing degradation can cause elevated amperage. Check suction for debris."
    hits = search_text("high amps bearing", text, top_k=1)
    assert hits
    assert "Bearing" in hits[0]["text"]
