from fastapi import APIRouter, UploadFile, File, Depends
from sqlmodel import Session, select
import os, json, shutil

from database import get_session
from models import Document
from services import landing_ai, pathway_client, finance_logic, pathway_rag
from services.extraction_schema import COMPREHENSIVE_SCHEMA, categorize_extraction

router = APIRouter()
UPLOAD_DIR = "./uploads"


# -----------------------
# Upload a document (POST)
# -----------------------
@router.post("/")
async def upload_document(
    task_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    # 1️⃣ Save file locally
    task_dir = os.path.join(UPLOAD_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    file_path = os.path.join(task_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2️⃣ ADE parse → markdown
    parsed = landing_ai.parse_pdf(file_path)
    markdown = parsed.get("markdown", "")

    # 3️⃣ ADE extract → structured JSON (using comprehensive 39-field schema)
    extraction = landing_ai.extract_from_markdown(markdown, COMPREHENSIVE_SCHEMA)
    extraction_json = extraction.get("extraction", {})
    
    # Categorize the extraction by domain (financial, company, deal, risk, operational)
    categorized_data = categorize_extraction(extraction_json)
    
    import json
    print("\n🚀 Raw ADE Response:", json.dumps(extraction, indent=2))
    print("🧩 ADE Extraction JSON:", json.dumps(extraction_json, indent=2))
    print("📊 Categorized Data:", json.dumps(categorized_data, indent=2))

    # ---------------------------------------------------
    # 🧩 4️⃣ Compute financial metrics (normalize + calculate ratios)
    # ---------------------------------------------------
    metrics = pathway_client.process_ade_data(extraction_json)

    # ---------------------------------------------------
    # 🧠 5️⃣ CFO logic (based on computed metrics)
    # ---------------------------------------------------
    analysis = finance_logic.analyze_financials(extraction_json)

    # ---------------------------------------------------
    # 💾 6️⃣ Save all metadata to DB
    # ---------------------------------------------------
    doc = Document(
        task_id=task_id,
        filename=file.filename,
        path=file_path,
        markdown=markdown,
        extraction_json=json.dumps(extraction_json),
        meta_json=json.dumps({"parsed": True}),
        ingested=True,
        red_flags=json.dumps(analysis["insights"])  # update key name
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # ---------------------------------------------------
    # 🔍 7️⃣ Index document for RAG (Hybrid Indexing)
    # ---------------------------------------------------
    try:
        pathway_rag.index_document(
            task_id=task_id,
            doc_id=doc.id,
            markdown=markdown,
            extraction_json=extraction_json,
            metadata={
                "filename": file.filename,
                "doc_id": doc.id,
                "file_path": file_path
            }
        )
        print(f"✅ Document {file.filename} indexed for RAG")
    except Exception as e:
        print(f"⚠️ RAG indexing failed (non-critical): {e}")

    # ---------------------------------------------------
    # ✅ 8️⃣ Return a rich response
    # ---------------------------------------------------
    return {
        "id": doc.id,
        "task_id": task_id,
        "filename": doc.filename,
        "ingested": True,
        "metrics": metrics,
        "analysis": analysis,
        "extraction": extraction_json
    }


# ---------------------
# List documents (GET)
# ---------------------
@router.get("/")
async def list_documents(task_id: str, session: Session = Depends(get_session)):
    docs = session.exec(select(Document).where(Document.task_id == task_id)).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "ingested": d.ingested,
            "red_flags": json.loads(d.red_flags or "[]"),
            "created_at": str(d.created_at)
        }
        for d in docs
    ]
