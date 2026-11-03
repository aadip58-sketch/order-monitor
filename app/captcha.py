"""
captcha.py — High-Accuracy CAPTCHA Solving Engine for SCI Case Monitor.

Uses ddddocr (ONNX neural network specifically trained on CAPTCHAs) paired with
OpenCV contour/component analysis and arithmetic evaluation for Supreme Court of India captchas.
Also supports pytesseract if tesseract binary is installed.
"""

from __future__ import annotations

import os
import re
import shutil
from io import BytesIO

# Suppress warnings
os.environ["TK_SILENCE_DEPRECATION"] = "1"

try:
    import cv2
    import numpy as np
    from PIL import Image
    _CV_OK = True
except ImportError:
    _CV_OK = False

try:
    import ddddocr
    _DDDD_OCR = ddddocr.DdddOcr(show_ad=False)
except Exception:
    _DDDD_OCR = None

try:
    import pytesseract
    _TESS_OK = True
except ImportError:
    _TESS_OK = False


def _find_tesseract_binary() -> str | None:
    candidates = [
        shutil.which("tesseract"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


_TESS_BIN = _find_tesseract_binary()
if _TESS_OK and _TESS_BIN:
    pytesseract.pytesseract.tesseract_cmd = _TESS_BIN


def clean_text(raw: str) -> str:
    """Normalize common OCR confusions for arithmetic digits & operators."""
    s = raw.strip()
    s = re.sub(r'[oOD]', '0', s)
    s = re.sub(r'[lI|i]', '1', s)
    s = re.sub(r'[zZ]', '2', s)
    s = re.sub(r'[sS]', '5', s)
    s = re.sub(r'[bB]', '6', s)
    s = re.sub(r'[>]', '7', s)
    s = re.sub(r'[,_—–~.]', '-', s)
    s = re.sub(r'[tTxX×*]', '+', s)
    s = re.sub(r'[=?].*$', '', s).strip()
    return s


def evaluate_expression(text: str) -> str | None:
    """Evaluate simple arithmetic expression (e.g. '8+4' -> '12', '10-3' -> '7')."""
    s = clean_text(text)
    m = re.search(r'(\d+)\s*([+\-])\s*(\d+)', s)
    if m:
        n1 = int(m.group(1))
        op = m.group(2)
        n2 = int(m.group(3))
        return str(n1 + n2 if op == '+' else n1 - n2)

    cleaned = re.sub(r'[^\d+\-]', '', s)
    if cleaned and any(op in cleaned for op in '+-'):
        try:
            return str(int(eval(cleaned, {'__builtins__': {}})))
        except Exception:
            pass
    return None


def solve_captcha(image_bytes: bytes) -> str:
    """
    Solve Supreme Court of India arithmetic CAPTCHA image bytes.
    Returns the evaluated numeric answer as a string (e.g. '12', '2', '5').
    Returns '' on failure so caller can retry with fresh CAPTCHA.
    """
    if not image_bytes:
        return ""

    # Strategy 1: ddddocr with thresholding and raw bytes
    if _DDDD_OCR is not None:
        try:
            # 1a. Try on thresholded binarized image (cleans background noise)
            if _CV_OK:
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    _, th = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY)
                    _, buf = cv2.imencode('.png', th)
                    res_th = _DDDD_OCR.classification(buf.tobytes())
                    ans = evaluate_expression(res_th)
                    if ans is not None:
                        return ans

            # 1b. Try on raw bytes
            res_raw = _DDDD_OCR.classification(image_bytes)
            ans = evaluate_expression(res_raw)
            if ans is not None:
                return ans

            # 1c. Hybrid ddddocr + OpenCV component analysis
            # If ddddocr got digits but missed operator (e.g. '54' from '5-4')
            if _CV_OK:
                ans_comp = _solve_with_components(img, res_raw)
                if ans_comp:
                    return ans_comp

        except Exception:
            pass

    # Strategy 2: pytesseract if installed
    if _TESS_OK and _TESS_BIN:
        try:
            img_pil = Image.open(BytesIO(image_bytes)).convert("L")
            w, h = img_pil.size
            img_up = img_pil.resize((w * 2, h * 2), Image.LANCZOS)
            arr = np.array(img_up)
            _, thresh = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            denoised = cv2.medianBlur(thresh, 3)
            pil_clean = Image.fromarray(denoised)
            raw = pytesseract.image_to_string(
                pil_clean,
                config="--psm 6 -c tessedit_char_whitelist=0123456789+=-"
            )
            ans = evaluate_expression(raw)
            if ans is not None:
                return ans
        except Exception:
            pass

    return ""


def _solve_with_components(img: np.ndarray, raw_text: str) -> str:
    """Helper: use connected components to recover missing operators."""
    try:
        _, inv = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY_INV)
        nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(inv)
        comps = []
        for i in range(1, nlabels):
            x, y, w, h, a = stats[i]
            if a > 14:
                comps.append((x, y, w, h, a))
        comps.sort(key=lambda c: c[0])

        digits = re.findall(r'\d', clean_text(raw_text))
        if not digits:
            return ""

        # 3 components: [num1, op, num2]
        if len(comps) == 3 and len(digits) >= 2:
            op_comp = comps[1]
            x, y, w, h, a = op_comp
            aspect = w / float(max(1, h))
            op = '-' if aspect > 1.2 or h < 16 else '+'
            n1, n2 = int(digits[0]), int(digits[-1])
            return str(n1 + n2 if op == '+' else n1 - n2)

        # 4 components: e.g. [1, 0, op, num2] for '10 + X'
        if len(comps) == 4 and len(digits) >= 2:
            op_comp = comps[2]
            x, y, w, h, a = op_comp
            aspect = w / float(max(1, h))
            op = '-' if aspect > 1.2 or h < 16 else '+'
            n1 = 10 if (raw_text.startswith('10') or (digits[0] == '1' and digits[1] == '0')) else int(digits[0])
            n2 = int(digits[-1])
            return str(n1 + n2 if op == '+' else n1 - n2)

    except Exception:
        pass
    return ""
