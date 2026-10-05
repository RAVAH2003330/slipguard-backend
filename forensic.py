# forensic.py
import json
import os
import google.generativeai as genai
from PIL import Image

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.5-flash")

# forensic.py හි prompt එක පහත පරිදි සකසන්න:

prompt = """
You are a Sri Lankan bank slip verification specialist. Analyze the uploaded receipt image.

Important Instructions on Image Artifacts:
- Note: Standard mobile screenshots, WhatsApp compression artifacts, lighting shadows, camera blur, or slight angle tilts are NORMAL and NOT tampering.
- Only flag high risk (risk_score > 40) if there are clear visual signs of digital editing: mismatched font styles, different text baseline, whiteout/cut-paste boxes over digits, or painted pixels over the original amount.
- If it looks like an authentic bank receipt with typical mobile/WhatsApp JPEG compression, keep risk_score below 20.

Extract the following in valid JSON:
{
  "bank_name": "Name of the Bank",
  "detected_amount": float,
  "reference_number": "Reference or Transaction ID",
  "risk_score": integer (0 to 100),
  "verdict": "CLEAN / LOW RISK" or "SUSPICIOUS"
}
"""

def inspect_slip_with_gemini(image: Image.Image) -> dict:
    try:
        response = model.generate_content([SYSTEM_PROMPT, image])
        clean_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        return {
            "bank_name": "Unknown",
            "amount": 0.0,
            "reference_number": None,
            "is_tampered": True,
            "risk_score_percentage": 100,
            "anomaly_reasons": [f"AI inspection error: {str(e)}"],
            "verdict": "ERROR"
        }