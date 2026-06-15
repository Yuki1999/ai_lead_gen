from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class VideoAsset:
    filename: str
    size_mb: float


@dataclass(frozen=True)
class ProductProfile:
    product_name: str
    category: str
    procedure: str
    summary: str
    specialties: list[str]
    ideal_customer_types: list[str]
    search_keywords: list[str]
    value_points: list[str]
    source_files: list[str]
    video_assets: list[VideoAsset]
    extracted_text_preview: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["video_assets"] = [asdict(asset) for asset in self.video_assets]
        return payload


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def extract_product_profile(root: Path | None = None) -> ProductProfile:
    root = root or project_root()
    pdf_paths = sorted(root.glob("*.pdf"))
    video_paths = sorted(path for path in root.iterdir() if path.suffix.lower() in {".mp4", ".mov"})

    extracted_chunks: list[str] = []
    source_files: list[str] = []
    for pdf_path in pdf_paths:
        source_files.append(pdf_path.name)
        extracted_chunks.append(_extract_pdf_text(pdf_path))

    extracted_text = "\n".join(chunk for chunk in extracted_chunks if chunk).strip()
    normalized = extracted_text.lower()

    product_name = "SkyWalker Robotic Platform Total Knee Application"
    if "skywalker" not in normalized:
        product_name = "Orthopedic Surgical Robotics Product"

    value_points = _value_points(normalized)
    search_keywords = _search_keywords(normalized)

    summary = (
        "CT-based semi-active robotic platform for total knee arthroplasty, supporting "
        "patient-specific preoperative planning, intraoperative adjustment, real-time gap "
        "balancing, robotically located cutting planes, and Evolution Medial-Pivot Knee workflows."
    )
    if not extracted_text:
        summary = (
            "Orthopedic surgical robotics product. The available PDFs did not expose extractable "
            "text, so search terms use file names and known SkyWalker/TKA positioning."
        )

    return ProductProfile(
        product_name=product_name,
        category="orthopedic surgical robotics",
        procedure="total knee arthroplasty (TKA)",
        summary=summary,
        specialties=[
            "orthopedics",
            "joint replacement",
            "knee arthroplasty",
            "hospital operating room capital equipment",
            "surgical robotics",
        ],
        ideal_customer_types=[
            "orthopedic implant distributor",
            "joint replacement product distributor",
            "surgical robotics distributor",
            "hospital capital equipment distributor",
            "orthopedic hospital or joint replacement center",
        ],
        search_keywords=search_keywords,
        value_points=value_points,
        source_files=source_files,
        video_assets=[
            VideoAsset(filename=path.name, size_mb=round(path.stat().st_size / 1024 / 1024, 2))
            for path in video_paths
        ],
        extracted_text_preview=extracted_text[:1400],
    )


def _extract_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(path)
    except Exception:
        return ""

    page_text: list[str] = []
    for page in reader.pages[:10]:
        try:
            page_text.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(page_text)


def _search_keywords(text: str) -> list[str]:
    base = [
        "orthopedic implant distributor",
        "total knee arthroplasty distributor",
        "joint replacement distributor",
        "surgical robotics distributor",
        "hospital capital equipment distributor",
    ]
    if "medial-pivot" in text or "medial pivot" in text:
        base.append("medial pivot knee distributor")
    if "ct-based" in text:
        base.append("CT based orthopedic navigation distributor")
    if "gap balancing" in text:
        base.append("knee gap balancing orthopedic distributor")
    return base


def _value_points(text: str) -> list[str]:
    points = [
        "CT-based patient-specific planning",
        "robotically located cutting planes",
        "total knee arthroplasty workflow",
    ]
    if "real-time gap balancing" in text or "gap balancing" in text:
        points.append("real-time gap balancing")
    if "motion follow" in text or "motion-follow" in text:
        points.append("motion-follow cutting block capability")
    if "evolution" in text and "medial" in text:
        points.append("compatible with Evolution Medial-Pivot Knee implants")
    return points

