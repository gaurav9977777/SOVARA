import pymupdf as fitz  # PyMuPDF
import docx
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
import os

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}

def is_image_file(file_path):
    """Checks if a file is an image format."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in IMAGE_EXTENSIONS

def render_pdf_to_image(file_path, page_num=0, dpi=150):
    """
    Renders a page of a PDF document into a PNG image.
    Essential for LLaVA OCR scanning of scanned document PDFs.
    """
    try:
        doc = fitz.open(file_path)
        if len(doc) == 0:
            return None
        page = doc[min(page_num, len(doc) - 1)]
        pix = page.get_pixmap(dpi=dpi)
        
        dir_name = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        image_path = os.path.join(dir_name, f"{base_name}_page{page_num + 1}.png")
        pix.save(image_path)
        return image_path
    except Exception as e:
        print(f"Error rendering PDF page to image: {e}")
        return None

def extract_text_from_pdf(file_path):
    """Extracts digital text from PDF."""
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text() + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def extract_text_from_docx(file_path):
    """Extracts text from DOCX file."""
    text = ""
    try:
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"Error reading DOCX: {e}")
    return text

def process_uploaded_document(file_path):
    """
    Analyzes an uploaded file (PDF, DOCX, JPG, PNG).
    If it's an image or a scanned PDF (little or no text), prepares it for LLaVA Vision/OCR.
    """
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()

    if is_image_file(file_path):
        return {
            "type": "image",
            "text": "",
            "image_path": file_path,
            "is_scanned": True,
            "ocr_ready": True
        }

    if ext == ".pdf":
        digital_text = extract_text_from_pdf(file_path).strip()
        # If very little digital text (< 50 chars), it is likely a scanned PDF document
        if len(digital_text) < 50:
            rendered_image = render_pdf_to_image(file_path, page_num=0)
            return {
                "type": "scanned_pdf",
                "text": "[Scanned document detected - LLaVA Vision OCR activated]",
                "image_path": rendered_image,
                "is_scanned": True,
                "ocr_ready": True
            }
        else:
            return {
                "type": "pdf",
                "text": digital_text,
                "image_path": None,
                "is_scanned": False,
                "ocr_ready": False
            }

    if ext == ".docx":
        text = extract_text_from_docx(file_path)
        return {
            "type": "docx",
            "text": text,
            "image_path": None,
            "is_scanned": False,
            "ocr_ready": False
        }

    return {
        "type": "unknown",
        "text": "",
        "image_path": None,
        "is_scanned": False,
        "ocr_ready": False
    }

def export_to_excel(data, filename="sovara_export.xlsx"):
    path = os.path.join(os.getcwd(), filename)
    df = pd.DataFrame([{"Bot Response": data}])
    df.to_excel(path, index=False)
    return path

def export_to_pdf(data, filename="sovara_export.pdf"):
    path = os.path.join(os.getcwd(), filename)
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    
    textobject = c.beginText()
    textobject.setTextOrigin(40, height - 40)
    textobject.setFont("Helvetica", 10)
    
    lines = data.split('\n')
    for line in lines:
        wrapped_lines = simpleSplit(line, "Helvetica", 10, width - 80)
        for wrapped in wrapped_lines:
            if textobject.getY() < 40:
                c.drawText(textobject)
                c.showPage()
                textobject = c.beginText()
                textobject.setTextOrigin(40, height - 40)
                textobject.setFont("Helvetica", 10)
            textobject.textLine(wrapped)
            
    c.drawText(textobject)
    c.save()
    return path
