import os
import json
import io
import re
from PIL import Image
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def inspect_slip_with_gemini(image_input, expected_amount: float = 0.0, *args, **kwargs) -> dict:
    """
    Sri Lankan Bank Receipt Verification Engine.
    Handles WhatsApp images, scans, and mobile banking screenshots.
    """
    try:
        # 1. Byte Stream Handle කිරීම (File pointer issue එක වලක්වාලීමට)
        if isinstance(image_input, bytes):
            image_bytes = image_input
        elif hasattr(image_input, "read"):
            image_bytes = image_input.read()
            if hasattr(image_input, "seek"):
                image_input.seek(0)
        else:
            with open(image_input, "rb") as f:
                image_bytes = f.read()

        if not image_bytes or len(image_bytes) < 100:
            print("CRITICAL: Received empty or corrupt image bytes!")
            return {
                "bank_name": "Unknown",
                "detected_amount": 0.0,
                "reference_number": "N/A",
                "risk_score": 100,
                "verdict": "ERROR",
                "error": "Empty image received"
            }

        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")

        # 2. Strict JSON Generation Configuration
        generation_config = {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        }

        model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite",
            generation_config=generation_config
        )

        prompt = f"""
        You are an expert Sri Lankan automated banking auditor.
        Examine this bank slip / transfer receipt image. Target Amount: {expected_amount}

        TASKS:
        1. Find the principal payment or transfer amount. Ignore account balances. Look for 'Rs', 'LKR', '/=', or amounts matching {expected_amount}.
        2. Extract the issuing bank name (e.g. Bank of Ceylon, Commercial Bank, Sampath Bank, People's Bank, HNB, FriMi, etc.).
        3. Extract the reference / transaction ID.
        4. Tampering Check: WhatsApp compression, blur, perspective skew, or camera lighting are completely NORMAL. Authentic receipts have risk_score between 5 and 20. Only flag risk_score > 45 if digits are photoshopped or text fonts don't match.

        OUTPUT JSON SCHEMA (Provide pure JSON without markdown):
        {{
            "bank_name": "string",
            "detected_amount": float,
            "reference_number": "string",
            "risk_score": int,
            "verdict": "CLEAN / LOW RISK"
        }}
        """

        response = model.generate_content([prompt, image])
        raw_text = response.text.strip()
        print(f"DEBUG - Raw Gemini Output: {raw_text}")

        # JSON Parse කිරීම
        data = json.loads(raw_text)

        # Numerical amount validation
        detected_val = data.get("detected_amount")
        if isinstance(detected_val, str):
            clean_num = re.sub(r"[^\d.]", "", detected_val)
            data["detected_amount"] = float(clean_num) if clean_num else 0.0
        else:
            data["detected_amount"] = float(detected_val or 0.0)

        data["risk_score"] = int(data.get("risk_score", 10))
        if data["risk_score"] <= 45:
            data["verdict"] = "CLEAN / LOW RISK"
        else:
            data["verdict"] = "SUSPICIOUS"

        print(f"DEBUG - Extracted Data: Bank={data.get('bank_name')}, Amount={data.get('detected_amount')}, Risk={data.get('risk_score')}")
        return data

    except Exception as e:
        print(f"CRITICAL ERROR in inspect_slip_with_gemini: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "bank_name": "Unknown",
            "detected_amount": 0.0,
            "reference_number": "N/A",
            "risk_score": 100,
            "verdict": "ERROR",
            "error": str(e)
        }

# Alias
analyze_bank_slip = inspect_slip_with_gemini