import os
import json
import re
from PIL import Image
import google.generativeai as genai

# Gemini API Key එක පරිසර විචල්‍යයන්ගෙන් (Environment Variables) ලබා ගැනීම
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def analyze_bank_slip(image_file, expected_amount: float = 0.0) -> dict:
    """
    ශ්‍රී ලංකාවේ බැංකු රිසිට්පත් විශ්ලේෂණය කර මුදල, බැංකුව, 
    ගනුදෙනු අංකය සහ ව්‍යාජ සංස්කරණ (Tampering) හඳුනාගැනීම.
    """
    try:
        # රූප ගොනුව විවෘත කිරීම
        image = Image.open(image_file)

        # Gemini 1.5 Flash ආකෘතිය භාවිතය
        model = genai.GenerativeModel("gemini-3.5-flash")

        prompt = f"""
        You are an expert Sri Lankan bank receipt verification system.
        Analyze this bank transfer receipt / deposit slip image carefully.

        The expected order amount is approximately: {expected_amount}

        Instructions:
        1. Amount Detection:
           - Look specifically for the transferred or deposited monetary amount (labels like: Amount, Paid, LKR, Rs, රු, /=).
           - Ignore transaction fees or account balances; look for the principal payment amount.
           - Remove currency symbols and commas, and extract ONLY the numerical amount as a float (e.g., 350.00).

        2. Bank Details:
           - Extract the name of the Bank (e.g., Bank of Ceylon, Commercial Bank, Sampath Bank, People's Bank, Hatton National Bank, FriMi, etc.).

        3. Transaction Reference:
           - Extract the Reference Number, Transaction ID, or Sequence Number.

        4. Risk & Authenticity Assessment:
           - NOTE: Standard mobile screenshots, WhatsApp compression noise/artifacts, camera perspective skew, lighting variations, or mild lens blur are NORMAL and NOT digital tampering.
           - Only increase risk_score (> 40) if there are obvious cut-and-paste rectangles, font mismatch in digits, or pixel manipulation over the amount or transaction ID.
           - For standard authentic receipts (even with WhatsApp compression), assign a risk_score between 5 and 20.

        Return ONLY a raw valid JSON object with no markdown fences, no backticks, and no extra text:
        {{
          "bank_name": "string",
          "detected_amount": float,
          "reference_number": "string",
          "risk_score": integer (0 to 100),
          "verdict": "CLEAN / LOW RISK" or "SUSPICIOUS"
        }}
        """

        # Gemini වෙත Request එක යැවීම
        response = model.generate_content([prompt, image])
        text_resp = response.text.strip()

        # Markdown code fences (```json ... ```) ඇත්නම් ඉවත් කිරීම
        if text_resp.startswith("```"):
            text_resp = re.sub(r"^```[a-zA-Z]*\n?", "", text_resp)
            text_resp = re.sub(r"```$", "", text_resp).strip()

        data = json.loads(text_resp)

        # Amount එක නිවැරදි float අගයක් බවට පත් කිරීම
        raw_amt = data.get("detected_amount", 0.0)
        if isinstance(raw_amt, str):
            clean_amt = re.sub(r"[^\d.]", "", raw_amt)
            data["detected_amount"] = float(clean_amt) if clean_amt else 0.0
        else:
            data["detected_amount"] = float(raw_amt or 0.0)

        # Risk score නිවැරදි integer එකක් බවට පත් කිරීම
        data["risk_score"] = int(data.get("risk_score", 10))

        # Verdict එක තහවුරු කිරීම
        if "verdict" not in data or not data["verdict"]:
            data["verdict"] = "CLEAN / LOW RISK" if data["risk_score"] <= 40 else "SUSPICIOUS"

        # අමතර හිස් අගයන් සඳහා defaults
        if not data.get("bank_name"):
            data["bank_name"] = "Bank Transfer"
        if not data.get("reference_number"):
            data["reference_number"] = "N/A"

        return data

    except Exception as e:
        print(f"SlipGuard Forensic Error: {str(e)}")
        return {
            "bank_name": "Unknown",
            "detected_amount": 0.0,
            "reference_number": "N/A",
            "risk_score": 100,
            "verdict": "ERROR",
            "error": str(e)
        }