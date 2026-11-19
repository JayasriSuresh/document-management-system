import os
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User, Document

client = TestClient(app)

def get_token(email):
    response = client.post("/api/auth/login", json={"email": email, "password": "Pasword@123"})
    if response.status_code != 200:
        raise Exception(f"Login failed for {email}: {response.text}")
    return response.json()["access_token"]

def get_docs(token):
    return client.get("/api/documents", headers={"Authorization": f"Bearer {token}"}).json()

def delete_doc(token, doc_id):
    return client.delete(f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {token}"})

def run_tests():
    db = SessionLocal()
    j_token = get_token("jayasri@example.com")
    s_token = get_token("samrethi@example.com")
    suji_token = get_token("sujipriya@example.com")
    h_token = get_token("hindupriya@example.com")
    boom_token = get_token("boomika@example.com")
    
    # 1. Soft Delete Tests
    # Reset soft delete status for test docs so test is idempotent
    db.query(Document).filter(
        Document.original_filename.in_([
            "chennai_admin_doc.jpg",
            "mysore_admin_doc.jpg",
            "sujipriya_recent.jpg",
            "boomika_recent.jpg"
        ])
    ).update({Document.deleted_at: None, Document.deleted_by: None}, synchronize_session=False)
    db.commit()
    
    # We need to find the IDs of the documents
    # Samrethi doc (Chennai)
    c_doc = db.query(Document).filter(Document.original_filename == "chennai_admin_doc.jpg").first()
    # Hindu Priya doc (Mysore)
    m_doc = db.query(Document).filter(Document.original_filename == "mysore_admin_doc.jpg").first()
    
    # Sujipriya -> delete any document -> denied
    assert delete_doc(suji_token, c_doc.id).status_code == 403, "Sujipriya should be denied deletion"
    
    # Boomika -> delete any document -> denied
    assert delete_doc(boom_token, m_doc.id).status_code == 403, "Boomika should be denied deletion"

    # Samrethi -> delete Mysore document -> 404
    assert delete_doc(s_token, m_doc.id).status_code == 404, "Samrethi should not see Mysore doc"
    
    # Hindu Priya -> delete Chennai document -> 404
    assert delete_doc(h_token, c_doc.id).status_code == 404, "Hindu Priya should not see Chennai doc"
    
    # Samrethi -> delete Chennai document -> allowed
    res = delete_doc(s_token, c_doc.id)
    assert res.status_code == 200, f"Samrethi should be able to delete Chennai doc, got {res.status_code}"
    
    # Hindu Priya -> delete Mysore document -> allowed
    res = delete_doc(h_token, m_doc.id)
    assert res.status_code == 200, "Hindu Priya should be able to delete Mysore doc"
    
    # Jayasri -> delete remaining documents -> allowed
    # Find Sujipriya recent doc (Chennai)
    c2_doc = db.query(Document).filter(Document.original_filename == "sujipriya_recent.jpg").first()
    # Find Boomika recent doc (Mysore)
    m2_doc = db.query(Document).filter(Document.original_filename == "boomika_recent.jpg").first()
    
    assert delete_doc(j_token, c2_doc.id).status_code == 200, "Jayasri should delete Chennai doc"
    assert delete_doc(j_token, m2_doc.id).status_code == 200, "Jayasri should delete Mysore doc"
    
    # Verify they don't appear in lists anymore
    j_docs = get_docs(j_token)
    for doc in j_docs:
        assert doc["id"] not in [c_doc.id, m_doc.id, c2_doc.id, m2_doc.id], "Deleted doc found in list"
        
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
