import os
import re
import logging
from pathlib import Path
from threading import Lock
from typing import Any

# Prevent OpenMP / MKL multi-threading deadlocks and PIR oneDNN crashes on Windows
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

logger = logging.getLogger(__name__)

_PIPELINE_LOCK = Lock()
_PADDLE_ENGINE: Any = None
_EASYOCR_ENGINE: Any = None


def _get_paddle_engine() -> Any:
    global _PADDLE_ENGINE
    if _PADDLE_ENGINE is None:
        try:
            from paddleocr import PaddleOCR
            _PADDLE_ENGINE = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
        except Exception as err:
            logger.warning(f"PaddleOCR load error: {err}")
            _PADDLE_ENGINE = False
    return _PADDLE_ENGINE if _PADDLE_ENGINE is not False else None


def _get_easyocr_engine() -> Any:
    global _EASYOCR_ENGINE
    if _EASYOCR_ENGINE is None:
        try:
            import easyocr
            _EASYOCR_ENGINE = easyocr.Reader(["en"], gpu=False)
        except Exception as err:
            logger.warning(f"EasyOCR load error: {err}")
            _EASYOCR_ENGINE = False
    return _EASYOCR_ENGINE if _EASYOCR_ENGINE is not False else None


def clean_ocr_token(text: str) -> str:
    if not text:
        return ""
    t = str(text).strip()
    # Insert spaces between lowercase and uppercase
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    # Insert spaces around currency / colons / question marks in price lines
    t = re.sub(r"(MRP|USP|RS|INR)[?:\s]*(?=\d)", r"\1 ", t, flags=re.I)
    t = re.sub(r"([₹:])([A-Za-z0-9])", r"\1 \2", t)
    # Insert space before MM/YYYY dates if glued to previous words
    t = re.sub(r"([A-Za-z0-9])((?:0[1-9]|1[0-2])/\d{4})", r"\1 \2", t)
    return re.sub(r"\s+", " ", t).strip()


def run_ocr(image_path: str | Path) -> list[dict[str, Any]]:
    """Run cached OCR detection returning normalized bounding box items using PaddleOCR."""
    resolved_image_path = Path(image_path).resolve()

    if not resolved_image_path.is_file():
        raise FileNotFoundError(f"Image not found: {resolved_image_path}")

    # 1. Primary: PaddleOCR PP-OCRv6 Medium engine
    paddle = _get_paddle_engine()
    if paddle is not None:
        try:
            results = None
            try:
                results = paddle.predict(str(resolved_image_path))
            except Exception:
                results = paddle.ocr(str(resolved_image_path))
            
            ocr_items = []
            if results:
                # Handle PaddleOCR 3.x list of OCRResult objects or dicts
                for res_obj in results:
                    if not res_obj:
                        continue
                    
                    res_data = {}
                    if hasattr(res_obj, "json") and isinstance(res_obj.json, dict):
                        res_data = res_obj.json.get("res", res_obj.json)
                    elif isinstance(res_obj, dict):
                        res_data = res_obj.get("res", res_obj)

                    rec_texts = res_data.get("rec_texts") if isinstance(res_data, dict) else None
                    rec_scores = res_data.get("rec_scores") if isinstance(res_data, dict) else None
                    dt_polys = (
                        (res_data.get("dt_polys") or res_data.get("rec_polys") or res_data.get("rec_boxes"))
                        if isinstance(res_data, dict)
                        else None
                    )

                    if not rec_texts and hasattr(res_obj, "rec_texts"):
                        rec_texts = getattr(res_obj, "rec_texts", [])
                        rec_scores = getattr(res_obj, "rec_scores", [])
                        dt_polys = getattr(res_obj, "dt_polys", None) or getattr(res_obj, "rec_polys", None) or getattr(res_obj, "rec_boxes", [])

                    if rec_texts:
                        for idx, raw_text in enumerate(rec_texts):
                            cleaned_txt = clean_ocr_token(raw_text)
                            if not cleaned_txt:
                                continue
                            conf = float(rec_scores[idx]) if rec_scores and idx < len(rec_scores) else 0.9
                            raw_box = dt_polys[idx] if dt_polys and idx < len(dt_polys) else None
                            
                            if hasattr(raw_box, "tolist"):
                                raw_box = raw_box.tolist()

                            if isinstance(raw_box, (list, tuple)) and len(raw_box) > 0:
                                if isinstance(raw_box[0], (list, tuple)):
                                    box_pts = [[float(p[0]), float(p[1])] for p in raw_box if len(p) >= 2]
                                else:
                                    box_pts = [[float(x), float(x)] for x in raw_box]
                            else:
                                box_pts = [[0, 0], [100, 0], [100, 20], [0, 20]]
                                
                            ocr_items.append({
                                "text": cleaned_txt,
                                "confidence": conf,
                                "box": box_pts
                            })
                    # Case B: Standard PaddleOCR tuple list [[box, (text, conf)], ...]
                    elif isinstance(res_obj, (list, tuple)):
                        for line in res_obj:
                            if not line or not isinstance(line, (list, tuple)) or len(line) < 2:
                                continue
                            box = line[0]
                            text_info = line[1]
                            if isinstance(text_info, (list, tuple)):
                                text = str(text_info[0])
                                conf = float(text_info[1])
                            else:
                                text = str(text_info)
                                conf = 0.9
                            
                            cleaned_txt = clean_ocr_token(text)
                            if not cleaned_txt:
                                continue

                            if hasattr(box, "tolist"):
                                box = box.tolist()

                            if isinstance(box, list) and len(box) > 0 and isinstance(box[0], (list, tuple)):
                                box_pts = [[float(p[0]), float(p[1])] for p in box if len(p) >= 2]
                            else:
                                box_pts = [[float(x), float(x)] for x in box]

                            ocr_items.append({"text": cleaned_txt, "confidence": conf, "box": box_pts})

            if ocr_items:
                return ocr_items
        except Exception as err:
            logger.warning(f"PaddleOCR prediction error: {err}")

    # 2. Secondary: EasyOCR cached engine fallback
    easy_engine = _get_easyocr_engine()
    if easy_engine is not None:
        try:
            results = easy_engine.readtext(str(resolved_image_path))
            items = []
            for bbox, text, conf in results:
                pts = [[float(p[0]), float(p[1])] for p in bbox]
                if text and text.strip():
                    items.append({"text": text.strip(), "box": pts, "confidence": float(conf)})
            if items:
                return items
        except Exception as err:
            logger.warning(f"EasyOCR prediction error: {err}")

    # 3. Clean empty fallback - no mock default data
    return []

