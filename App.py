import streamlit as st
import pandas as pd

import importlib.util
import io
import zipfile
import time
from io import BytesIO
from pypdf import PdfReader, PdfWriter

# Optional dependency: pdf2image (only used for PDF→Images)
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False

st.set_page_config(page_title="PDF Pro | Bulk Toolkit", page_icon="📑", layout="centered")

# (Optional debug — keep BELOW set_page_config)
# st.write("pypdf spec:", importlib.util.find_spec("pypdf"))

# Optional dependency: pdf2image (only used for PDF→Images)
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False


# =========================
# MUST be first Streamlit call
# =========================
st.set_page_config(page_title="PDF Pro | Bulk Toolkit", page_icon="📑", layout="centered")


# =========================
# STYLE + BANNER (EDIT LINKS)
# =========================
PDF_PRO_LIFETIME_STRIPE_LINK = "PASTE_YOUR_PDF_PRO_STRIPE_LINK_HERE"

st.markdown(
    """
<style>
.stButton>button {
    width: 100%;
    border: none;
    font-weight: 650;
}
.launch-banner {
    background: linear-gradient(90deg, #1e293b, #334155);
    color: #ffffff;
    padding: 14px 16px;
    border-radius: 10px;
    margin: 10px 0 18px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,.12);
}
.launch-banner a {
    background: #ef4444;
    color: white !important;
    padding: 10px 12px;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 800;
    font-size: 0.92rem;
    white-space: nowrap;
}
.small-muted {
    color: #6b7280;
    font-size: 0.88rem;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="launch-banner">
  <div>
    <strong>📑 PDF Pro Lifetime Deal:</strong> Stop paying Adobe for basic tools.<br/>
    Merge, split, compress, export pages — fast, clean, and simple.
  </div>
  <a href="{PDF_PRO_LIFETIME_STRIPE_LINK}" target="_blank">Get Lifetime Access →</a>
</div>
""",
    unsafe_allow_html=True,
)


# =========================
# LICENSE SYSTEM (Google Sheet CSV)
# =========================
# Put your PDF Pro license sheet (published as CSV) here
LICENSE_SHEET_URL = "PASTE_YOUR_PUBLISHED_GOOGLE_SHEET_CSV_URL_HERE"

# Recommended sheet columns (case-insensitive):
# key, tier, email, created_at, app_id(optional)
#
# tier values: free / pro / agency (you choose)


@st.cache_data(ttl=300)
def load_license_sheet() -> pd.DataFrame:
    """Load license sheet (published as CSV). Return normalized DataFrame."""
    try:
        df = pd.read_csv(LICENSE_SHEET_URL)
    except Exception:
        return pd.DataFrame()

    df.columns = [c.strip().lower() for c in df.columns]
    if "key" not in df.columns or "tier" not in df.columns:
        return pd.DataFrame()

    df["key"] = df["key"].astype(str).str.strip().str.upper()
    df["tier"] = df["tier"].astype(str).str.strip().str.lower()
    # Optional app_id column to ensure keys belong to PDF Pro
    if "app_id" in df.columns:
        df["app_id"] = df["app_id"].astype(str).str.strip().str.lower()

    return df


def check_license(license_key: str) -> str:
    """Return tier for key or 'free' if not found."""
    if not license_key:
        return "free"

    df = load_license_sheet()
    if df.empty:
        return "free"

    k = str(license_key).strip().upper()
    row = df.loc[df["key"] == k]
    if row.empty:
        return "free"

    # Optional: enforce app_id == "pdf_pro" if you use it
    if "app_id" in row.columns:
        app_id = str(row.iloc[0].get("app_id", "")).strip().lower()
        if app_id and app_id != "pdf_pro":
            return "free"

    tier = str(row.iloc[0]["tier"]).strip().lower()
    return tier if tier else "free"


# =========================
# PDF ENGINES
# =========================
def merge_pdfs(files) -> bytes:
    writer = PdfWriter()
    for f in files:
        reader = PdfReader(f)
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()


def split_pdf_to_zip(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            page_out = BytesIO()
            writer.write(page_out)
            page_out.seek(0)
            zf.writestr(f"page_{i+1}.pdf", page_out.getvalue())

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def compress_pdf_losslessish(pdf_bytes: bytes) -> bytes:
    """
    Lossless-ish compression: compress content streams.
    (Not a full image downsample; just stream optimization.)
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        try:
            page.compress_content_streams()  # can be CPU heavy on big PDFs
        except Exception:
            pass
        writer.add_page(page)

    # Keep metadata if possible
    try:
        if reader.metadata:
            writer.add_metadata(reader.metadata)
    except Exception:
        pass

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()


def pdf_to_images_zip(pdf_bytes: bytes, fmt: str = "jpeg", dpi: int = 200) -> bytes:
    """
    Convert PDF pages to images and return ZIP bytes.
    Requires pdf2image + poppler installed.
    """
    if not PDF2IMAGE_AVAILABLE:
        raise RuntimeError("pdf2image not available in this environment.")

    images = convert_from_bytes(pdf_bytes, fmt=fmt, dpi=dpi)
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(images):
            img_bytes = BytesIO()
            save_fmt = "JPEG" if fmt.lower() in ("jpg", "jpeg") else "PNG"
            img.save(img_bytes, format=save_fmt)
            img_bytes.seek(0)
            ext = "jpg" if save_fmt == "JPEG" else "png"
            zf.writestr(f"page_{i+1}.{ext}", img_bytes.getvalue())

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# =========================
# SIDEBAR: LICENSE + TOOL PICKER
# =========================
st.sidebar.title("📑 PDF Pro")

license_key = st.sidebar.text_input("License Key", type="password")
user_tier = check_license(license_key)

# Set plan limits (edit to taste)
# Free should be limited to prevent heavy compute blowups.
PLAN_LIMITS = {
    "free": {"merge_files": 3, "max_pages": 30, "dpi": 150},
    "pro": {"merge_files": 20, "max_pages": 300, "dpi": 200},
    "agency": {"merge_files": 100, "max_pages": 1200, "dpi": 250},
}

plan = PLAN_LIMITS.get(user_tier, PLAN_LIMITS["free"])

if user_tier == "free":
    st.sidebar.warning("Free Tier (limited)")
else:
    st.sidebar.success(f"Plan: {user_tier.capitalize()}")

st.sidebar.markdown("---")
tool = st.sidebar.radio(
    "Select Tool",
    ["Merge PDFs", "Split PDF", "PDF → Images", "Compress PDF"],
)
st.sidebar.markdown("---")
st.sidebar.caption("Processed in-memory. No accounts needed.")

st.markdown("---")
st.subheader("📋 Pricing")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🟢 Free")
    st.markdown(
        "- Up to **3 files** per action\n"
        "- Basic tools\n"
        "- No signup required"
    )
    st.markdown("**$0 forever**")

with col2:
    st.markdown("### 🔵 Pro (Lifetime)")
    st.markdown(
        "- Unlimited files\n"
        "- All PDF tools\n"
        "- High-quality exports\n"
        "- Bulk ZIP downloads\n"
        "- Commercial use\n"
        "- No watermarks"
    )
    st.markdown("**$69 one-time**")
    st.markdown("[Get Lifetime Access](YOUR_STRIPE_LINK)")
# =========================
# MAIN UI
# =========================
st.title(tool)
st.markdown('<div class="small-muted">Tip: For large PDFs, use Pro/Agency to avoid limits.</div>', unsafe_allow_html=True)
st.markdown("---")


# =========================
# TOOL: MERGE
# =========================
if tool == "Merge PDFs":
    st.write("Combine multiple PDF files into one.")
    files = st.file_uploader(
        "Upload PDFs (drag & drop)",
        type="pdf",
        accept_multiple_files=True,
        help=f"Free tier max: {plan['merge_files']} files",
    )

    if files:
        if len(files) > plan["merge_files"]:
            st.error(f"Your plan allows up to {plan['merge_files']} files per merge.")
        else:
            if st.button("Merge Files"):
                with st.spinner("Merging PDFs..."):
                    try:
                        merged = merge_pdfs(files)
                        st.success("Done!")
                        st.download_button(
                            "Download Merged PDF",
                            data=merged,
                            file_name="merged.pdf",
                            mime="application/pdf",
                        )
                    except Exception as e:
                        st.error("Merge failed.")
                        st.exception(e)

# =========================
# TOOL: SPLIT
# =========================
elif tool == "Split PDF":
    st.write("Extract every page into a separate PDF (download as ZIP).")
    f = st.file_uploader("Upload a PDF", type="pdf", accept_multiple_files=False)

    if f:
        try:
            reader = PdfReader(BytesIO(f.getvalue()))
            pages = len(reader.pages)
        except Exception:
            pages = None

        if pages is not None and pages > plan["max_pages"]:
            st.error(f"Your plan supports up to {plan['max_pages']} pages. This PDF has {pages}.")
        else:
            if st.button("Split Pages"):
                with st.spinner("Splitting pages..."):
                    try:
                        zip_bytes = split_pdf_to_zip(f.getvalue())
                        st.success("Done!")
                        st.download_button(
                            "Download Pages (ZIP)",
                            data=zip_bytes,
                            file_name="split_pages.zip",
                            mime="application/zip",
                        )
                    except Exception as e:
                        st.error("Split failed.")
                        st.exception(e)

# =========================
# TOOL: PDF → IMAGES
# =========================
elif tool == "PDF → Images":
    st.write("Convert each PDF page into an image (JPG/PNG) and download as ZIP.")
    f = st.file_uploader("Upload a PDF", type="pdf", accept_multiple_files=False)
    fmt = st.selectbox("Output format", ["jpeg", "png"])
    dpi = st.slider("Quality (DPI)", 100, 300, int(plan["dpi"]), step=25)

    if f:
        # Quick page count check
        try:
            reader = PdfReader(BytesIO(f.getvalue()))
            pages = len(reader.pages)
        except Exception:
            pages = None

        if pages is not None and pages > plan["max_pages"]:
            st.error(f"Your plan supports up to {plan['max_pages']} pages. This PDF has {pages}.")
        else:
            if st.button("Convert to Images"):
                with st.spinner("Rendering pages..."):
                    try:
                        zip_bytes = pdf_to_images_zip(f.getvalue(), fmt=fmt, dpi=dpi)
                        st.success("Done!")
                        st.download_button(
                            "Download Images (ZIP)",
                            data=zip_bytes,
                            file_name="pdf_images.zip",
                            mime="application/zip",
                        )
                    except Exception as e:
                        st.error("PDF → Images failed in this environment.")
                        st.info(
                            "If you're on Streamlit Cloud, this usually means **poppler** isn't installed. "
                            "Run this feature on a host/container where poppler is available."
                        )
                        st.exception(e)

# =========================
# TOOL: COMPRESS
# =========================
elif tool == "Compress PDF":
    st.write("Reduce file size via stream optimization (lossless-ish).")
    f = st.file_uploader("Upload a PDF", type="pdf", accept_multiple_files=False)

    if f:
        raw = f.getvalue()
        original_size = len(raw)

        # Page limit check
        try:
            reader = PdfReader(BytesIO(raw))
            pages = len(reader.pages)
        except Exception:
            pages = None

        if pages is not None and pages > plan["max_pages"]:
            st.error(f"Your plan supports up to {plan['max_pages']} pages. This PDF has {pages}.")
        else:
            if st.button("Compress File"):
                with st.spinner("Compressing streams..."):
                    try:
                        compressed = compress_pdf_losslessish(raw)
                        new_size = len(compressed)

                        savings = original_size - new_size
                        if savings > 0:
                            pct = round((savings / original_size) * 100, 1)
                            st.success(f"Reduced by {pct}% ({savings/1024:.1f} KB saved)")
                        else:
                            st.warning("No size reduction detected (already optimized or content type limits compression).")

                        st.download_button(
                            "Download Compressed PDF",
                            data=compressed,
                            file_name="compressed.pdf",
                            mime="application/pdf",
                        )
                    except Exception as e:
                        st.error("Compression failed.")
                        st.exception(e)

# =========================
# FOOTER
# =========================
st.markdown("---")
st.caption("PDF Pro — simple tools that save time.")
