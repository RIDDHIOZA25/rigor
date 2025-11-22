from fastapi import APIRouter, Depends, BackgroundTasks
from sqlmodel import Session, select
import json, uuid

from database import get_session
from models import ChatMessage, Memo, Document
from services import gemini_client, finance_logic
from services.multi_query_rag import multi_query_rag

router = APIRouter()

# --- In-memory status tracker (for polling) ---
chat_status = {}  # {chat_id: {"status": str, "progress": int, "message": str}}


def update_status(chat_id, status, progress, message):
    chat_status[chat_id] = {"status": status, "progress": progress, "message": message}


# ----------------------
# Get All Chats for Task
# ----------------------
@router.get("/")
def get_all_chats(task_id: str, session: Session = Depends(get_session)):
    chats = session.exec(
        select(ChatMessage)
        .where(ChatMessage.task_id == task_id)
        .order_by(ChatMessage.created_at)
    ).all()
    
    return [
        {
            "chat_id": chat.id,
            "role": chat.role,
            "response": chat.content,
            "reasoning_log": json.loads(chat.reasoning_log or '{"sub_queries": [], "insights": []}'),
            "citations": json.loads(chat.citations or "[]"),
            "status": chat.status,
            "created_at": chat.created_at.isoformat(),
        }
        for chat in chats
    ]


# ----------------------
# Create Chat Request
# ----------------------
@router.post("/")
def create_chat(
    task_id: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    user_message = payload.get("message", "")
    chat_id = str(uuid.uuid4())

    # Store initial chat record
    chat_msg = ChatMessage(
        id=chat_id,
        task_id=task_id,
        role="user",
        content=user_message,
        status="pending",
    )
    session.add(chat_msg)
    session.commit()

    # Background processing
    background_tasks.add_task(run_agent_pipeline, chat_id, task_id, user_message, session)

    return {"chat_id": chat_id, "status": "pending"}


# ----------------------
# Poll Chat Status
# ----------------------
@router.get("/{chat_id}/status")
def get_chat_status(chat_id: str):
    return chat_status.get(chat_id, {"status": "unknown", "progress": 0})


# ----------------------
# Get Chat Result
# ----------------------
@router.get("/{chat_id}")
def get_chat_result(chat_id: str, session: Session = Depends(get_session)):
    chat = session.get(ChatMessage, chat_id)
    if not chat:
        return {"error": "Chat not found"}

    return {
        "chat_id": chat.id,
        "role": chat.role,
        "response": chat.content,
        "reasoning_log": json.loads(chat.reasoning_log or '{"sub_queries": [], "insights": []}'),
        "citations": json.loads(chat.citations or "[]"),
        "status": chat.status,
    }


# ----------------------
# Background CFO Agent
# ----------------------
def run_agent_pipeline(chat_id: str, task_id: str, user_message: str, session: Session):
    try:
        update_status(chat_id, "loading_data", 10, "Fetching financial data from ADE")

        # 1️⃣ Fetch all ADE JSONs from DB for this task
        docs = session.exec(select(Document).where(Document.task_id == task_id)).all()
        if not docs:
            update_status(chat_id, "failed", 100, "No document found for this task.")
            return

        structured_data = {}
        for d in docs:
            try:
                extracted = json.loads(d.extraction_json or "{}")
                # Normalize key casing to avoid mismatches
                extracted = {k.lower(): v for k, v in extracted.items()}
                structured_data.update(extracted)
            except Exception as e:
                print(f"⚠️ Could not parse ADE JSON for {d.filename}: {e}")

        print(f"🧾 Structured data sent to CFO agent: {structured_data}")

        update_status(chat_id, "computing_metrics", 40, "Processing data and computing financial metrics")

        # 2️⃣ Compute financial metrics
        analysis = finance_logic.analyze_financials(structured_data)
        metrics = analysis.get("summary", {})
        insights = analysis.get("insights", [])

        update_status(chat_id, "searching_documents", 60, "Searching indexed documents with multi-query RAG")

        # 🔍 3️⃣ Multi-Query RAG: Decompose query → retrieve per sub-query → synthesize
        try:
            rag_result = multi_query_rag(
                query=user_message,
                task_id=task_id,
                structured_data=structured_data,
                metrics=metrics,
                insights=insights
            )
            
            summary = rag_result["answer"]
            sub_queries = rag_result.get("sub_queries", [])
            citations = rag_result.get("citations", [])
            rag_reasoning = rag_result.get("reasoning", "")
            
            print(f"✅ Multi-query RAG: {len(sub_queries)} sub-queries, {len(citations)} citations")
            print(f"📌 Sub-queries: {sub_queries}")
            print(f"📄 Citations: {citations}")
            
        except Exception as e:
            print(f"⚠️ Multi-query RAG failed, falling back to direct answer: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: Direct Gemini answer without RAG
            # Still try to decompose query to show analysis steps
            from services.multi_query_rag import decompose_query
            try:
                sub_queries = decompose_query(user_message)
            except:
                sub_queries = [user_message]  # Ultimate fallback
            
            citations = []
            update_status(chat_id, "summarizing", 70, "Generating CFO summary via Gemini")
            
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are a CFO assistant. Given structured financial data, computed ratios, "
                        "write a concise but insightful summary of the company's financial health. "
                        "Highlight key risks, leverage, liquidity, and performance insights clearly. "
                        "CRITICAL: Output PLAIN TEXT ONLY. Do not use markdown formatting, asterisks, "
                        "hashtags, or any special formatting. Write in normal sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User question: {user_message}\n\n"
                        f"Structured data: {json.dumps(structured_data, indent=2)}\n\n"
                        f"Computed metrics: {json.dumps(metrics, indent=2)}\n\n"
                        f"Insights: {json.dumps(insights, indent=2)}"
                    ),
                },
            ]
            summary = gemini_client.ask_gemini(prompt)
            rag_reasoning = ""

        update_status(chat_id, "saving_results", 90, "Saving CFO agent results")

        # 🔍 If no citations from RAG, add document-level citations as fallback
        if not citations and docs:
            citations = [
                {
                    "document": doc.filename,
                    "page": "",
                    "sub_query": "Source document",
                    "sub_query_index": 0
                }
                for doc in docs[:5]  # Show up to 5 documents
            ]

        # 5️⃣ Save to DB with citations and sub-queries
        chat_msg = session.get(ChatMessage, chat_id)
        chat_msg.role = "agent"
        chat_msg.content = summary
        
        # Build reasoning log with sub-queries and insights
        reasoning_data = {
            "sub_queries": sub_queries,
            "insights": []
        }
        
        # Filter out empty insights and generic "no metrics" messages
        valid_insights = [
            i for i in insights 
            if i and str(i).strip() 
            and "No valid financial metrics" not in str(i)
            and "Could not process" not in str(i)
            and len(str(i).strip()) > 5  # Must have meaningful content
        ]
        
        # Only save insights if they contain actual financial terms/numbers
        has_financial_content = any(
            any(term in str(insight).lower() for term in 
                ['ratio', 'margin', 'equity', 'debt', 'revenue', 'profit', 'loss', 
                 'cash', 'ebitda', 'leverage', '%', '$'])
            for insight in valid_insights
        )
        
        if has_financial_content:
            reasoning_data["insights"] = valid_insights
        
        chat_msg.reasoning_log = json.dumps(reasoning_data)
        chat_msg.citations = json.dumps(citations)  # 🆕 Save RAG citations with sub_query tracking
        chat_msg.status = "done"
        session.add(chat_msg)

        # 6️⃣ Create / update memo summary
        existing_memo = session.exec(select(Memo).where(Memo.task_id == task_id)).first()
        memo_text = summary
        core_metrics = {
            "debt_to_equity": metrics.get("debt_to_equity"),
            "debt_to_revenue": metrics.get("debt_to_revenue"),
            "cash_flow": metrics.get("cash_flow"),
        }

        if existing_memo:
            existing_memo.summary = memo_text
            existing_memo.metrics = json.dumps(core_metrics)
            session.add(existing_memo)
        else:
            new_memo = Memo(task_id=task_id, summary=memo_text, metrics=json.dumps(core_metrics))
            session.add(new_memo)

        session.commit()
        update_status(chat_id, "done", 100, "Analysis complete ✅")

    except Exception as e:
        update_status(chat_id, "failed", 100, f"Agent pipeline failed: {e}")
        print(f"❌ Agent pipeline failed: {e}")
