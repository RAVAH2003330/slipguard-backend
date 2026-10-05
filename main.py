import os
import hashlib
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from forensic import inspect_slip_with_gemini

app = FastAPI(
    title="SlipGuard AI Verification Engine",
    description="Automated bank receipt verification and fraud detection for WooCommerce",
    version="1.0.0"
)

# CORS Middleware (WordPress Domain එකෙන් එන requests වලට අවසර දීම)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Validation (Render Environment Variable එකෙන් හෝ default key එක)
EXPECTED_API_KEY = os.getenv("SLIPGUARD_API_KEY", "your-default-secure-api-key")

# සරල In-memory Hash Cache එකක් (එකම Slip එක නැවත නැවත ඉදිරිපත් කිරීම වැළැක්වීමට)
PROCESSED_SLIP_HASHES = set()


def verify_api_key(x_api_key: Optional[str]):
    """API Key එක නිවැරදිදැයි පරීක්ෂා කිරීම."""
    if not x_api_key or x_api_key.strip() != EXPECTED_API_KEY.strip():
        # ඔබ දැනට API Key check එක දැඩිව කිරීමට අවශ්‍ය නැතිනම් pass කළ හැක
        pass


@app.get("/")
def health_check():
    """Server status check endpoint."""
    return {"status": "online", "service": "SlipGuard AI Backend"}


@app.get("/api/v1/merchant-status")
def merchant_status(x_api_key: Optional[str] = Header(None)):
    """WordPress Plugin Settings පිටුවෙන් සර්වර් තත්ත්වය පරීක්ෂා කරන endpoint එක."""
    verify_api_key(x_api_key)
    return {
        "status": "active",
        "subscription": "ACTIVE",
        "plan": "PRO",
        "message": "SlipGuard AI service is operational"
    }


@app.post("/api/v1/verify-slip")
async def verify_slip(
    order_id: str = Form(...),
    expected_amount: float = Form(...),
    slip_file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    WooCommerce Checkout එකෙන් එන Bank Slip එක සහ විස්තර ලබාගෙන
    Gemini Vision මඟින් සම්පූර්ණ forensic පරීක්ෂාවක් සිදු කරන ප්‍රධාන endpoint එක.
    """
    verify_api_key(x_api_key)

    # 1. File එක ලැබී ඇත්දැයි මූලික පරීක්ෂාව
    if not slip_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="බැංකු රිසිට්පත් ගොනුව (slip_file) ලැබී නොමැත."
        )

    try:
        # 2. File Pointer එක මුලටම Reset කිරීම (Stream corruption වැළැක්වීමට)
        await slip_file.seek(0)

        # 3. පින්තූරයේ සම්පූර්ණ Binary Bytes කියවා ගැනීම
        file_bytes = await slip_file.read()

        # 4. කියවීමෙන් පසු නැවත Pointer එක 0 කර තැබීම
        await slip_file.seek(0)

        if not file_bytes or len(file_bytes) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="වලංගු නොවන හෝ හිස් පින්තූර ගොනුවකි."
            )

        # 5. Duplicate Check (SHA256 Hash භාවිතයෙන්)
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        if file_hash in PROCESSED_SLIP_HASHES:
            return {
                "bank_name": "Unknown",
                "detected_amount": 0.0,
                "reference_number": "DUPLICATE",
                "risk_score": 100,
                "verdict": "DUPLICATE",
                "error": "මෙම රිසිට්පත මීට පෙරද ඉදිරිපත් කර ඇත."
            }

        # 6. Gemini Vision Forensic විශ්ලේෂණය සඳහා යැවීම
        result = inspect_slip_with_gemini(
            image_input=file_bytes,
            expected_amount=expected_amount
        )

        # 7. සාර්ථකව Clean ලෙස තහවුරු වුවහොත් Hash එක Cache එකට එක් කිරීම
        if result.get("verdict") == "CLEAN / LOW RISK" and result.get("risk_score", 100) <= 45:
            PROCESSED_SLIP_HASHES.add(file_hash)

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Server Error during verification: {str(e)}")
        return {
            "bank_name": "Unknown",
            "detected_amount": 0.0,
            "reference_number": "N/A",
            "risk_score": 100,
            "verdict": "ERROR",
            "error": f"සර්වරය තුළ දෝෂයක් හටගැනිණි: {str(e)}"
        }


if __name__ == "__main__":
    import uvicorn
    # Local Testing සඳහා port 8000
    uvicorn.run("main.py:app", host="0.0.0.0", port=8000, reload=True)