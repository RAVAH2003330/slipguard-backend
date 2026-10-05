# forensic.py
import json
import google.generativeai as genai
from PIL import Image

GEMINI_API_KEY = "AQ.Ab8RN6I0kxBFLWP54vWGJrsR_lbx1gBb4m5vq_CUp52-Zpt5-g"  # ඔබේ Gemini API Key එක මෙතැනට දමන්න
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.5-flash")

SYSTEM_PROMPT = """
You are an expert Sri Lankan Banking Forensic Document Examiner.
Analyze this bank transfer receipt/slip image. Look closely for:
1. Font mismatches, digital text insertions, altered amounts or reference numbers.
2. Irregular artifact edges, box misalignments, blurred backgrounds behind text.
3. Extract: bank_name, detected_amount, reference_number.

Return strictly raw JSON format without markdown code blocks:
{
  "bank_name": "Commercial Bank / BOC / Sampath / People's / HNB / etc",
  "amount": 3500.00,
  "reference_number": "12345678",
  "is_tampered": false,
  "risk_score_percentage": 5,
  "anomaly_reasons": [],
  "verdict": "CLEAN / LOW RISK"
}
If tampered or altered, set "is_tampered": true, "verdict": "TAMPERED", and risk_score_percentage above 75.
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